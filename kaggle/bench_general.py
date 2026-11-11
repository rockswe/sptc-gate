"""Real-vLLM client for a workload that is not code-mode sPTC: ReAct agents with
prediction-based speculation (sptc_sim/general.py, workload (a)), optionally next to
background batch jobs (workload (c)). Same server and arm mechanics as vllm_bench.py:
the OpenAI-compatible streaming completions API, raw prompts, ignore_eos so every call
has a fixed length, tags in `vllm_xargs`. Standard library only (no openai package).

  python kaggle/bench_general.py react    --base-url URL --model M --out DIR --arm ARM
         [--modes none,action,next] [--agents 1,4,8] [--sessions 3] [--batch-workers 0]
  python kaggle/bench_general.py matrix   --model M --out DIR [--quick]  # serve per arm
  python kaggle/bench_general.py estimate [--quick]                      # GPU minutes

Arms (one vLLM server each; matrix starts and stops them):
  fcfs      stock vLLM, speculative calls untagged
  priority  stock vLLM --scheduling-policy priority; speculative calls priority 1
  plugin    the sptc_vllm plugin; speculative calls tagged {"sptc_class": "bet"}

A session: `steps` LLM calls (thought + action) with a sleeping tool between them; the
context grows by each output and a ~300-token observation. Output lengths, tool times
and which steps a guess is right come from react_plan(), the simulator's own draw.
  none     no speculation
  action   k=3 short (8-token) candidate calls with each step's call; a right first
           candidate starts the tool when it finishes (SPAgent's setting, 40% hits)
  next     during the tool, a guess of the next step's full call on a guessed
           observation; a right guess (27.8%, PASTE's top-1) is kept as that call
  next3    three such guesses, 43.9% (PASTE's top-3)
A kept guess with no token for stall_s seconds is cancelled and re-issued untagged;
so is a guess the server refused (plugin: no finish_reason, or "abort").
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import os
import shlex
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

FILLER = ("The quarterly report covers revenue, latency, safety and quality across all "
          "regions, with per-item notes on cloud spend and energy use. ")
FILLER_TOKENS = 26  # Qwen3 tokenizer: 107 copies + tag = 2804 tokens (kaggle_t4 calib.json)

# the simulator's ReactCfg defaults and REACT_MODES (sptc_sim/general.py); a test
# checks that react_plan() below draws exactly the simulator's plan
BASE = dict(steps=6, sys_prompt=1200, step_out=120.0, answer_out=80.0, obs_tokens=300,
            out_sigma=0.3, tool_p50=1.5, tool_p99=6.0, k=3, hit=0.40, cand_out=8,
            cand_suffix=60, stall_s=1.0)
MODES = {"none": dict(mode="none"), "action": dict(mode="action", k=3, hit=0.40),
         "next": dict(mode="next", k=1, hit=0.278), "next3": dict(mode="next", k=3, hit=0.439)}
BET_EXTRA = {"fcfs": {}, "priority": {"priority": 1},
             "plugin": {"vllm_xargs": {"sptc_class": "bet"}}}
BATCH = dict(prompt=1500, out=250.0, out_sigma=0.3, backoff=1.0)
BATCH_TAG = {"fcfs": "normal", "priority": "low", "plugin": "bet"}

MODEL = "Qwen/Qwen3-1.7B"
SERVE = ["vllm", "serve", "{model}", "--dtype", "half", "--max-model-len", "8192",
         "--gpu-memory-utilization", "0.90", "--port", "{port}"]  # as sptc_kaggle.ipynb
# server flags: vllm_bench.py's SERVERS, the one definition of each setup (the plugin
# with free_window 8, kv_reserve 0.10, a fixed 512-token prefill allowance; stock and
# priority with the same --additional-config, so all three run one compiled artifact)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vllm_bench import HOST_CPU_MAX, HOST_SAT_MAX, SERVERS, GpuLog, HostCpu  # noqa: E402

ARM_FLAGS = {"fcfs": SERVERS["fcfs"]["flags"], "priority": SERVERS["priority"]["flags"],
             "plugin": SERVERS["plugin"]["flags"]}
# QUICK is a subset of FULL's cells (same sessions), so pre-registered claims 1, 3 and 5
# (results/general/predictions.json, "quick_claims") apply to it unchanged
QUICK = dict(modes="none,next3", agents="8", sessions=3, batch=False)
FULL = dict(modes="none,action,next,next3", agents="1,4,8,16", sessions=3, batch=True)


# ----------------------------------------------------------------------------- plan
def _u01(*parts) -> float:  # = sptc_sim.agent._u01
    h = hashlib.sha1(repr(parts).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def _normal(*parts) -> float:  # = sptc_sim.agent._normal
    u1 = max(_u01(*parts, "a"), 1e-12)
    u2 = _u01(*parts, "b")
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def _len(mean: float, sigma: float, *key) -> int:
    mu = math.log(max(mean, 1.0)) - sigma ** 2 / 2
    return max(1, int(round(math.exp(mu + sigma * _normal(*key)))))


def cfg_for(mode: str) -> dict:
    return {**BASE, **MODES[mode]}


def react_plan(cfg: dict, seed: int, sid: int) -> list[tuple[int, float, bool]]:
    """Per step: (output tokens, tool seconds, guess right) = sptc_sim.general.react_plan."""
    sigma = math.log(cfg["tool_p99"] / cfg["tool_p50"]) / 2.326
    out = []
    for i in range(cfg["steps"]):
        mean = cfg["answer_out"] if i == cfg["steps"] - 1 else cfg["step_out"]
        n = _len(mean, cfg["out_sigma"], seed, sid, i, "out")
        tool = cfg["tool_p50"] * math.exp(sigma * _normal(seed, sid, i, "tool"))
        out.append((n, tool, _u01(seed, sid, i, "hit") < cfg["hit"]))
    return out


def filler(tokens: int, tag: str) -> str:
    return f"[{tag}] " + FILLER * max(1, round(tokens / FILLER_TOKENS))


# ----------------------------------------------------------------------------- calls
class Stream:
    """One streamed raw completion in its own thread: per-token arrival times, the
    text, and the finish reason. cancel() closes the socket (vLLM aborts the request
    when the client disconnects)."""

    def __init__(self, base_url: str, model: str, prompt: str, max_tokens: int,
                 extra: dict | None = None, role: str = "root") -> None:
        self.url = urllib.parse.urlparse(base_url.rstrip("/") + "/completions")
        self.body = {"model": model, "prompt": prompt, "max_tokens": max_tokens,
                     "temperature": 0.0, "stream": True, "ignore_eos": True, "logprobs": 0,
                     "stream_options": {"include_usage": True}, **(extra or {})}
        self.max_tokens, self.role = max_tokens, role
        self.times: list[float] = []  # absolute perf_counter times, one per token
        self.parts: list[str] = []
        self.finish = self.stop_reason = self.usage = None
        self.cancelled = False
        self.claimed = role == "root"
        self.done = threading.Event()
        self._conn = None
        self.t0 = time.perf_counter()
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()

    def _run(self) -> None:
        try:
            conn = http.client.HTTPConnection(self.url.hostname, self.url.port or 80,
                                              timeout=900)
            self._conn = conn
            if self.cancelled:
                return
            conn.request("POST", self.url.path, json.dumps(self.body),
                         {"Content-Type": "application/json"})
            resp = conn.getresponse()
            if self.cancelled:
                return
            if resp.status != 200:
                self.finish = f"error: HTTP {resp.status} {resp.read()[:200]!r}"
                return
            for raw in resp:
                if self.cancelled:
                    break
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                ch = json.loads(data)
                now = time.perf_counter()
                for c in ch.get("choices") or []:
                    text = c.get("text") or ""
                    toks = (c.get("logprobs") or {}).get("tokens")
                    n = len(toks) if toks else (1 if text else 0)
                    self.times.extend([now] * n)
                    self.parts.append(text)
                    if c.get("finish_reason"):
                        self.finish = c["finish_reason"]
                        self.stop_reason = c.get("stop_reason")
                if ch.get("usage"):
                    self.usage = ch["usage"]
        except Exception as e:  # noqa: BLE001 - cancel or a refused request
            if not self.cancelled:
                self.finish = f"error: {type(e).__name__}: {e}"[:200]
        finally:
            if self.cancelled and self.finish is None:
                self.finish = "client_abort"
            self.t_end = time.perf_counter()
            self.done.set()
            try:
                if self._conn is not None:
                    self._conn.close()
            except Exception:  # noqa: BLE001
                pass

    def cancel(self) -> None:
        if self.done.is_set() or self.cancelled:
            return
        self.cancelled = True
        conn = self._conn
        if conn is not None and conn.sock is not None:
            try:
                import socket

                conn.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    @property
    def text(self) -> str:
        return "".join(self.parts)

    @property
    def ok(self) -> bool:
        return self.done.is_set() and self.finish in ("length", "stop") and bool(self.times)

    @property
    def refused(self) -> bool:
        """The plugin's rule (integrations/README.md): a tagged call whose finish_reason
        is "abort" or missing was refused. Only meaningful once done."""
        return self.done.is_set() and not self.cancelled and (
            self.finish is None or str(self.finish).startswith(("abort", "error")))

    @property
    def tpot(self) -> float | None:
        t = self.times
        return (t[-1] - t[0]) / (len(t) - 1) if len(t) > 1 else None


def keep(s: Stream, stall_s: float) -> bool:
    """Wait for a kept guess; give up (cancel) if it stalls for stall_s or was refused."""
    t_claim = time.perf_counter()
    while not s.done.wait(0.02):
        last = s.times[-1] if s.times else t_claim
        if time.perf_counter() - max(t_claim, last) >= stall_s:
            s.cancel()
            s.done.wait()
            return False
    return s.ok


def sleep_until(t: float) -> None:
    dt = t - time.perf_counter()
    if dt > 0:
        time.sleep(dt)


# ----------------------------------------------------------------------------- session
def react_session(a, arm: str, mode: str, sid: int, seed: int = 0) -> dict:
    cfg = cfg_for(mode)
    plan = react_plan(cfg, seed, sid)
    bet = BET_EXTRA[arm]
    tag = f"{a.run_id} {arm} {mode} s{sid}"
    ctx = filler(cfg["sys_prompt"], f"agent {tag}") + "\nQuestion: answer step by step.\n"
    calls: list[Stream] = []
    roots: list[Stream] = []
    rec = {"sid": sid, "hits": 0, "used": 0, "stalled": 0}
    carried: Stream | None = None
    t0 = time.perf_counter()

    def start(prompt, n, extra, role):
        s = Stream(a.base_url, a.model, prompt, n, extra, role)
        calls.append(s)
        return s

    for i, (out, tool_s, hit) in enumerate(plan):
        last = i == len(plan) - 1
        root = None
        if carried is not None:
            if keep(carried, cfg["stall_s"]):
                root = carried
                rec["used"] += 1
            elif carried.cancelled:
                rec["stalled"] += 1
                carried.claimed = False
            else:
                carried.claimed = False
            carried = None
        cands: list[Stream] = []
        if root is None:
            root = start(ctx, out, {}, "root")
            if cfg["mode"] == "action" and not last:
                cands = [start(ctx + f"\n[candidate {j}] " + filler(cfg["cand_suffix"], "next "
                                                                     "action?"),
                               cfg["cand_out"], bet, "bet") for j in range(cfg["k"])]
            root.done.wait()
        roots.append(root)
        ctx += root.text
        if last:
            break
        t_tool = time.perf_counter()
        rec["hits"] += hit and cfg["mode"] != "none"
        for j, c in enumerate(cands):
            if hit and j == 0 and c.done.is_set() and c.ok:
                c.claimed = True  # the guessed action's tool started when it finished
                t_tool = min(t_tool, c.t_end)
                rec["used"] += 1
            c.cancel()
        obs = "\nObservation: " + filler(cfg["obs_tokens"], f"obs {tag} {i}") + "\n"
        if cfg["mode"] == "next":
            nxt = plan[i + 1][0]
            guesses = [start(ctx + (obs if hit and j == 0 else
                                    "\nObservation: " + filler(cfg["obs_tokens"],
                                                               f"guess {tag} {i} {j}") + "\n"),
                             nxt, bet, "bet") for j in range(cfg["k"])]
            sleep_until(t_tool + tool_s)
            for j, g in enumerate(guesses):
                if hit and j == 0 and not g.refused:
                    g.claimed = True
                    carried = g
                else:
                    g.cancel()
        else:
            sleep_until(t_tool + tool_s)
        ctx += obs
    rec["latency"] = time.perf_counter() - t0
    for c in calls:
        c.done.wait(30)
    bets = [c for c in calls if c.role == "bet"]
    rec.update(
        root_tpot=[r.tpot for r in roots if r.tpot is not None],
        bets=len(bets),
        rejected=sum(c.refused and not c.times for c in bets),
        dropped=sum(c.refused and bool(c.times) for c in bets),
        tokens=sum(len(c.times) for c in calls),
        wasted_tokens=sum(len(c.times) for c in calls if not c.claimed),
        finishes=sorted({str(c.finish) for c in calls}),
    )
    return rec


def batch_worker(a, arm: str, wid: int, stop: threading.Event, stats: dict, lock) -> None:
    """Background jobs back to back until stop: workload (c). On a refused bet the
    worker backs off and retries as a bet."""
    tag = BATCH_TAG[arm]
    extra = BET_EXTRA[arm] if tag in ("low", "bet") else {}
    j = 0
    while not stop.is_set():
        n = _len(BATCH["out"], BATCH["out_sigma"], 0, wid, j, "bg")
        prompt = filler(BATCH["prompt"], f"batch {a.run_id} {arm} {wid} {j}") + "\nSummarize."
        while not stop.is_set():
            s = Stream(a.base_url, a.model, prompt, n, extra, "batch")
            while not s.done.wait(0.1):
                if stop.is_set():
                    s.cancel()
            s.done.wait()
            if s.cancelled:
                return  # cut off by the end of the cell, not refused
            with lock:
                if s.ok:
                    stats["jobs"] += 1
                    stats["tokens"] += len(s.times)
                    break
                stats["refused"] += s.refused
                stats["lost_tokens"] += len(s.times)
            if not stop.wait(BATCH["backoff"]):
                continue
        j += 1


def pctl(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return xs[min(len(xs) - 1, max(0, math.ceil(q / 100 * len(xs)) - 1))]


def run_cell(a, arm: str, mode: str, agents: int, sessions: int, batch_workers: int = 0
             ) -> dict:
    """`agents` closed-loop agents, each running `sessions` sessions back to back
    (session id = agent * 1000 + j, the simulator's numbering for the predictions)."""
    recs: list[dict] = []
    lock = threading.Lock()
    stop = threading.Event()
    stats = {"jobs": 0, "tokens": 0, "refused": 0, "lost_tokens": 0}
    bws = [threading.Thread(target=batch_worker, args=(a, arm, w, stop, stats, lock),
                            daemon=True) for w in range(batch_workers)]
    for t in bws:
        t.start()

    def agent(i):
        for j in range(sessions):
            r = react_session(a, arm, mode, i * 1000 + j)
            with lock:
                recs.append(r)

    # whole-host CPU (the clients share the 4-vCPU host with vLLM) and GPU clocks
    cpu, gpu, done = HostCpu(), GpuLog(), threading.Event()

    def watch():
        k = 0
        while True:
            cpu.sample()
            if k % 5 == 0:
                gpu.sample()
            k += 1
            if done.wait(1.0):
                cpu.sample()
                return

    mon = threading.Thread(target=watch, daemon=True)
    mon.start()
    t0 = time.perf_counter()
    ths = [threading.Thread(target=agent, args=(i,)) for i in range(agents)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    wall = time.perf_counter() - t0
    done.set()
    mon.join(10)
    stop.set()
    for t in bws:
        t.join(60)
    lat = [r["latency"] for r in recs]
    tp = [x for r in recs for x in r["root_tpot"]]
    tok = sum(r["tokens"] for r in recs)
    row = {"arm": arm, "mode": mode, "agents": agents, "sessions": len(recs),
           "batch_workers": batch_workers, "wall_s": wall,
           "lat_p50": statistics.median(lat), "lat_p99": pctl(lat, 99),
           "lat_mean": statistics.mean(lat),
           "root_tpot_p50_ms": 1000 * statistics.median(tp) if tp else None,
           "root_tpot_p99_ms": 1000 * pctl(tp, 99) if tp else None,
           "bets": sum(r["bets"] for r in recs), "hits": sum(r["hits"] for r in recs),
           "used": sum(r["used"] for r in recs), "stalled": sum(r["stalled"] for r in recs),
           "rejected": sum(r["rejected"] for r in recs),
           "dropped": sum(r["dropped"] for r in recs),
           "wasted_token_frac": sum(r["wasted_tokens"] for r in recs) / tok if tok else 0.0,
           "finishes": sorted({f for r in recs for f in r["finishes"]}),
           **cpu.result(), "gpu": gpu.result()}
    if row["host_cpu_util"] is not None:  # vllm_bench's validity rule; None off Linux
        row["cpu_ok"] = (row["host_cpu_util"] < HOST_CPU_MAX
                         and (row["host_cpu_sat_frac"] or 0.0) < HOST_SAT_MAX)
    if batch_workers:
        row.update(batch_jobs_s=stats["jobs"] / wall, batch_tok_s=stats["tokens"] / wall,
                   batch_refused=stats["refused"], batch_lost_tokens=stats["lost_tokens"])
    return row


def react(a) -> dict:
    rows = []
    for agents in [int(x) for x in a.agents.split(",")]:
        for mode in a.modes.split(","):
            row = run_cell(a, a.arm, mode, agents, a.sessions)
            rows.append(row)
            print(json.dumps(row), flush=True)
        if a.batch_workers:
            row = run_cell(a, a.arm, "none", agents, a.sessions, a.batch_workers)
            rows.append(row)
            print(json.dumps(row), flush=True)
    return {"react": rows}


# ----------------------------------------------------------------------------- servers
def answers(base_url: str) -> bool:
    try:
        urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=2)
        return True
    except Exception:  # noqa: BLE001
        return False


def start_server(cmd: list[str], base_url: str, log: Path, env: dict | None = None,
                 wait_s: float = 1200):
    if answers(base_url):  # e.g. left over by a timed-out start: its config is not ours
        raise RuntimeError(f"a server already answers at {base_url}: stop it first "
                           "(pkill -f 'vllm serve'); not launching over it")
    p = subprocess.Popen(cmd, stdout=open(log, "a"), stderr=subprocess.STDOUT,
                         env={**os.environ, **(env or {})})
    t0 = time.time()
    while time.time() - t0 < wait_s:
        try:
            urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=2)
            return p
        except Exception:  # noqa: BLE001
            if p.poll() is not None:
                raise RuntimeError(log.read_text()[-3000:]) from None
            time.sleep(1)
    stop_server(p, 0)
    raise TimeoutError(f"server not up after {wait_s} s")


