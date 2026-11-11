"""spec-ptc's OOLONG RLM campaign, three ways, on one vLLM engine.

Arms: same tasks, same engine and the same client code, except the REPL class.

- nospec: stock rlms LocalREPL. Sub-calls run when the program reaches them.
- fanout: spec-ptc's SpeculativeLocalREPL, as the campaign uses it: a shadow pass over
  each finished block, then the real run. This is the mode behind the published 1.0–1.2x.
- stream: cloud/rlm_stream.py's StreamingSpecREPL. The root's tokens feed spec-ptc while
  they stream (sPTC as the blog describes it).

Every arm runs rlm_stream.StreamingRLM, so root completions stream and root TTFT and TPOT
are logged the same way in each; only `stream` feeds them to spec-ptc. Tasks, RLM
settings, scoring and per-unit logs are the campaign's (spec-ptc benchmark/oolong_campaign,
unmodified), and so are the server flags (benchmark/experiments/model_sweep.py,
start_server).

Deviation, on by default (--no-repl-fix turns it off): cloud/repl_fix.py makes rlms'
LocalREPL safe to run as concurrent threads. Stock rlms 0.1.3 swaps the process-wide
sys.stdout and working directory per execution, so concurrent tasks can lose or swap
printed REPL output and crash with FileNotFoundError.

Subcommands:
- tasks: tasks.json from the campaign's load_tasks(n_trec, n_pairs, seed 7).
- run: the campaign, units (arm, concurrency, repeat) in ABBA order, each with a /metrics
  poller. --launch starts vLLM first. Resumable through DONE markers.
- summarize: summary.md and summary.json for an output directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SPEC_PTC = Path(os.environ.get("SPEC_PTC_ROOT") or HERE.parents[1] / "spec-ptc")

MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
ARMS = ("nospec", "fanout", "stream")
# the campaign's server (model_sweep.py start_server, campaign.py MODELS: tp 1, util 0.92)
UPSTREAM_FLAGS = ["--gpu-memory-utilization", "0.92", "--max-model-len", "8192",
              "--tensor-parallel-size", "1", "--enforce-eager"]
UPSTREAM_KERNEL_CONFIG = {"enable_flashinfer_autotune": False, "enable_cutedsl_warmup": False,
                      "enable_jit_warmup": False}
UPSTREAM_ENV = {"VLLM_USE_FLASHINFER_SAMPLER": "0", "VLLM_ATTENTION_BACKEND": "FLASH_ATTN"}

SPEC_KINDS = ("dispatch", "adopt", "claim_hit", "claim_miss", "evict", "shadow_stop")

# The gate (cloud/GATE.md, fixed before the main run): is there time left for more
# speculation to hide, after spec-ptc's streaming mode?
GATE_ARM = "stream"
GATE_CONCS = (8, 4)
GATE_THRESHOLD = 0.15  # median after-stream share of a task's wall time
GATE_MIN_OK_TASKS = 12  # finished tasks a cell needs (of 16 planned)
PROVENANCE_FILES = ("GATE.md", "GATE_ADDENDUM.md", "rlm_campaign.py", "rlm_stream.py",
                    "repl_fix.py", "app.py")


def setup_paths(spec_ptc: Path) -> None:
    os.environ["SPEC_PTC_ROOT"] = str(spec_ptc)
    for p in (str(spec_ptc), str(HERE)):
        if p not in sys.path:
            sys.path.insert(0, p)


# --------------------------------------------------------------------------- tasks
def cmd_tasks(a) -> None:
    setup_paths(a.spec_ptc)
    from benchmark.oolong_campaign.data import load_tasks

    tasks = load_tasks(a.n_trec, a.n_pairs, seed=a.seed)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps([asdict(t) for t in tasks]))
    for t in tasks:
        print(f"{t.task_id:28s} {t.dataset:22s} context {len(t.context):>9,d} chars")


def load_task_file(path: Path, only: str | None = None, limit: int | None = None):
    from benchmark.oolong_campaign.data import Task

    tasks = [Task(**r) for r in json.loads(Path(path).read_text())]
    if only:
        tasks = [t for t in tasks if t.dataset.startswith(only)]
    return tasks[:limit] if limit else tasks


# --------------------------------------------------------------------------- server
def kernel_config(py: str) -> tuple[dict, list[str]]:
    """The campaign's --kernel-config, minus keys this vLLM's KernelConfig doesn't define."""
    code = ("import dataclasses, json\n"
            "try:\n    from vllm.config import KernelConfig\n"
            "except ImportError:\n    from vllm.config.kernel import KernelConfig\n"
            "print(json.dumps([f.name for f in dataclasses.fields(KernelConfig)]))")
    try:
        out = subprocess.run([py, "-c", code], capture_output=True, text=True, timeout=600)
        fields = set(json.loads(out.stdout.strip().splitlines()[-1]))
    except Exception:  # noqa: BLE001 - keep the config as is
        return dict(UPSTREAM_KERNEL_CONFIG), []
    keep = {k: v for k, v in UPSTREAM_KERNEL_CONFIG.items() if k in fields}
    return keep, sorted(set(UPSTREAM_KERNEL_CONFIG) - set(keep))


