"""Modal app: what a TensorRT-LLM server writes for the governor (client patch 8), on one L4.

Patch 8 was written from the sources of TensorRT-LLM 1.4.0rc3 and run on no server. This
runs it on one, with the engine's own container and the model the T4 runs used, and
answers what the sources could not:

- on a quiet engine, is every active request in the step? (num_requests_running less
  num_scheduled_requests has to be 0, or the window never grows);
- what does the KV cache read once the work is done? (if blocks kept for reuse count
  as used, it reads fuller than it is);
- how often do the gauges change, against how often the engine steps;
- does a governed window move on a burst of short calls, and is the burst faster than
  at the window of 16.

Run from this directory, after `modal setup`:

    modal run trtllm_probe_app.py::check    # CPU only: the image, the CLI, the model
    modal run trtllm_probe_app.py::probe    # one L4, at most 12 minutes

`check` first: it costs cents and finds what would stop the server from starting. `probe`
has a hard timeout, so one launch costs at most 12 minutes of an L4. The weights are in
the volume already (bench_app.py's `prepare`); the GPU container downloads nothing.

`modal app stop sptc-trtllm` kills anything still running.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import warnings
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
# The patched client, next to this repository. This file is imported in the container
# too, at /root, where there is no such place: its sources are at /opt/sptc there, and
# the image's SPTC_HINTS_ROOT says so.
FORK = Path(os.environ.get("SPTC_HINTS_ROOT")
            or (HERE.parents[1] if len(HERE.parents) > 1 else HERE) / "spec-ptc-sptc-hints")

TRTLLM = "1.4.0rc3"
MODEL = "Qwen/Qwen3-1.7B"
VOL_HF, VOL_RESULTS = "/vol/hf", "/vol/results"
PORT = 8000
BASE = f"http://127.0.0.1:{PORT}"
METRICS = BASE + "/prometheus/metrics"
SERVER_LOG = "/tmp/trtllm_server.log"
START_TIMEOUT_S = 7 * 60  # 146 to 245 s in the launches that came up
# in the server's log, these say it will not come up: no reason to wait the timeout out
FATAL = ("MPI_ABORT was invoked", "Error in MPI_", "CUDA out of memory")

hf_vol = modal.Volume.from_name("sptc-hf", create_if_missing=True)
results_vol = modal.Volume.from_name("sptc-results", create_if_missing=True)
VOLUMES = {VOL_HF: hf_vol, VOL_RESULTS: results_vol}

image = (
    # The engine's own container: nothing of it is installed here. Modal's Python is
    # added next to the container's, and runs this file only: the server is started as
    # a process of the container's Python (server_env).
    modal.Image.from_registry(f"nvcr.io/nvidia/tensorrt-llm/release:{TRTLLM}",
                              add_python="3.12")
    .entrypoint([])
    .env({
        "HF_HOME": VOL_HF,
        "HF_HUB_OFFLINE": "1",
        "PYTHONUNBUFFERED": "1",
        "SPTC_HINTS_ROOT": "/opt/sptc/fork",
        "OMPI_ALLOW_RUN_AS_ROOT": "1",
        "OMPI_ALLOW_RUN_AS_ROOT_CONFIRM": "1",
    })
    # the patched client's sources (stdlib only); client_on_path makes them spec_ptc
    .add_local_dir(FORK / "src", "/opt/sptc/fork/src", ignore=["**/__pycache__"])
)

app = modal.App("sptc-trtllm", image=image)


# The server's engine is a process the server spawns with MPI (mpi4py.futures), and the
# server's metrics come from that process only. Each entry: what to add to the
# environment so that the two can reach each other in Modal's sandbox, which has no
# /sys/class/net for UCX to list the network devices from.
MPI_VARIANTS = {
    "default": {},
    "ob1": {"OMPI_MCA_pml": "ob1"},
    "ob1_tcp_lo": {"OMPI_MCA_pml": "ob1", "OMPI_MCA_btl": "self,tcp",
                   "OMPI_MCA_btl_tcp_if_include": "lo"},
    "ob1_sm": {"OMPI_MCA_pml": "ob1", "OMPI_MCA_btl": "self,sm"},
    "ob1_vader": {"OMPI_MCA_pml": "ob1", "OMPI_MCA_btl": "self,vader"},
    "ob1_sm_tcp": {"OMPI_MCA_pml": "ob1", "OMPI_MCA_btl": "self,sm,tcp"},
    "ucx_shm": {"UCX_TLS": "shm,self"},
    "ucx_posix": {"UCX_TLS": "posix,self"},
    "ucx_tcp_lo": {"UCX_TLS": "tcp,self", "UCX_NET_DEVICES": "lo"},
}

def client_on_path() -> None:
    """The patched client, importable as spec_ptc: its package is its src/ directory."""
    shim = Path("/tmp/sptc_shim")
    shim.mkdir(exist_ok=True)
    link = shim / "spec_ptc"
    if not link.exists():
        link.symlink_to(FORK / "src")
    if str(shim) not in sys.path:
        sys.path.insert(0, str(shim))


# --------------------------------------------------------------------------- the server
def serve_script() -> str:
    import shutil

    path = shutil.which("trtllm-serve")
    if path is None:
        raise RuntimeError("no trtllm-serve on PATH in this image")
    return path


def serve_python() -> str:
    """The interpreter trtllm-serve runs in: the first line of the script."""
    first = Path(serve_script()).read_text(errors="replace").splitlines()[0]
    return first[2:].strip().split()[0] if first.startswith("#!") else "python3"


def server_env() -> dict:
    """The container's environment without Modal's Python in it: this file runs in the
    Python Modal added, and its paths must not reach the engine's."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")}
    env["PATH"] = f"{Path(serve_python()).parent}:{env.get('PATH', '')}"
    # The server spawns its engine with MPI. With Open MPI's default, UCX, the two cannot
    # reach each other in Modal's sandbox ("no active messages transport"): the spawned
    # side aborts and the server waits for it for good (the first launch,
    # 20261113-130917). Over shared memory and TCP they can (`mpi`, MPI_VARIANTS).
    # TLLM_WORKER_USE_SINGLE_PROCESS=1 is no way around MPI here: the engine then runs
    # in the server's process and starts, but its per-step records never reach the
    # server, and /prometheus/metrics has no gauge of the engine (the third launch,
    # 20261113-140922).
    env.update(MPI_VARIANTS["ob1_sm_tcp"])
    return env