def stop_server(p, settle_s: float = 10) -> None:
    p.terminate()
    try:
        p.wait(timeout=120)
    except subprocess.TimeoutExpired:
        p.kill()
    time.sleep(settle_s)  # let the GPU memory go


def matrix(a) -> dict:
    size = QUICK if a.quick else FULL
    a.modes = a.modes or size["modes"]
    a.agents = a.agents or size["agents"]
    a.sessions = a.sessions or size["sessions"]
    batch = a.batch_workers if a.batch_workers is not None else (16 if size["batch"] else 0)
    out = Path(a.out)
    integ = str(Path(__file__).resolve().parents[1] / "integrations")
    # resume: cells of an earlier, interrupted matrix in the same --out are kept, not rerun
    part = out / "general_partial.json"
    rows = json.loads(part.read_text())["react"] if part.exists() else []
    done = {(r["arm"], r["mode"], r["agents"], r["batch_workers"]) for r in rows}
    loads = [int(x) for x in a.agents.split(",")]
    for arm in a.arms.split(","):
        cells = [(mode, n, 0) for n in loads for mode in a.modes.split(",")]
        cells += [("none", 4, batch)] if batch else []
        todo = [c for c in cells if (arm, *c) not in done]
        if not todo:
            print("already done:", arm, flush=True)
            continue
        tmpl = shlex.split(a.serve_cmd) if a.serve_cmd else SERVE
        cmd = [x.format(model=a.model, port=a.port) for x in tmpl] + ARM_FLAGS[arm]
        env = {"PYTHONPATH": integ + os.pathsep + os.environ.get("PYTHONPATH", "")}
        print("serving", arm, " ".join(cmd), flush=True)
        try:
            p = start_server(cmd, a.base_url, out / f"vllm_general_{arm}.log", env)
        except (RuntimeError, TimeoutError) as e:  # go on with the next arm; rerun to retry
            print(f"SERVER FAILED for {arm}, skipping it: {str(e)[-2000:]}", flush=True)
            continue
        try:
            a.arm = arm
            # warm-up: one short call, so the first cell does not pay compile/caches
            Stream(a.base_url, a.model, "Say hi.", 4).done.wait(300)
            for mode, agents, workers in todo:
                row = run_cell(a, arm, mode, agents, a.sessions, workers)
                rows.append(row)
                print(json.dumps(row), flush=True)
                tmp = part.with_suffix(".tmp")  # after every cell, atomically
                tmp.write_text(json.dumps({"react": rows}, indent=1))
                os.replace(tmp, part)
        finally:
            stop_server(p, a.settle_s)
    return {"react": rows}