class Server:
    def __init__(self, model: str, port: int, log_path: Path, extra: list[str] | None = None,
                 py: str = sys.executable) -> None:
        self.model, self.port, self.log_path = model, port, log_path
        self.extra, self.py = extra or [], py
        self.proc: subprocess.Popen | None = None
        self.info: dict = {}

    def start(self) -> None:
        kc, dropped = kernel_config(self.py)
        cmd = [self.py, "-m", "vllm.entrypoints.openai.api_server", "--model", self.model,
               "--port", str(self.port), *UPSTREAM_FLAGS, "--kernel-config", json.dumps(kc),
               *self.extra]
        self.info = {"cmd": cmd, "env": UPSTREAM_ENV, "kernel_config": kc,
                     "kernel_config_dropped": dropped, "t_start": time.time()}
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "w")
        self.proc = subprocess.Popen(cmd, env={**os.environ, **UPSTREAM_ENV}, stdout=log,
                                     stderr=subprocess.STDOUT)

    def wait(self, timeout: float = 2400) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc is not None and self.proc.poll() is not None:
                return False
            try:
                urllib.request.urlopen(f"http://localhost:{self.port}/v1/models", timeout=3)
                self.info["ready_s"] = round(time.time() - self.info["t_start"], 1)
                return True
            except Exception:  # noqa: BLE001
                time.sleep(5)
        return False

    def facts(self) -> dict:
        """Lines from the server log worth keeping: KV size, concurrency, backend, version."""
        keys = ("GPU KV cache size", "Maximum concurrency", "attention backend",
                "Using FLASH_ATTN", "vLLM API server version", "Available KV cache memory",
                "model weights took", "Model loading took")
        out = []
        try:
            for line in self.log_path.read_text(errors="replace").splitlines():
                if any(k.lower() in line.lower() for k in keys):
                    out.append(line.strip()[-240:])
        except OSError:
            pass
        return {**self.info, "log_facts": out[:40]}

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.proc.kill()


# --------------------------------------------------------------------------- /metrics poller
GAUGES = {"running": ("num_requests_running",), "waiting": ("num_requests_waiting",),
          "kv": ("kv_cache_usage_perc", "gpu_cache_usage_perc")}
COUNTERS = {"preemptions": ("num_preemptions_total", "num_preemptions"),
            "prefix_queries": ("prefix_cache_queries_total", "prefix_cache_queries"),
            "prefix_hits": ("prefix_cache_hits_total", "prefix_cache_hits"),
            "prompt_tokens": ("prompt_tokens_total",),
            "gen_tokens": ("generation_tokens_total",)}
FIELDS = ["t", *GAUGES, *COUNTERS, "host_cpu"]


def parse_metric(text: str, names: tuple) -> float | None:
    """Sum of a metric over its label sets; the first matching name wins (as
    kaggle/vllm_bench.py MetricsPoller.parse)."""
    for want in names:
        tot, seen = 0.0, False
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            name = line.split("{", 1)[0].split(" ", 1)[0]
            if name.split(":", 1)[-1] != want:
                continue
            try:
                tot += float(line.rsplit(" ", 1)[1])
                seen = True
            except ValueError:
                pass
        if seen:
            return tot
    return None