def model_path() -> str:
    snaps = sorted(Path(VOL_HF, "hub", "models--" + MODEL.replace("/", "--"),
                        "snapshots").glob("*"))
    if not snaps:
        raise RuntimeError(f"{MODEL} is not in the sptc-hf volume (bench_app.py::prepare)")
    return str(snaps[-1])


def _sh(cmd: list[str], timeout: float = 120, env: dict | None = None) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env,
                           check=False)
    except Exception as e:  # noqa: BLE001 - reported, not raised: this is a check
        return f"{type(e).__name__}: {e}"
    return (p.stdout + p.stderr).strip()


def _get(url: str, timeout: float = 5.0) -> str:
    return urllib.request.urlopen(url, timeout=timeout).read().decode()


def _post(path: str, body: dict, timeout: float = 180.0) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def start_server() -> subprocess.Popen:
    cfg = Path("/tmp/trtllm.yaml")
    # /prometheus/metrics is mounted with return_perf_metrics only, and the gauges are
    # written from the engine's per-step records, which enable_iter_perf_stats turns on
    cfg.write_text("return_perf_metrics: true\nenable_iter_perf_stats: true\n")
    cmd = [serve_script(), model_path(), "--host", "127.0.0.1", "--port", str(PORT),
           "--backend", "pytorch", "--max_batch_size", "64", "--config", str(cfg),
           # one frontend, not the default of 8: fewer processes that have to reach
           # each other in the sandbox
           "--num_serve_frontends", "1"]
    log = open(SERVER_LOG, "w")  # noqa: SIM115 - the server writes to it until it is stopped
    return subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=server_env())