def estimate(a) -> dict:
    """GPU minutes: session time from the simulator's predictions where present."""
    size = QUICK if a.quick else FULL
    pred = Path(__file__).resolve().parents[1] / "results" / "general" / "predictions.json"
    lat = {}
    if pred.exists():
        for r in json.loads(pred.read_text())["quick_cells" if a.quick else "cells"]:
            lat[(r["arm"], r["mode"], r["agents"], r.get("batch_workers", 0))] = r["lat_mean"]
    total, n_arms = 0.0, len(a.arms.split(","))
    for arm in a.arms.split(","):
        for agents in [int(x) for x in size["agents"].split(",")]:
            for mode in size["modes"].split(","):
                total += size["sessions"] * lat.get((arm, mode, agents, 0), 40.0)
        if size["batch"]:
            total += size["sessions"] * lat.get((arm, "none", 4, 16), 60.0)
    startup = 4.0 * 60 * n_arms  # vllm serve with CUDA graphs on a T4, plus settle
    res = {"quick": a.quick, "bench_min": total / 60, "startup_min": startup / 60,
           "gpu_min": (total + startup) / 60, "from_predictions": bool(lat)}
    print(json.dumps(res))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["react", "matrix", "estimate"])
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--out", default="kaggle_out")
    ap.add_argument("--arm", default="fcfs", choices=sorted(BET_EXTRA))
    ap.add_argument("--arms", default="fcfs,priority,plugin")
    ap.add_argument("--modes", default="")
    ap.add_argument("--agents", default="")
    ap.add_argument("--sessions", type=int, default=0)
    ap.add_argument("--batch-workers", type=int, default=None)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--serve-cmd", default="", help="override `vllm serve` (tests); the arm's "
                    "flags are appended")
    ap.add_argument("--settle-s", type=float, default=10.0)
    a = ap.parse_args()
    a.run_id = f"r{time.time_ns() % 10**9}"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "react":
        size = QUICK if a.quick else FULL
        a.modes = a.modes or size["modes"]
        a.agents = a.agents or size["agents"]
        a.sessions = a.sessions or size["sessions"]
        a.batch_workers = a.batch_workers or 0
    res = {"react": react, "matrix": matrix, "estimate": estimate}[a.cmd](a)
    name = {"react": f"general_{a.arm}", "matrix": "general",
            "estimate": "general_estimate" + ("_quick" if a.quick else "")}
    (out / f"{name[a.cmd]}.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