class Poller:
    def __init__(self, root_url: str, path: Path, every: float = 0.5) -> None:
        self.url, self.path, self.every = f"{root_url}/metrics", path, every
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._loop, daemon=True)
        try:
            import psutil

            psutil.cpu_percent(None)
            self._cpu = lambda: psutil.cpu_percent(None) / 100.0
        except ImportError:
            self._cpu = lambda: None

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._th.start()

    def stop(self) -> None:
        self._stop.set()
        self._th.join(timeout=10)

    def _loop(self) -> None:
        with open(self.path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            while not self._stop.is_set():
                t = time.time()
                row = {"t": round(t, 3), "host_cpu": self._cpu()}
                try:
                    text = urllib.request.urlopen(self.url, timeout=3).read().decode()
                    for k, names in {**GAUGES, **COUNTERS}.items():
                        row[k] = parse_metric(text, names)
                except Exception:  # noqa: BLE001 - a missed sample stays empty
                    pass
                w.writerow(row)
                f.flush()
                self._stop.wait(max(0.0, self.every - (time.time() - t)))


# --------------------------------------------------------------------------- campaign
def plan_units(arms, concs, repeats) -> list[tuple[str, int, int]]:
    """ABBA within each concurrency: odd repeats in `arms` order, even repeats reversed."""
    units = []
    for c in concs:
        for r in range(1, repeats + 1):
            order = arms if r % 2 else tuple(reversed(arms))
            units += [(arm, c, r) for arm in order]
    return units


def unit_dir(out: Path, arm: str, conc: int, rep: int) -> Path:
    return out / "units" / f"{arm}_c{conc}_r{rep}"


def done_seconds(out: Path, conc: int) -> list[float]:
    xs = []
    for p in (out / "units").glob(f"*_c{conc}_r*/unit.json"):
        m = json.loads(p.read_text())
        if (p.parent / "DONE").exists():
            xs.append(m["t1"] - m["t0"])
    return xs


def provenance(spec_ptc: Path) -> dict:
    """sha256 of the files that define this run, taken before the first unit: the gate
    (GATE.md), the campaign code, and spec-ptc's Python sources (the client under test)."""
    import hashlib

    def sha(p: Path) -> str | None:
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None

    tree = hashlib.sha256()
    n = 0
    for p in sorted(Path(spec_ptc).rglob("*.py")):
        rel = p.relative_to(spec_ptc).as_posix()
        if "__pycache__" in rel or rel.startswith((".venv", "tests/")):
            continue
        tree.update(f"{rel}\0{sha(p)}\n".encode())
        n += 1
    return {"files": {name: sha(HERE / name) for name in PROVENANCE_FILES},
            "spec_ptc_py_tree": tree.hexdigest(), "spec_ptc_py_files": n}


# Warm-up waves: (concurrent sub-call-like requests, prompt size). Each wave runs next to
# one streamed, root-like request.
WARMUP_WAVES = ((1, "short"), (2, "short"), (4, "short"), (8, "short"), (16, "short"),
                (32, "short"), (64, "short"), (128, "short"),
                (1, "long"), (4, "long"), (16, "long"))
_WARMUP_FILLER = "The quarterly metrics improved across all measured dimensions. "


def warmup(base_url: str, model: str, passes: int, note=None) -> list[dict]:
    """Send every batch shape the campaign will produce once before the first unit.

    With --enforce-eager (the campaign's flags) vLLM skips its kernel warm-up and compiles kernels
    the first time a batch shape appears. In the smoke run of 2026-11-09 the first burst
    of 13 concurrent sub-calls stalled the root's stream for 8.4 s; the same burst took
    1.1 s later in that run. Without a warm-up, whichever arm first sends concurrent calls
    pays for that.

    Each wave is one streamed request with `n` concurrent short-output requests next to
    it. Prompts are unique, so nothing comes from the prefix cache. Returns one record per
    wave: its wall time and the longest gap between the streamed request's tokens. A
    second pass shows what a warm engine does with the same waves."""
    from concurrent.futures import ThreadPoolExecutor

    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key="EMPTY", timeout=300)
    rng = random.Random(0)

    def prompt(kind: str) -> str:
        tag = f"[{rng.getrandbits(64):016x}] "
        if kind == "long":  # about 3,400 tokens, under the campaign's 4,096-token sub-call room
            return tag + "Summarize in three words:\n" + _WARMUP_FILLER * 340
        return tag + ("Classify the following question into one of these categories: 'entity', "
                      "'location', 'numeric value'. Only output the category name. Question: "
                      "What bay sparkles next to Miami , Florida ?")

    def sub(p: str) -> None:
        client.chat.completions.create(model=model, max_tokens=4, temperature=0.0,
                                       messages=[{"role": "user", "content": p}])

    def root(p: str) -> float:
        """A streamed request; returns its longest gap between tokens, in ms."""
        last, gap = None, 0.0
        for chunk in client.chat.completions.create(
                model=model, max_tokens=48, temperature=0.0, stream=True,
                messages=[{"role": "user", "content": p + " Then explain why, at length."}]):
            if chunk.choices and getattr(chunk.choices[0].delta, "content", None):
                now = time.perf_counter()
                if last is not None:
                    gap = max(gap, now - last)
                last = now
        return 1000 * gap

    waves = []
    for k in range(1, passes + 1):
        for n, kind in WARMUP_WAVES:
            t0 = time.perf_counter()
            with ThreadPoolExecutor(max_workers=n + 1) as pool:
                stream = pool.submit(root, prompt("short"))
                time.sleep(0.5)  # the burst arrives while the stream decodes
                subs = [pool.submit(sub, prompt(kind)) for _ in range(n)]
                errors = sum(1 for f in subs if f.exception() is not None)
                try:
                    gap_ms = round(stream.result(), 1)
                except Exception:  # noqa: BLE001 - a failed warm-up request is only recorded
                    gap_ms, errors = None, errors + 1
            rec = {"pass": k, "n": n, "prompt": kind, "errors": errors,
                   "wall_s": round(time.perf_counter() - t0, 3), "stream_max_gap_ms": gap_ms}
            waves.append(rec)
            if note is not None:
                note("warmup_wave", **rec)
    return waves


