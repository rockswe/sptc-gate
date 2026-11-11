"""Modal app: the replay campaign on one GPU.

Run from this directory. The corpus holds OOLONG text: it goes to the private results
volume, never into the image or the repository.

    modal volume put sptc-results ../../_modal_runs/replay/corpus replay/corpus
    modal run replay_app.py::probe_handler                 # CPU: rlms' LM handler under a burst
    modal run --detach replay_app.py::smoke                # T4, ~15 min: the plumbing on a real vLLM
    SPTC_REPLAY_TIMEOUT_MIN=110 modal run --detach replay_app.py::replay   # PREREG_REPLAY.md's design
    modal volume get sptc-results replay/<run> ../../_modal_runs/replay/

- **Clients.** `/opt/spec-ptc` is spec-ptc as checked out locally (9b78b7d, the
  client the campaign measured); `/opt/spec-ptc-fork` is the sptc-hints fork's working
  tree. Neither is pip-installed: each unit's process puts its arm's tree on its path
  (replay_campaign.py). The commits and whether the trees were clean are recorded at
  launch (`launch.json`).
- **Limits:** `--max-minutes`
  stops before a unit that would pass it; SPTC_REPLAY_TIMEOUT_MIN (default 120) is the
  function's hard timeout. Results are committed to the volume after every unit and every
  two minutes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
SMOKE_MODEL = "Qwen/Qwen3-1.7B"
VOL_HF, VOL_CACHE, VOL_RESULTS = "/vol/hf", "/vol/vllm-cache", "/vol/results"
TIMEOUT_MIN = int(os.environ.get("SPTC_REPLAY_TIMEOUT_MIN", "120"))
IGNORE = [".git", "**/.git", "media", "**/__pycache__", ".venv*", "*.egg-info", ".pytest_cache",
          ".ruff_cache", "uv.lock"]

hf_vol = modal.Volume.from_name("sptc-hf", create_if_missing=True)
cache_vol = modal.Volume.from_name("sptc-vllm-cache", create_if_missing=True)
results_vol = modal.Volume.from_name("sptc-results", create_if_missing=True)
VOLUMES = {VOL_HF: hf_vol, VOL_CACHE: cache_vol, VOL_RESULTS: results_vol}


def _git(root: Path) -> dict:
    def run(*a):
        return subprocess.run(["git", "-C", str(root), *a], capture_output=True,
                              text=True).stdout.strip()

    return {"path": str(root), "commit": run("rev-parse", "HEAD"),
            "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": [x for x in run("status", "--porcelain").splitlines() if x][:20]}


image = (
    modal.Image.from_registry("nvidia/cuda:13.0.2-devel-ubuntu24.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install("vllm==0.32.0", "rlms==0.1.3", "datasets", "huggingface_hub", "psutil")
    .env({"HF_HOME": VOL_HF, "VLLM_CACHE_ROOT": VOL_CACHE, "PYTHONUNBUFFERED": "1"})
)
LAUNCH: dict = {}
if modal.is_local():
    STOCK = Path(os.environ.get("SPEC_PTC_ROOT") or HERE.parents[1] / "spec-ptc")
    FORK = Path(os.environ.get("SPTC_HINTS_ROOT") or HERE.parents[1] / "spec-ptc-sptc-hints")
    LAUNCH = {"stock": _git(STOCK), "fork": _git(FORK), "cloud": _git(HERE.parent)}
    image = (
        image
        # which commits these trees are, and whether they were clean: read by the functions
        .env({"SPTC_LAUNCH": json.dumps(LAUNCH)})
        .add_local_dir(STOCK, "/opt/spec-ptc", copy=True, ignore=IGNORE)
        .add_local_dir(FORK, "/opt/spec-ptc-fork", copy=True, ignore=IGNORE)
        .add_local_dir(HERE, "/opt/cloud", ignore=["tests", "**/__pycache__", ".pytest_cache",
                                                   ".ruff_cache"])
    )

app = modal.App("sptc-replay", image=image)
TREES = "stock=/opt/spec-ptc,fork=/opt/spec-ptc-fork"


def _committer(stop: threading.Event, every: float = 120.0) -> None:
    while not stop.wait(every):
        try:
            results_vol.commit()
        except Exception as e:  # noqa: BLE001 - the next tick tries again
            print(f"volume commit failed: {e}", flush=True)


def _campaign(out: Path, argv: list[str], launch: str) -> str:
    sys.path.insert(0, "/opt/cloud")
    import replay_campaign

    out.mkdir(parents=True, exist_ok=True)
    launch = launch or os.environ.get("SPTC_LAUNCH", "")
    if launch:
        (out / "launch.json").write_text(launch)
    args = replay_campaign.parser().parse_args(argv)
    args.on_unit_done = lambda _u: results_vol.commit()
    print("argv", argv, flush=True)
    stop = threading.Event()
    threading.Thread(target=_committer, args=(stop,), daemon=True).start()
    try:
        replay_campaign.run_campaign(args)
    finally:
        stop.set()
        for v in (cache_vol, results_vol):
            v.commit()
    md = out / "summary.md"
    text = md.read_text() if md.exists() else "no summary"
    print(text, flush=True)
    return text


# PREREG_REPLAY.md's design: the 8 sessions, the four arms twice, the two controls once
SESSIONS = ("pairs32k-15,pairs32k-1,pairs32k-20,trec132k-17000222,trec132k-17000232,"
            "trec132k-17000241,trec132k-17000222.w8k-c8,trec132k-17000232.w8k-c1")


@app.function(gpu="H100", cpu=8.0, timeout=TIMEOUT_MIN * 60, volumes=VOLUMES, retries=0)
def replay(run: str = "", arms: str = "nospec,stream,scout,wide",
           once: str = "wide-threads,nospec-wide", repeats: int = 2, conc: int = 8,
           sessions: str = SESSIONS, corpus: str = "replay/corpus", max_minutes: float = 95,
           unit_estimate_min: float = 10, unit_timeout_min: float = 30,
           serve_extra: str = "--max-model-len 65536", warmup_passes: int = 2,
           handler_backlog: int = 1024, launch: str = "", units: str = "",
           warm_arm: str = "", design_file: str = "", estimates: str = "",
           extra_units: str = "", extra_sessions: str = "", warm_sessions: str = "") -> str:
    """Start vLLM with the campaign's flags once, then every unit against it. The defaults are the
    pre-registered design of PREREG_REPLAY.md. PREREG_RECORD.md's replay gives `units`,
    `warm_arm`, `design_file` (a file of this directory), `estimates`, and its own `corpus`
    and `sessions`; PREREG_GOVERN.md's also `warm_sessions`."""
    os.environ["HF_HUB_OFFLINE"] = "1"  # weights come from app.py::prepare
    run = run or f"{time.strftime('%Y%m%d-%H%M%S')}-replay"
    out = Path(VOL_RESULTS, "replay", run)
    argv = ["run", "--out", str(out), "--corpus", str(Path(VOL_RESULTS, corpus)),
            "--arms", arms, "--once", once, "--repeats", str(repeats), "--conc", str(conc),
            "--trees", TREES, "--model", MODEL, "--launch", "--start-timeout", "1200",
            "--max-minutes", str(max_minutes), "--unit-estimate-min", str(unit_estimate_min),
            "--unit-timeout-min", str(unit_timeout_min), "--warmup-passes", str(warmup_passes),
            "--handler-backlog", str(handler_backlog)]
    if sessions:
        argv += ["--sessions", sessions]
    if serve_extra:
        argv += [f"--serve-extra={serve_extra}"]
    if units:
        argv += ["--units", units]
    if warm_arm:
        argv += ["--warm-arm", warm_arm]
    if design_file:
        argv += ["--design-file", str(Path("/opt/cloud", design_file))]
    if estimates:
        argv += ["--estimates", estimates]
    if extra_units:
        argv += ["--extra-units", extra_units]
    if extra_sessions:
        argv += ["--extra-sessions", extra_sessions]
    if warm_sessions:
        argv += ["--warm-sessions", warm_sessions]
    return _campaign(out, argv, launch)