def wait_ready(proc: subprocess.Popen) -> float:
    """Seconds until /health answers. Raises if the server ends or takes too long."""
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < START_TIMEOUT_S:
        if proc.poll() is not None:
            raise RuntimeError(f"trtllm-serve ended with code {proc.returncode}")
        log = "\n".join(log_tail(200))
        if any(mark in log for mark in FATAL):
            raise RuntimeError("trtllm-serve's log says it will not start")
        try:
            _get(BASE + "/health", timeout=2.0)
            return time.perf_counter() - t0
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(1.0)
    raise RuntimeError(f"trtllm-serve was not ready after {START_TIMEOUT_S} s")


def log_tail(n: int = 60) -> list[str]:
    try:
        return Path(SERVER_LOG).read_text(errors="replace").splitlines()[-n:]
    except OSError:
        return []


# --------------------------------------------------------------------------- the metrics
ROWS: dict[str, list] = {}  # every sample of a phase, written next to the summary

RAW = ("num_requests_running", "num_requests_waiting", "num_scheduled_requests",
       "num_generation_requests", "num_context_requests", "num_paused_requests",
       "iteration_latency_seconds", "kv_cache_used_blocks", "kv_cache_max_blocks",
       "kv_cache_free_blocks", "kv_cache_tokens_per_block", "kv_cache_utilization",
       "num_requests_completed_total", "generation_tokens_total")


def raw_gauges(text: str) -> dict:
    """The engine's own numbers, summed over their label sets, as it wrote them."""
    out: dict[str, float] = {}
    for line in text.splitlines():
        if not line.startswith("trtllm_"):
            continue
        head, _, value = line.rpartition(" ")
        name = head.split("{", 1)[0][len("trtllm_"):]
        if name in RAW:
            try:
                out[name] = out.get(name, 0.0) + float(value)
            except ValueError:
                pass
    return out


def sample(url: str, parse) -> dict:
    """One read: the engine's numbers, and what the client makes of them."""
    t = time.perf_counter()
    try:
        text = _get(url)
    except Exception as e:  # noqa: BLE001 - recorded
        return {"t": t, "error": f"{type(e).__name__}: {e}"}
    row = {"t": t, **raw_gauges(text)}
    try:
        m = parse(text)
        row["parsed"] = {k: m[k] for k in ("running", "waiting", "kv", "kv_tokens", "paused",
                                           "step_ms") if k in m}
        row["sig"] = hash(m.get("step_sig"))
    except Exception as e:  # noqa: BLE001 - a refused text is a result here
        row["refused"] = str(e)
    return row


def watch(url: str, parse, until, every: float = 0.05) -> list[dict]:
    rows = []
    while not until():
        rows.append(sample(url, parse))
        time.sleep(every)
    return rows