def run_campaign(a, on_unit_done=None) -> Path:
    setup_paths(a.spec_ptc)
    import benchmark.oolong_campaign.runner as runner
    import rlm.environments as rlm_envs
    import rlm_stream

    import repl_fix

    if a.repl_fix:
        repl_fix.apply()
    stock = runner._STOCK_LOCAL_REPL
    classes = {"nospec": stock, "fanout": rlm_stream.SpeculativeLocalREPL,
               "stream": rlm_stream.StreamingSpecREPL}
    runner.RLM = rlm_stream.StreamingRLM  # every arm: streamed root, root timing logged
    orig_run_task = runner._run_task

    def run_task(task, model, base_url, spec, log, outdir, **kw):
        rlm_stream.bind_task(task.task_id, log)
        try:
            return orig_run_task(task, model, base_url, spec, log, outdir, **kw)
        finally:
            rlm_stream.unbind_task()

    runner._run_task = run_task

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tasks = load_task_file(a.tasks, a.only, a.limit)
    camp = open(out / "campaign.jsonl", "a", buffering=1)

    def note(kind: str, **d) -> None:
        camp.write(json.dumps({"t": round(time.time(), 3), "kind": kind, **d}) + "\n")

    server = None
    base = a.base_url or f"http://localhost:{a.port}/v1"
    note("begin", tasks=[t.task_id for t in tasks], arms=a.arms, conc=a.conc,
         repeats=a.repeats, model=a.model, base_url=base, max_minutes=a.max_minutes,
         repl_fix=repl_fix.applied(), serve_extra=a.serve_extra,
         warmup_passes=a.warmup_passes, root_max_deltas=rlm_stream.ROOT_MAX_DELTAS,
         **provenance(a.spec_ptc))
    t_begin = time.time()
    try:
        if a.launch:
            server = Server(a.model, a.port, out / "server.log", a.serve_extra)
            server.start()
            ok = server.wait(a.start_timeout)
            (out / "server.json").write_text(json.dumps(server.facts(), indent=1))
            if not ok:
                note("server_failed")
                raise RuntimeError(f"vLLM did not start; see {out / 'server.log'}")
            note("server_ready", ready_s=server.info.get("ready_s"),
                 kernel_config_dropped=server.info.get("kernel_config_dropped"))
        units = plan_units(tuple(a.arms), a.conc, a.repeats)
        if a.warmup_passes and any(not (unit_dir(out, *u) / "DONE").exists() for u in units):
            t_w = time.time()
            waves = warmup(base, a.model, a.warmup_passes, note)
            note("warmup_done", passes=a.warmup_passes, waves=len(waves),
                 wall_s=round(time.time() - t_w, 1),
                 errors=sum(w["errors"] for w in waves))
            print(f"warm-up: {len(waves)} waves in {time.time() - t_w:.0f} s", flush=True)
        for arm, conc, rep in units:
            udir = unit_dir(out, arm, conc, rep)
            if (udir / "DONE").exists():
                continue
            prev = done_seconds(out, conc)
            est = statistics.mean(prev) if prev else (a.unit_estimate_min or 0) * 60
            spent = time.time() - t_begin
            if a.max_minutes and spent + est > a.max_minutes * 60:
                note("budget_stop", unit=udir.name, spent_s=round(spent), estimate_s=round(est))
                print(f"budget: stop before {udir.name} ({spent / 60:.1f} min spent, "
                      f"~{est / 60:.1f} min more)", flush=True)
                break

            def set_spec(enabled: bool, arm: str = arm) -> None:
                cls = classes[arm] if enabled else stock
                rlm_envs.LocalREPL = cls
                rlm_envs.local_repl.LocalREPL = cls

            runner._set_speculation = set_spec
            poller = Poller(base.rsplit("/v1", 1)[0], udir / "metrics.csv", a.metrics_every)
            poller.start()
            t0 = time.time()
            note("unit_begin", unit=udir.name)
            try:
                stats = runner.run_unit(a.model, base, arm != "nospec", conc, rep, tasks, udir)
            finally:
                poller.stop()
            t1 = time.time()
            (udir / "unit.json").write_text(json.dumps(
                {"arm": arm, "conc": conc, "rep": rep, "t0": t0, "t1": t1,
                 "tasks": [t.task_id for t in tasks]}))
            if (udir / "rlm_trajs").is_dir():
                compact_unit(udir)
            (udir / "DONE").write_text(str(t1))
            note("unit_end", unit=udir.name, wall_s=round(t1 - t0, 1),
                 errors=stats.get("n_errors"), score=stats.get("score_mean"))
            print(f"{udir.name}: {t1 - t0:.0f} s, task p50 {stats['task_wall_p50_s']} s, "
                  f"score {stats['score_mean']}, errors {stats['n_errors']}", flush=True)
            if on_unit_done is not None:
                on_unit_done(udir)
    finally:
        if server is not None:
            (out / "server.json").write_text(json.dumps(server.facts(), indent=1))
            server.stop()
        note("end", spent_s=round(time.time() - t_begin))
        camp.close()
    summarize(out)
    return out