@app.function(gpu="T4", cpu=8.0, timeout=int(os.environ.get("SPTC_T4_TIMEOUT_MIN", "45")) * 60,
              volumes=VOLUMES, retries=0)
def small(run: str = "", units: str = "stream:1,wide:1,auto:1", warm_arm: str = "auto",
          sessions: str = "", warm_sessions: str = "", conc: int = 8,
          corpus: str = "replay/corpus_fix", max_minutes: float = 35,
          serve_extra: str = "--max-model-len 32768 --dtype half --max-num-seqs 16",
          eager: bool = True, design_file: str = "", estimates: str = "",
          handler_backlog: int = 1024, unit_timeout_min: float = 12,
          launch: str = "") -> str:
    """A small engine for the limits that follow the load (PREREG_GOVERN.md): a 1.7B model
    on a T4, started with few places in its batch (`--max-num-seqs`), so that a window the
    H100 took without noticing is more than this engine can admit. The same client code as
    on the H100; what differs is what the engine reports.

    `eager=False` starts vLLM with CUDA graphs, as a production server would run."""
    sys.path.insert(0, "/opt/cloud")
    import rlm_campaign

    # a T4 cannot run the H100's server flags (flash-attn backend, 0.92 of the memory)
    rlm_campaign.UPSTREAM_FLAGS = (["--gpu-memory-utilization", "0.90"]
                               + (["--enforce-eager"] if eager else []))
    rlm_campaign.UPSTREAM_ENV = {}
    run = run or f"{time.strftime('%Y%m%d-%H%M%S')}-small"
    out = Path(VOL_RESULTS, "replay", run)
    argv = ["run", "--out", str(out), "--corpus", str(Path(VOL_RESULTS, corpus)),
            "--units", units, "--conc", str(conc), "--trees", TREES, "--model", SMOKE_MODEL,
            "--launch", "--start-timeout", "900", "--max-minutes", str(max_minutes),
            "--unit-timeout-min", str(unit_timeout_min), "--warmup-passes", "1",
            "--handler-backlog", str(handler_backlog), f"--serve-extra={serve_extra}"]
    if sessions:
        argv += ["--sessions", sessions]
    if warm_arm:
        argv += ["--warm-arm", warm_arm]
    if warm_sessions:
        argv += ["--warm-sessions", warm_sessions]
    if design_file:
        argv += ["--design-file", str(Path("/opt/cloud", design_file))]
    if estimates:
        argv += ["--estimates", estimates]
    return _campaign(out, argv, launch)


