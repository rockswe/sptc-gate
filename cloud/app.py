"""Modal app: spec-ptc's OOLONG RLM campaign on one H100.

Run from this directory, after `modal setup`.

What each command does:

    modal run app.py::probe        # ~2 min of H100: driver, CUDA, torch, vLLM, KernelConfig
    modal run app.py::prepare      # CPU only: model weights and tasks.json into volumes
    modal run --detach app.py::campaign --preset smoke   # one TREC task per arm, conc 1
    modal run --detach app.py::campaign --preset main --unit-estimate-min 6
    modal volume ls sptc-results rlm
    modal volume get sptc-results rlm/<run> ../results/modal_h100_rlm/

Limits:
- The campaign stops before any unit that would overrun --max-minutes, and every
  function has a hard timeout.
- Weights are downloaded by `prepare` on a CPU container, so the GPU container never
  downloads them. The campaign runs with HF_HUB_OFFLINE=1.

`modal app stop sptc-rlm` kills anything still running.
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
VOL_HF, VOL_CACHE, VOL_RESULTS = "/vol/hf", "/vol/vllm-cache", "/vol/results"

hf_vol = modal.Volume.from_name("sptc-hf", create_if_missing=True)
cache_vol = modal.Volume.from_name("sptc-vllm-cache", create_if_missing=True)
results_vol = modal.Volume.from_name("sptc-results", create_if_missing=True)
VOLUMES = {VOL_HF: hf_vol, VOL_CACHE: cache_vol, VOL_RESULTS: results_vol}

image = (
    # Modal's hosts: driver 610.57, CUDA 13.3 (modal.com/docs/guide/cuda, as of
    # 2026-11-08); vLLM 0.32.0's default build is CUDA 13.0
    modal.Image.from_registry("nvidia/cuda:13.0.2-devel-ubuntu24.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install("vllm==0.32.0", "rlms==0.1.3", "datasets", "huggingface_hub", "psutil")
    .env({
        "HF_HOME": VOL_HF,
        "VLLM_CACHE_ROOT": VOL_CACHE,
        "SPEC_PTC_ROOT": "/opt/spec-ptc",
        "PYTHONUNBUFFERED": "1",
    })
    # spec-ptc as checked out locally (commit 9b78b7d, unmodified): the client under test
    .add_local_dir(SPEC_PTC, "/opt/spec-ptc", copy=True,
                   ignore=[".git", "**/.git", "media", "**/__pycache__", ".venv*", "*.egg-info",
                           ".pytest_cache"])
    .run_commands("python -m pip install --no-deps /opt/spec-ptc")
    .add_local_dir(HERE, "/opt/cloud", ignore=["tests", "**/__pycache__", ".pytest_cache"])
)

app = modal.App("sptc-rlm", image=image)


def _sh(*cmd: str) -> str:
    p = subprocess.run(list(cmd), capture_output=True, text=True)
    return (p.stdout + p.stderr).strip()


@app.function(gpu="H100", cpu=2.0, timeout=15 * 60, volumes=VOLUMES, retries=0)
def probe() -> dict:
    """Driver, CUDA, torch and vLLM as the campaign will see them (no model load)."""
    code = (
        "import json, dataclasses, torch, vllm\n"
        "try:\n    from vllm.config import KernelConfig\n"
        "except ImportError:\n    from vllm.config.kernel import KernelConfig\n"
        "print(json.dumps({'torch': torch.__version__, 'torch_cuda': torch.version.cuda,"
        " 'cuda_ok': torch.cuda.is_available(),"
        " 'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,"
        " 'vllm': vllm.__version__,"
        " 'kernel_config_fields': [f.name for f in dataclasses.fields(KernelConfig)]}))"
    )
    out = {
        "nvidia_smi": _sh("nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                          "--format=csv"),
        "python": sys.version.split()[0],
        "versions": _sh(sys.executable, "-c", code).splitlines()[-1],
        "rlms": _sh(sys.executable, "-c",
                    "import importlib.metadata as m; print(m.version('rlms'))"),
        "nproc": os.cpu_count(),
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    Path(VOL_RESULTS, "rlm").mkdir(parents=True, exist_ok=True)
    Path(VOL_RESULTS, "rlm", "probe.json").write_text(json.dumps(out, indent=1))
    results_vol.commit()
    print(json.dumps(out, indent=1))
    return out


@app.function(cpu=4.0, memory=16384, timeout=2 * 3600, volumes=VOLUMES, retries=0)
def prepare(n_trec: int = 4, n_pairs: int = 4) -> dict:
    """Weights into the HF volume, the campaign's 8 tasks into tasks.json (CPU only)."""
    from huggingface_hub import snapshot_download

    t0 = time.time()
    path = snapshot_download(MODEL)
    hf_vol.commit()
    rev = Path(path).name
    size = sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
    sys.path.insert(0, "/opt/cloud")
    import rlm_campaign

    tasks = Path(VOL_RESULTS, "rlm", "tasks.json")
    rlm_campaign.main(["--spec-ptc", "/opt/spec-ptc", "tasks", "--out", str(tasks),
                       "--n-trec", str(n_trec), "--n-pairs", str(n_pairs)])
    hf_vol.commit()  # the datasets cache lives under HF_HOME too
    info = {"model": MODEL, "revision": rev, "weights_gb": round(size / 1e9, 1),
            "tasks": str(tasks), "seconds": round(time.time() - t0)}
    Path(VOL_RESULTS, "rlm", "prepare.json").write_text(json.dumps(info, indent=1))
    results_vol.commit()
    print(json.dumps(info, indent=1))
    return info