# --------------------------------------------------------------------------- compact
def compact_unit(udir: Path) -> dict:
    """Write trajs_compact/ next to a unit's rlm_trajs/: the same JSON lines without each
    block's `locals` (the REPL's variables, the whole context among them) and without each
    turn's `prompt` (the message history). What is left is what the offline analyses read:
    the replies, the code, its output, and every recorded sub-call with its prompt,
    response and time. Typically a few percent of the size."""
    src, dst = udir / "rlm_trajs", udir / "trajs_compact"
    dst.mkdir(exist_ok=True)
    before = after = 0
    for f in sorted(src.glob("*.jsonl")):
        before += f.stat().st_size
        with open(f) as fin, open(dst / f.name, "w") as fout:
            for line in fin:
                if not line.strip():
                    continue
                d = json.loads(line)
                if d.get("type") == "iteration":
                    d.pop("prompt", None)
                    for b in d.get("code_blocks", []):
                        (b.get("result") or {}).pop("locals", None)
                fout.write(json.dumps(d) + "\n")
        after += (dst / f.name).stat().st_size
    return {"unit": udir.name, "files": len(list(dst.glob("*.jsonl"))), "bytes": before,
            "compact_bytes": after}


def compact(out: Path) -> list[dict]:
    return [compact_unit(u) for u in sorted((Path(out) / "units").glob("*_c*_r*"))
            if (u / "rlm_trajs").is_dir()]


# --------------------------------------------------------------------------- summary
def _pct(xs: list[float], q: float) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _geo_ratio_ci(pairs: list[tuple[float, float]], n_boot: int = 4000, seed: int = 0):
    """Geometric mean of num/den over pairs, with a bootstrap 95% CI (resampling pairs)."""
    logs = [math.log(n / d) for n, d in pairs if n > 0 and d > 0]
    if not logs:
        return None, None, None
    rng = random.Random(seed)
    boots = sorted(statistics.fmean(rng.choices(logs, k=len(logs))) for _ in range(n_boot))
    return (math.exp(statistics.fmean(logs)), math.exp(boots[int(0.025 * n_boot)]),
            math.exp(boots[int(0.975 * n_boot) - 1]))


def _read_metrics(path: Path) -> dict:
    rows = []
    if path.exists():
        with open(path) as f:
            rows = list(csv.DictReader(f))

    def col(k):
        return [float(r[k]) for r in rows if r.get(k) not in (None, "")]

    waiting, running, kv, pre = col("waiting"), col("running"), col("kv"), col("preemptions")
    return {
        "samples": len(rows),
        "queue_share": (sum(1 for w in waiting if w > 0) / len(waiting)) if waiting else None,
        "max_waiting": max(waiting) if waiting else None,
        "mean_running": statistics.fmean(running) if running else None,
        "max_running": max(running) if running else None,
        "kv_peak": max(kv) if kv else None,
        "preemptions": (pre[-1] - pre[0]) if len(pre) > 1 else None,
        "host_cpu_mean": statistics.fmean(col("host_cpu")) if col("host_cpu") else None,
    }


