"""Modal app: record `nospec` sessions with rlms' batch path fixed (PREREG_RECORD.md).

Run from this directory. What each command does:

    modal run --detach record_app.py::smoke     # T4, ~10 min: the plumbing on a real vLLM
    SPTC_RECORD_TIMEOUT_MIN=58 modal run --detach record_app.py::record   # the H100 run
    modal volume ls sptc-results record
    modal volume get sptc-results record/<run>/summary.md .

- **Client:** `/opt/spec-ptc` is spec-ptc as checked out locally (9b78b7d,
  unmodified), as in app.py. The image is app.py's, so nothing is rebuilt.
- **Tasks:** `rlm/tasks.json` on the results volume, written by `app.py::prepare`: the
  campaign's 8 tasks.
- **Limits:** A unit lasts
  at most about 21 minutes (rlm_record.py: sub-calls are refused 1,200 s after a task
  starts). `--max-minutes` stops before a unit that would pass it. SPTC_RECORD_TIMEOUT_MIN
  (default 60) is the function's hard timeout, read when `modal run` starts. Results are
  committed to the volume after every unit and every two minutes.
- **Data:** trajectories hold OOLONG text. They stay on the private volume and in
  `../../_modal_runs/record/`, never in the repository.
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
SPEC_PTC = Path(os.environ.get("SPEC_PTC_ROOT") or HERE.parents[1] / "spec-ptc")
MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
SMOKE_MODEL = "Qwen/Qwen3-1.7B"
VOL_HF, VOL_CACHE, VOL_RESULTS = "/vol/hf", "/vol/vllm-cache", "/vol/results"
TIMEOUT_MIN = int(os.environ.get("SPTC_RECORD_TIMEOUT_MIN", "60"))

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
    # the layers of app.py's image, in its order
    modal.Image.from_registry("nvidia/cuda:13.0.2-devel-ubuntu24.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install("vllm==0.32.0", "rlms==0.1.3", "datasets", "huggingface_hub", "psutil")
    .env({
        "HF_HOME": VOL_HF,
        "VLLM_CACHE_ROOT": VOL_CACHE,
        "SPEC_PTC_ROOT": "/opt/spec-ptc",
        "PYTHONUNBUFFERED": "1",
    })
)
LAUNCH: dict = {}
if modal.is_local():
    LAUNCH = {"stock": _git(SPEC_PTC), "cloud": _git(HERE.parent)}
    image = (
        image
        .add_local_dir(SPEC_PTC, "/opt/spec-ptc", copy=True,
                       ignore=[".git", "**/.git", "media", "**/__pycache__", ".venv*",
                               "*.egg-info", ".pytest_cache"])
        .run_commands("python -m pip install --no-deps /opt/spec-ptc")
        # which commits these trees are, and whether they were clean: read by the functions
        .env({"SPTC_LAUNCH": json.dumps(LAUNCH)})
        .add_local_dir(HERE, "/opt/cloud", ignore=["tests", "**/__pycache__", ".pytest_cache",
                                                   ".ruff_cache"])
    )

app = modal.App("sptc-record", image=image)


def _record(out: Path, argv: list[str]) -> str:
    sys.path.insert(0, "/opt/cloud")
    import rlm_record

    out.mkdir(parents=True, exist_ok=True)
    launch = os.environ.get("SPTC_LAUNCH", "")
    if launch:
        (out / "launch.json").write_text(launch)
    args = rlm_record.parse(argv)
    print("argv", argv, flush=True)
    # Commit every two minutes as well as after each unit: if the hard timeout kills a
    # unit, its events and finished trajectories are already stored.
    lock, stop = threading.Lock(), threading.Event()

    def commit() -> None:
        with lock:
            results_vol.commit()

    def commit_loop() -> None:
        while not stop.wait(120):
            try:
                commit()
            except Exception as e:  # noqa: BLE001 - the next tick tries again
                print(f"volume commit failed: {e}", flush=True)

    args.on_unit_done = lambda _u: commit()
    threading.Thread(target=commit_loop, daemon=True).start()
    try:
        rlm_record.run(args)
    finally:
        stop.set()
        cache_vol.commit()
        commit()
    md = out / "summary.md"
    text = md.read_text() if md.exists() else "no summary"
    print(text, flush=True)
    return text


@app.function(gpu="H100", cpu=8.0, timeout=TIMEOUT_MIN * 60, volumes=VOLUMES, retries=0)
def record(run: str = "", arms: str = "nospec", conc: str = "8", repeats: int = 2,
           max_minutes: float = 50, unit_estimate_min: float = 21,
           serve_extra: str = "--max-model-len 65536", warmup_passes: int = 2) -> str:
    """Start vLLM with the rerun's flags, warm up, probe the batch path, then the units.
    The defaults are PREREG_RECORD.md's design: `nospec`, the 8 tasks, 8 at a time, twice."""
    os.environ["HF_HUB_OFFLINE"] = "1"  # weights come from app.py::prepare
    run = run or f"{time.strftime('%Y%m%d-%H%M%S')}-record"
    out = Path(VOL_RESULTS, "record", run)
    argv = ["--spec-ptc", "/opt/spec-ptc", "run", "--out", str(out),
            "--tasks", str(Path(VOL_RESULTS, "rlm", "tasks.json")), "--model", MODEL,
            "--arms", arms, "--conc", conc, "--repeats", str(repeats), "--launch",
            "--max-minutes", str(max_minutes), "--unit-estimate-min", str(unit_estimate_min),
            "--warmup-passes", str(warmup_passes), "--start-timeout", "1200"]
    if serve_extra:  # one argument: the value itself starts with dashes
        argv += [f"--serve-extra={serve_extra}"]
    return _record(out, argv)