PRESETS = {
    # one TREC task per arm at concurrency 1: plumbing, server start, task duration
    "smoke": {"conc": "1", "repeats": 1, "only": "trec", "limit": 1, "max_minutes": 35},
    # 3 arms x conc {8, 4} x 2 repeats, ABBA, 8 tasks per unit
    "main": {"conc": "8,4", "repeats": 2, "only": None, "limit": None, "max_minutes": 100},
}


# Hard cap on one campaign call, in minutes, read when `modal run` starts. --max-minutes
# only stops before the next unit; this kills a unit that hangs. Finished units are
# already committed to the results volume.
CAMPAIGN_TIMEOUT_MIN = int(os.environ.get("SPTC_CAMPAIGN_TIMEOUT_MIN", "180"))


@app.function(gpu="H100", cpu=8.0, timeout=CAMPAIGN_TIMEOUT_MIN * 60, volumes=VOLUMES,
              retries=0)
def campaign(preset: str = "smoke", run: str = "", max_minutes: float = 0,
             unit_estimate_min: float = 0, arms: str = "nospec,fanout,stream",
             conc: str = "", repeats: int = 0, repl_fix: bool = True,
             serve_extra: str = "", warmup_passes: int = 2) -> str:
    """Start vLLM with the campaign's flags, run the units, commit results after each one."""
    os.environ["HF_HUB_OFFLINE"] = "1"  # weights come from `prepare`, never downloaded here
    p = dict(PRESETS[preset])
    run = run or f"{time.strftime('%Y%m%d-%H%M%S')}-{preset}"
    out = Path(VOL_RESULTS, "rlm", run)
    argv = ["--spec-ptc", "/opt/spec-ptc", "run", "--out", str(out),
            "--tasks", str(Path(VOL_RESULTS, "rlm", "tasks.json")), "--model", MODEL,
            "--arms", arms, "--conc", conc or p["conc"],
            "--repeats", str(repeats or p["repeats"]), "--launch",
            "--max-minutes", str(max_minutes or p["max_minutes"]),
            "--unit-estimate-min", str(unit_estimate_min),
            "--warmup-passes", str(warmup_passes),
            "--start-timeout", "1200"]  # a hung vLLM start ends after 20 minutes
    if p["only"]:
        argv += ["--only", p["only"]]
    if p["limit"]:
        argv += ["--limit", str(p["limit"])]
    if not repl_fix:
        argv += ["--no-repl-fix"]
    if serve_extra:  # one argument: the value itself starts with dashes
        argv += [f"--serve-extra={serve_extra}"]
    sys.path.insert(0, "/opt/cloud")
    import rlm_campaign

    args = rlm_campaign.parser().parse_args(argv)
    print("run", run, "argv", argv, flush=True)
    # Commit the results every two minutes as well as after each unit: if the hard
    # timeout kills a unit, its events and finished trajectories are already stored.
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

    threading.Thread(target=commit_loop, daemon=True).start()
    try:
        rlm_campaign.run_campaign(args, on_unit_done=lambda _u: commit())
    finally:
        stop.set()
        cache_vol.commit()
        commit()
    summary = (out / "summary.md").read_text() if (out / "summary.md").exists() else "no summary"
    print(summary, flush=True)
    return summary


@app.function(cpu=2.0, memory=8192, timeout=30 * 60, volumes=VOLUMES, retries=0)
def compact(run: str) -> list:
    """trajs_compact/ for every unit of a run on the results volume (CPU only).
    Then `modal volume get` each unit without its rlm_trajs/ to fetch megabytes, not
    gigabytes: the raw trajectories repeat the whole context in every block."""
    sys.path.insert(0, "/opt/cloud")
    import rlm_campaign

    res = rlm_campaign.compact(Path(VOL_RESULTS, "rlm", run))
    results_vol.commit()
    for r in res:
        print(f"{r['unit']}: {r['files']} files, {r['bytes'] / 1e6:.1f} MB -> "
              f"{r['compact_bytes'] / 1e6:.1f} MB", flush=True)
    return res