def load_units(out: Path) -> list[dict]:
    units = []
    for udir in sorted((out / "units").glob("*_c*_r*")):
        if not (udir / "DONE").exists():
            continue
        meta = json.loads((udir / "unit.json").read_text())
        stats = json.loads((udir / "unit_stats.json").read_text())
        events = [json.loads(line) for line in open(udir / "events.jsonl") if line.strip()]
        roots = [e for e in events if e.get("kind") == "root_stream"]
        spec = Counter(e["kind"][5:] for e in events if str(e.get("kind", "")).startswith("spec_"))
        units.append({**meta, "unit": udir.name, "wall_s": meta["t1"] - meta["t0"],
                      "tasks": stats.get("tasks", []), "roots": roots, "spec": dict(spec),
                      "engine": _read_metrics(udir / "metrics.csv")})
    return units


def task_shares(units: list[dict]) -> list[dict]:
    """Per finished task: its wall time, the time its root spent streaming, and the time
    after each stream until that turn's code had run (the shadow's wait plus the real run)."""
    out = []
    for u in units:
        acc: dict = defaultdict(lambda: [0.0, 0.0, 0])
        for r in u["roots"]:
            a = acc[r.get("task_id")]
            a[0] += float(r.get("stream_s") or 0.0)
            a[1] += float(r.get("shadow_wait_s") or 0.0) + float(r.get("exec_s") or 0.0)
            a[2] += 1
        for t in u["tasks"]:
            if not t.get("ok") or not t.get("wall_s") or t["task_id"] not in acc:
                continue
            stream_s, after_s, turns = acc[t["task_id"]]
            out.append({"task_id": t["task_id"], "unit": u["unit"], "wall_s": t["wall_s"],
                        "stream_s": stream_s, "after_s": after_s, "turns": turns,
                        "after_share": after_s / t["wall_s"],
                        "stream_share": stream_s / t["wall_s"]})
    return out


def _median_ci(xs: list[float], n_boot: int = 4000, seed: int = 0):
    """Median with a bootstrap 95% CI (resampling tasks)."""
    if not xs:
        return None, None, None
    rng = random.Random(seed)
    boots = sorted(statistics.median(rng.choices(xs, k=len(xs))) for _ in range(n_boot))
    return (statistics.median(xs), boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1])


def gate(rows: list[dict]) -> dict:
    """cloud/GATE.md's rule on the summary rows."""
    cells = []
    for r in rows:
        if r["arm"] != GATE_ARM:
            continue
        share = (r.get("after_share") or {}).get("p50")
        cells.append({"conc": r["conc"], "ok_tasks": r.get("ok_tasks", 0), "share": share,
                      "ci": (r.get("after_share") or {}).get("ci"),
                      "valid": share is not None and r.get("ok_tasks", 0) >= GATE_MIN_OK_TASKS})
    valid = [c for c in cells if c["valid"]]
    if any(c["share"] >= GATE_THRESHOLD for c in valid):
        verdict = "go"
    elif {c["conc"] for c in valid} >= set(GATE_CONCS):
        verdict = "no-go"
    else:
        verdict = "unresolved"
    return {"verdict": verdict, "threshold": GATE_THRESHOLD, "min_ok_tasks": GATE_MIN_OK_TASKS,
            "arm": GATE_ARM, "concs": list(GATE_CONCS), "cells": cells}