@app.function(gpu="T4", cpu=8.0, timeout=45 * 60, volumes=VOLUMES, retries=0)
def smoke(run: str = "", arms: str = "nospec,stream,scout,wide", once: str = "",
          sessions: str = "pairs32k-15,trec132k-17000232.w8k-c1,trec132k-17000222.w8k-c8",
          conc: int = 3, corpus: str = "replay/corpus", max_minutes: float = 30,
          handler_backlog: int = 0, launch: str = "") -> str:
    """The plumbing on a real vLLM, cheaply: a 1.7B model on a T4, three sessions, every
    arm once. Checks what the fake engine cannot: forced output lengths, running usage
    counts in the stream, and that each unit is exact on a real engine. Its times say
    nothing about the H100."""
    sys.path.insert(0, "/opt/cloud")
    import rlm_campaign

    # a T4 cannot run the H100's server flags (flash-attn backend, 0.92 of the memory)
    rlm_campaign.UPSTREAM_FLAGS = ["--gpu-memory-utilization", "0.90", "--enforce-eager"]
    rlm_campaign.UPSTREAM_ENV = {}
    run = run or f"{time.strftime('%Y%m%d-%H%M%S')}-smoke"
    out = Path(VOL_RESULTS, "replay", run)
    argv = ["run", "--out", str(out), "--corpus", str(Path(VOL_RESULTS, corpus)),
            "--arms", arms, "--once", once, "--repeats", "1", "--conc", str(conc),
            "--sessions", sessions, "--trees", TREES, "--model", SMOKE_MODEL, "--launch",
            "--start-timeout", "900", "--max-minutes", str(max_minutes),
            "--unit-timeout-min", "12", "--warmup-passes", "1",
            "--handler-backlog", str(handler_backlog),
            "--serve-extra=--max-model-len 32768 --dtype half"]
    return _campaign(out, argv, launch)