def digest(rows: list[dict]) -> dict:
    """What a phase's samples say about the two things the sources left open."""
    read = [r for r in rows if "error" not in r]
    fresh, last = [], None
    for r in read:  # one row for each step seen
        if "sig" in r and r["sig"] != last:
            fresh.append(r)
        last = r.get("sig", last)
    held = [r.get("num_requests_running", 0.0) - r.get("num_scheduled_requests", 0.0)
            for r in fresh if "num_scheduled_requests" in r]
    span = (read[-1]["t"] - read[0]["t"]) if len(read) > 1 else 0.0
    kv = [r["parsed"]["kv"] for r in read if "kv" in r.get("parsed", {})]
    step_ms = sorted(r["iteration_latency_seconds"] * 1000 for r in fresh
                     if "iteration_latency_seconds" in r)
    return {
        "samples": len(rows), "read": len(read), "refused": sum("refused" in r for r in read),
        "seconds": round(span, 2), "steps_seen": len(fresh),
        "steps_seen_per_s": round(len(fresh) / span, 1) if span else None,
        "held_max": max(held) if held else None,
        "held_nonzero_share": round(sum(h != 0 for h in held) / len(held), 3) if held else None,
        "running_max": max((r.get("num_requests_running", 0.0) for r in read), default=None),
        "scheduled_max": max((r.get("num_scheduled_requests", 0.0) for r in read),
                             default=None),
        "queue_max": max((r.get("num_requests_waiting", 0.0) for r in read), default=None),
        "paused_max": max((r.get("num_paused_requests", 0.0) for r in read), default=None),
        "kv_min": round(min(kv), 4) if kv else None, "kv_max": round(max(kv), 4) if kv else None,
        "kv_last": round(kv[-1], 4) if kv else None,
        "step_ms_median": round(step_ms[len(step_ms) // 2], 2) if step_ms else None,
    }


# --------------------------------------------------------------------------- the phases
def complete(model: str, prompt: str, max_tokens: int) -> int:
    out = _post("/v1/completions", {"model": model, "prompt": prompt,
                                    "max_tokens": max_tokens, "temperature": 0.7})
    return int(out.get("usage", {}).get("completion_tokens", 0))


def quiet_phase(url: str, parse, model: str, n: int) -> dict:
    """A few long calls at once, far below what the engine takes."""
    tokens = [0] * n

    def one(i: int) -> None:
        tokens[i] = complete(model, f"Write a long story about river number {i}.", 256)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    t0 = time.perf_counter()
    for th in threads:
        th.start()
    rows = watch(url, parse, lambda: not any(th.is_alive() for th in threads))
    seconds = time.perf_counter() - t0
    ROWS["quiet"] = rows
    first = next((r["t"] - t0 for r in rows if r.get("num_requests_running", 0) > 0), None)
    return {**digest(rows), "calls": n, "tokens": sum(tokens),
            "tokens_per_s": round(sum(tokens) / seconds, 1),
            "first_sample_with_a_request_s": None if first is None else round(first, 3)}


def idle_phase(url: str, parse, seconds: float = 3.0) -> dict:
    """The engine has nothing to do: what do its gauges say then?"""
    time.sleep(seconds)
    rows = []
    for _ in range(5):
        rows.append(sample(url, parse))
        time.sleep(0.25)
    last = rows[-1]
    return {**digest(rows), "last": {k: last[k] for k in RAW if k in last}}


def burst(url: str | None, model: str, calls: int, tag: str) -> dict:
    """`calls` short calls through the client's launcher: at the window of 16 (url None),
    or with a window that follows the engine at `url`."""
    from spec_ptc.contracts.events import EventBus
    from spec_ptc.contracts.tools import ToolRegistry
    from spec_ptc.speculator import SpecSession

    def llm_query(prompt: str) -> int:
        return complete(model, prompt, 32)

    reg, bus = ToolRegistry(), EventBus()
    tool = reg.register("llm_query", llm_query, speculatable=True, pure=True)
    session = SpecSession(reg, bus, max_dispatches_per_turn=calls + 64,
                          govern=url is not None, load=url)
    budget = session.launcher.budget
    peak = {"in_use": 0}
    done = threading.Event()
    rows: list[dict] = []
    ROWS[f"burst_{tag}"] = rows

    def meter() -> None:
        from spec_ptc.engine.load import parse_metrics

        n = 0
        while not done.wait(0.02):
            peak["in_use"] = max(peak["in_use"], budget.in_use())
            n += 1
            if n % 5 == 0:  # the engine's numbers ten times a second, with the window
                row = sample(METRICS, parse_metrics)
                row["window"], row["in_flight"] = budget.max_inflight, budget.in_use()
                rows.append(row)

    threading.Thread(target=meter, daemon=True).start()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        t0 = time.perf_counter()
        specs = [session.launcher.dispatch(tool, (f"{tag} {i}: name one colour.",), {}, "shadow")
                 for i in range(calls)]
        specs = [s for s in specs if s is not None]  # None: over the turn's cap (not here)
        for s in specs:
            s.done.wait(300)
        seconds = time.perf_counter() - t0
    done.set()
    moves = [{"t": round(e.t - t0, 2), **{k: e.data.get(k) for k in
              ("window", "was", "why", "waiting", "running", "kv", "tax")}}
             for e in bus.history if e.kind == "govern"]
    probe = session.governor.probe if session.governor is not None else None
    seen = digest(rows)
    out = {
        "engine": {k: seen[k] for k in ("steps_seen", "running_max", "scheduled_max",
                                        "queue_max", "paused_max", "kv_max",
                                        "step_ms_median")},
        "calls": calls, "launched": len(specs), "seconds": round(seconds, 2),
        "calls_per_s": round(calls / seconds, 1),
        "failed": sum(s.error is not None for s in specs),
        "errors": sorted({f"{type(s.error).__name__}: {s.error}"[:160]
                          for s in specs if s.error is not None})[:3],
        "peak_in_flight": peak["in_use"], "window_end": budget.max_inflight,
        "window_max": max([m["window"] for m in moves], default=budget.max_inflight),
        "moves": len(moves), "why": sorted({m["why"] for m in moves}),
        "first_moves": moves[:12], "last_moves": moves[-4:],
        "warnings": [str(w.message)[:200] for w in caught][:3],
        "probe": None if probe is None else {"samples": probe.samples, "errors": probe.errors},
    }
    session.close()
    if session.governor is not None:
        session.governor.close()
    return out


# --------------------------------------------------------------------------- functions
@app.function(cpu=2.0, timeout=10 * 60, volumes=VOLUMES, retries=0)
def check() -> dict:
    """No GPU. Is the CLI there, in which Python, and is the model in the volume?"""
    out: dict = {}
    try:
        out["serve_script"], out["serve_python"] = serve_script(), serve_python()
        env = server_env()
        out["serve_help"] = _sh([serve_script(), "--help"], env=env).splitlines()[:6]
        out["version"] = _sh([serve_python(), "-c",
                              "import tensorrt_llm; print(tensorrt_llm.__version__)"],
                             env=env).splitlines()[-3:]
    except Exception as e:  # noqa: BLE001
        out["cli_error"] = f"{type(e).__name__}: {e}"
    try:
        path = model_path()
        out["model_path"] = path
        cfg = json.loads(Path(path, "config.json").read_text())
        out["model"] = {k: cfg.get(k) for k in ("architectures", "num_hidden_layers",
                                                "hidden_size", "torch_dtype")}
    except Exception as e:  # noqa: BLE001
        out["model_error"] = f"{type(e).__name__}: {e}"
    client_on_path()
    try:
        from spec_ptc.engine.load import metrics_url

        out["metrics_url"] = metrics_url(BASE + "/v1", engine="trtllm")
    except Exception as e:  # noqa: BLE001
        out["client_error"] = f"{type(e).__name__}: {e}"
    print(json.dumps(out, indent=1))
    return out


MPI_SPAWN = """
from mpi4py.futures import MPIPoolExecutor
with MPIPoolExecutor(max_workers=1) as ex:
    print("RESULT", ex.submit(pow, 2, 5).result(timeout=40))
"""


@app.function(cpu=4.0, timeout=10 * 60, retries=0)
def mpi() -> dict:
    """No GPU. With which MPI settings does a spawned process answer here?"""
    env = {k: v for k, v in server_env().items() if not k.startswith("OMPI_MCA_")}
    out: dict = {
        "ompi": _sh(["ompi_info", "--version"], env=env).splitlines()[:1],
        "components": [ln.strip()[:70] for ln in _sh(["ompi_info"], env=env).splitlines()
                       if ln.strip().startswith(("MCA pml:", "MCA btl:"))],
        "ucx": _sh(["ucx_info", "-v"], env=env).splitlines()[:1],
        "net": _sh(["sh", "-c", "ls /sys/class/net 2>&1; cat /proc/net/dev 2>&1 | tail -3"]),
        "variants": {},
    }

    def one(name: str) -> None:
        text = _sh([serve_python(), "-c", MPI_SPAWN], timeout=75,
                   env={**env, **MPI_VARIANTS[name]})
        lines = [ln for ln in text.splitlines() if ln.strip()]
        out["variants"][name] = {"works": "RESULT 32" in text, "tail": lines[-2:]}

    threads = [threading.Thread(target=one, args=(n,)) for n in MPI_VARIANTS]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    out["working"] = [n for n in MPI_VARIANTS if out["variants"].get(n, {}).get("works")]
    print(json.dumps(out, indent=1))
    return out


@app.function(gpu="L4", cpu=4.0, memory=16384, timeout=12 * 60, volumes=VOLUMES, retries=0)
def probe(calls: int = 300, quiet: int = 4, client: str = "") -> dict:
    client_on_path()
    from spec_ptc.engine.load import metrics_url, parse_metrics

    url = metrics_url(BASE + "/v1", engine="trtllm")
    out: dict = {"trtllm": TRTLLM, "model": MODEL, "client": client, "gpu": _sh(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])}
    run = time.strftime("%Y%m%d-%H%M%S")
    dst = Path(VOL_RESULTS, "trtllm_probe", run)
    dst.mkdir(parents=True, exist_ok=True)
    proc = start_server()
    try:
        out["ready_s"] = round(wait_ready(proc), 1)
        model = json.loads(_get(BASE + "/v1/models"))["data"][0]["id"]
        first = _get(url)
        (dst / "metrics_before_any_request.txt").write_text(first)
        out["before_any_request"] = sample(url, parse_metrics)
        complete(model, "Say hello.", 8)  # the first call compiles what it needs
        out["quiet"] = quiet_phase(url, parse_metrics, model, quiet)
        out["idle_after_quiet"] = idle_phase(url, parse_metrics)
        out["burst_at_16"] = burst(None, model, calls, "a")
        out["burst_governed"] = burst(url, model, calls, "b")
        out["idle_after_bursts"] = idle_phase(url, parse_metrics)
        (dst / "metrics_after.txt").write_text(_get(url))
        held, idle_kv = out["quiet"]["held_max"], out["idle_after_bursts"]["kv_last"]
        out["verdicts"] = {
            # None: the engine's gauges were never read, and nothing is known
            "gauges_read": out["quiet"]["steps_seen"] > 0,
            # the window can grow: nothing is held on an engine with room
            "quiet_engine_holds_nothing": None if held is None else held == 0,
            # blocks kept for reuse are not counted as used: an idle cache reads low
            "idle_kv_cache_reads_low": None if idle_kv is None else idle_kv < 0.5,
            "window_grew": out["burst_governed"]["window_max"] > 16,
            "governed_faster_than_16": (out["burst_governed"]["seconds"]
                                        < out["burst_at_16"]["seconds"]),
        }
    except Exception as e:  # noqa: BLE001 - what went wrong is the result
        out["error"] = f"{type(e).__name__}: {e}"
        out["server_log_tail"] = log_tail()
    finally:
        proc.terminate()
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
        (dst / "server.log").write_text("\n".join(log_tail(400)))
        (dst / "samples.json").write_text(json.dumps(ROWS, default=str))
        (dst / "summary.json").write_text(json.dumps(out, indent=1, default=str))
        results_vol.commit()
    out["saved"] = f"sptc-results:trtllm_probe/{run}"
    print(json.dumps(out, indent=1, default=str))
    return out