@app.function(gpu="T4", cpu=8.0, timeout=40 * 60, volumes=VOLUMES, retries=0)
def smoke(run: str = "", arms: str = "nospec", limit: int = 2, conc: str = "2",
          max_minutes: float = 25, root_max_deltas: int = 300) -> str:
    """The plumbing on a real vLLM, cheaply: a 1.7B model on a T4, two TREC tasks, one unit.
    Checks what the fake server cannot: the probe against uvicorn (stock rlms loses
    prompts, the fix none, also after the server has closed idle connections), and a unit
    end to end in this image. A root reply is cut after 300 deltas: a model this small
    writes little of use, and nothing here depends on what it writes."""
    os.environ["SPTC_ROOT_MAX_DELTAS"] = str(root_max_deltas)  # read when rlm_stream is imported
    sys.path.insert(0, "/opt/cloud")
    import rlm_campaign

    # a T4 cannot run the H100's server flags (flash-attn backend, 0.92 of the memory)
    rlm_campaign.UPSTREAM_FLAGS = ["--gpu-memory-utilization", "0.90", "--enforce-eager"]
    rlm_campaign.UPSTREAM_ENV = {}
    run = run or f"{time.strftime('%Y%m%d-%H%M%S')}-smoke"
    out = Path(VOL_RESULTS, "record", run)
    argv = ["--spec-ptc", "/opt/spec-ptc", "run", "--out", str(out),
            "--tasks", str(Path(VOL_RESULTS, "rlm", "tasks.json")), "--model", SMOKE_MODEL,
            "--arms", arms, "--conc", conc, "--repeats", "1", "--only", "trec",
            "--limit", str(limit), "--launch", "--max-minutes", str(max_minutes),
            "--warmup-passes", "1", "--start-timeout", "900",
            "--serve-extra=--max-model-len 32768 --dtype half"]
    return _record(out, argv)


@app.local_entrypoint()
def launch_info() -> None:
    """What would be recorded as launch.json."""
    print(json.dumps(LAUNCH, indent=1))