def summarize(out: Path) -> dict:
    out = Path(out)
    units = load_units(out)
    by: dict = defaultdict(list)
    for u in units:
        by[(u["arm"], u["conc"])].append(u)
    walls = {(u["arm"], u["conc"], u["rep"], t["task_id"]): t["wall_s"]
             for u in units for t in u["tasks"] if t.get("ok")}
    rows = []
    for (arm, conc), us in sorted(by.items(), key=lambda kv: (-kv[0][1], ARMS.index(kv[0][0]))):
        tasks = [t for u in us for t in u["tasks"]]
        ok = [t for t in tasks if t.get("ok")]
        roots = [r for u in us for r in u["roots"]]
        shares = task_shares(us)
        wall = sum(s["wall_s"] for s in shares)
        p50, lo, hi = _median_ci([s["after_share"] for s in shares])
        row = {
            "arm": arm, "conc": conc, "units": len(us), "tasks": len(tasks),
            "errors": len(tasks) - len(ok), "ok_tasks": len(shares),
            "turns_mean": statistics.fmean(s["turns"] for s in shares) if shares else None,
            # where a task's wall time goes: the root's streams, and the time after them
            "after_share": {"p50": p50, "ci": [lo, hi],
                            "pooled": sum(s["after_s"] for s in shares) / wall if wall else None},
            "stream_share": {"p50": _pct([s["stream_share"] for s in shares], 0.5),
                             "pooled": (sum(s["stream_s"] for s in shares) / wall
                                        if wall else None)},
            "score": statistics.fmean(t.get("score", 0.0) for t in tasks) if tasks else None,
            "task_wall_p50": _pct([t["wall_s"] for t in ok], 0.5),
            "task_wall_mean": statistics.fmean(t["wall_s"] for t in ok) if ok else None,
            "unit_wall_mean": statistics.fmean(u["wall_s"] for u in us),
            "root_ttft_p50": _pct([r.get("ttft_s") for r in roots], 0.5),
            "root_tpot_p50": _pct([r.get("tpot_ms") for r in roots], 0.5),
            "root_tpot_p99": _pct([r.get("tpot_ms") for r in roots], 0.99),
            "shadow_wait_p50": _pct([r.get("shadow_wait_s") for r in roots if r.get("fed")], 0.5),
            "spec": {k: sum(u["spec"].get(k, 0) for u in us) for k in SPEC_KINDS},
        }
        for k in ("queue_share", "max_waiting", "mean_running", "max_running", "kv_peak",
                  "preemptions", "host_cpu_mean"):
            vals = [u["engine"][k] for u in us if u["engine"].get(k) is not None]
            peak = k in ("max_waiting", "max_running", "kv_peak", "host_cpu_mean")
            agg = max if peak else statistics.fmean
            row[k] = agg(vals) if vals else None
        for ref in ("nospec", "fanout"):
            if ref == arm:
                continue
            pairs = [(w, walls[(ref, c, r, tid)]) for (a_, c, r, tid), w in walls.items()
                     if a_ == arm and c == conc and (ref, c, r, tid) in walls]
            g, lo, hi = _geo_ratio_ci(pairs)
            row[f"vs_{ref}"] = {"ratio": g, "ci": [lo, hi], "pairs": len(pairs)}
        rows.append(row)
    summary = {"units": len(units), "rows": rows, "gate": gate(rows)}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    (out / "summary.md").write_text(render(rows, summary["gate"]))
    return summary


def _f(x, nd=2) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def render_shares(rows: list[dict], g: dict | None) -> list[str]:
    """Where a task's wall time goes, and the gate's verdict (cloud/GATE.md)."""
    lines = [
        "", "## Where the time goes", "",
        "Shares of a finished task's wall time. Root stream: the root's completions, from "
        "request to last token. After the stream: from the end of each stream until that "
        "turn's code has run (the shadow's wait plus the real run). In nospec that is all "
        "the tool time. In stream it is what speculation did not hide, and so the most that "
        "more speculation within a turn could still save. The median is over tasks, with a "
        "bootstrap 95% CI; pooled is total time over total time.", "",
        "| arm | conc | finished tasks | turns per task | root stream share p50 (pooled) "
        "| after-stream share p50 [CI] | pooled |",
        "|" + "---|" * 7,
    ]
    for r in rows:
        a, s = r.get("after_share") or {}, r.get("stream_share") or {}
        ci = a.get("ci") or [None, None]
        lines.append(
            f"| {r['arm']} | {r['conc']} | {r.get('ok_tasks', 0)} | {_f(r.get('turns_mean'), 1)} "
            f"| {_f(s.get('p50'), 3)} ({_f(s.get('pooled'), 3)}) "
            f"| {_f(a.get('p50'), 3)} [{_f(ci[0], 3)}, {_f(ci[1], 3)}] | {_f(a.get('pooled'), 3)} |")
    if g:
        lines += ["", f"**Gate: {g['verdict'].upper()}.** Rule (cloud/GATE.md): go if the "
                  f"{g['arm']} arm's median after-stream share is at least {g['threshold']:.2f} "
                  f"at concurrency {' or '.join(str(c) for c in g['concs'])}, in a cell with at "
                  f"least {g['min_ok_tasks']} finished tasks."]
        for c in g["cells"]:
            lines.append(f"- concurrency {c['conc']}: share {_f(c['share'], 3)}, "
                         f"{c['ok_tasks']} finished tasks, "
                         f"{'valid' if c['valid'] else 'not valid'}")
    return lines