@app.function(cpu=8.0, memory=4096, timeout=10 * 60, volumes=VOLUMES, retries=0)
def probe_handler(calls: int = 2000, sub_ms: float = 150.0) -> dict:
    """rlms' LM handler under a burst of single calls, on this Linux: `calls` requests
    through a pool of 16 and of 128 threads, with rlms' listen backlog of 5 and with 1,024.
    The client behind the handler only sleeps, so what is measured is the handler's
    socket path: time per call above the sleep, and calls that came back as an error."""
    import statistics
    from concurrent.futures import ThreadPoolExecutor

    from rlm.clients.base_lm import BaseLM
    from rlm.core.comms_utils import LMRequest, send_lm_request
    from rlm.core.lm_handler import LMHandler, ThreadingLMServer
    from rlm.core.types import ModelUsageSummary, UsageSummary

    class Sleeper(BaseLM):
        def __init__(self):
            super().__init__(model_name="sleeper")

        def completion(self, prompt, model=None):
            time.sleep(sub_ms / 1000.0)
            return "ok"

        async def acompletion(self, prompt, model=None):
            return "ok"

        def get_usage_summary(self):
            return UsageSummary(model_usage_summaries={})

        def get_last_usage(self):
            return ModelUsageSummary(total_calls=1, total_input_tokens=1, total_output_tokens=1)

    rows = []
    for backlog in (5, 1024):
        ThreadingLMServer.request_queue_size = backlog
        for width in (16, 128):
            with LMHandler(Sleeper()) as h:
                def one(i, addr=h.address):
                    t = time.perf_counter()
                    r = send_lm_request(addr, LMRequest(prompt=f"p{i}", depth=1), timeout=60)
                    return time.perf_counter() - t, bool(r.success)

                t0 = time.perf_counter()
                with ThreadPoolExecutor(max_workers=width) as pool:
                    res = list(pool.map(one, range(calls)))
                wall = time.perf_counter() - t0
            lat = sorted(1000 * x for x, _ in res)
            over = [x - sub_ms for x in lat]
            rows.append({"backlog": backlog, "width": width, "calls": calls,
                         "errors": sum(1 for _, ok in res if not ok), "wall_s": round(wall, 2),
                         "ideal_s": round(calls / width * sub_ms / 1000.0, 2),
                         "over_ms_p50": round(statistics.median(over), 1),
                         "over_ms_p99": round(over[int(0.99 * len(over))], 1),
                         "over_ms_max": round(over[-1], 1),
                         "slower_than_1s": sum(1 for x in over if x > 1000)})
            print(rows[-1], flush=True)
    def sysctl(path: str) -> str | None:
        try:
            return Path(path).read_text().strip()
        except OSError:  # Modal's sandbox (gVisor) has its own network stack
            return None

    info = {"rows": rows, "sub_ms": sub_ms, "nproc": os.cpu_count(),
            "kernel": subprocess.run(["uname", "-a"], capture_output=True, text=True).stdout.strip(),
            "somaxconn": sysctl("/proc/sys/net/core/somaxconn"),
            "abort_on_overflow": sysctl("/proc/sys/net/ipv4/tcp_abort_on_overflow"),
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    Path(VOL_RESULTS, "replay").mkdir(parents=True, exist_ok=True)
    Path(VOL_RESULTS, "replay", "probe_handler.json").write_text(json.dumps(info, indent=1))
    results_vol.commit()
    return info


@app.local_entrypoint()
def launch_info() -> None:
    """What would be recorded as launch.json (pass it with --launch to replay or smoke)."""
    print(json.dumps(LAUNCH, indent=1))