def render(rows: list[dict], g: dict | None = None) -> str:
    lines = [
        "# RLM campaign summary (measured)", "",
        "Task wall ratios are geometric means over tasks paired by (task, repeat), against the "
        "same concurrency's nospec (or fanout) arm, with a bootstrap 95% CI over pairs. Root "
        "TPOT is per root completion (ms per token after the first). Engine columns come from "
        "vLLM's /metrics: queue share is the share of samples with a request waiting.", "",
        "| arm | conc | units | tasks (err) | score | task wall p50 s | vs nospec | vs fanout "
        "| root TTFT p50 s | root TPOT p50 / p99 ms | queue | max wait | preempt/unit "
        "| KV peak | running mean / max | dispatch / hit / miss / evict | host CPU max |",
        "|" + "---|" * 17,
    ]
    for r in rows:
        def vs(k):
            v = r.get(k)
            if not v or v["ratio"] is None:
                return "-"
            return f"{v['ratio']:.3f} [{v['ci'][0]:.3f}, {v['ci'][1]:.3f}] n={v['pairs']}"

        s = r["spec"]
        lines.append(
            f"| {r['arm']} | {r['conc']} | {r['units']} | {r['tasks']} ({r['errors']}) "
            f"| {_f(r['score'], 3)} | {_f(r['task_wall_p50'], 1)} | {vs('vs_nospec')} "
            f"| {vs('vs_fanout')} | {_f(r['root_ttft_p50'], 3)} "
            f"| {_f(r['root_tpot_p50'], 1)} / {_f(r['root_tpot_p99'], 1)} "
            f"| {_f(r['queue_share'])} | {_f(r['max_waiting'], 0)} | {_f(r['preemptions'], 1)} "
            f"| {_f(r['kv_peak'])} | {_f(r['mean_running'], 1)} / {_f(r['max_running'], 0)} "
            f"| {s['dispatch']} / {s['claim_hit']} / {s['claim_miss']} / {s['evict']} "
            f"| {_f(r['host_cpu_mean'])} |")
    lines += render_shares(rows, g)
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- cli
def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--spec-ptc", type=Path, default=DEFAULT_SPEC_PTC)
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tasks")
    t.add_argument("--out", type=Path, required=True)
    t.add_argument("--n-trec", type=int, default=4)
    t.add_argument("--n-pairs", type=int, default=4)
    t.add_argument("--seed", type=int, default=7)

    r = sub.add_parser("run")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--tasks", type=Path, required=True)
    r.add_argument("--only", default=None, help="dataset prefix, e.g. trec")
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--model", default=MODEL)
    r.add_argument("--arms", type=lambda s: s.split(","), default=list(ARMS))
    r.add_argument("--conc", type=lambda s: [int(x) for x in s.split(",")], default=[8, 4])
    r.add_argument("--repeats", type=int, default=2)
    r.add_argument("--base-url", default=None)
    r.add_argument("--port", type=int, default=8210)
    r.add_argument("--launch", action="store_true", help="start vLLM with the campaign's flags first")
    r.add_argument("--serve-extra", type=lambda s: s.split(), default=[])
    r.add_argument("--start-timeout", type=float, default=2400)
    r.add_argument("--metrics-every", type=float, default=0.5)
    r.add_argument("--max-minutes", type=float, default=0, help="0: no budget stop")
    r.add_argument("--unit-estimate-min", type=float, default=0)
    r.add_argument("--no-repl-fix", dest="repl_fix", action="store_false",
                   help="run rlms' LocalREPL as shipped (races between concurrent tasks)")
    r.add_argument("--warmup-passes", type=int, default=0,
                   help="passes of warm-up waves before the first unit (see warmup)")

    s = sub.add_parser("summarize")
    s.add_argument("--out", type=Path, required=True)

    c = sub.add_parser("compact", help="trajs_compact/ for every unit (see compact_unit)")
    c.add_argument("--out", type=Path, required=True)
    return ap


def main(argv=None) -> None:
    a = parser().parse_args(argv)
    if a.cmd == "tasks":
        cmd_tasks(a)
    elif a.cmd == "run":
        for arm in a.arms:
            if arm not in ARMS:
                raise SystemExit(f"unknown arm {arm!r}; choose from {ARMS}")
        run_campaign(a)
        print((Path(a.out) / "summary.md").read_text())
    elif a.cmd == "compact":
        for r in compact(a.out):
            print(f"{r['unit']}: {r['files']} files, {r['bytes'] / 1e6:.1f} MB -> "
                  f"{r['compact_bytes'] / 1e6:.1f} MB")
    else:
        s = summarize(a.out)
        print(render(s["rows"], s["gate"]))


if __name__ == "__main__":
    main()
