"""Modal app: kaggle/vllm_bench.py on a Modal GPU, in place of the Kaggle T4 notebooks.

Run from this directory.

    modal run --detach bench_app.py::bench --preset both_default --client new
    modal run --detach bench_app.py::bench --preset both_default --client old \
        --arms fcfs-d/spec+bad,cap-d/both,plugin-d/both
    modal volume get sptc-results bench/<run> ../../_modal_runs/

`--client` picks the spec-ptc the agents run:

- `new`: ../../spec-ptc-sptc-hints as it is on disk (the sptc-hints fork's working tree).
- `old`: that fork's last commit, which is the client of the three Kaggle T4 runs
  (identical to integrations/spec-ptc-sptc-hints.patch on spec-ptc 9b78b7d).

The bench itself is unchanged: it launches and stops its own vLLM servers (stock, vLLM
priority, the sptc plugin), runs the preset's arms and writes sweep/summary.md. Its
`plan --preset <name>` prints an estimate without a GPU.

SPTC_BENCH_TIMEOUT_MIN (default 120) is the function's hard timeout, read when `modal run`
starts. Results are committed to the volume every two minutes, so a killed run keeps what
it finished; the bench skips finished runs when the same `--run` is started again.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
if modal.is_local():  # these paths exist on the machine that runs `modal run`, not in the container
    SIM = HERE.parent
    FORK = Path(os.environ.get("SPTC_HINTS_ROOT") or HERE.parents[1] / "spec-ptc-sptc-hints")
MODEL = "Qwen/Qwen3-1.7B"
VOL_HF, VOL_CACHE, VOL_RESULTS = "/vol/hf", "/vol/vllm-cache", "/vol/results"
BENCH_TIMEOUT_MIN = int(os.environ.get("SPTC_BENCH_TIMEOUT_MIN", "120"))
SPEC_IGNORE = [".git", "**/.git", "media", "**/__pycache__", ".venv*", "*.egg-info",
               ".pytest_cache", "uv.lock"]

hf_vol = modal.Volume.from_name("sptc-hf", create_if_missing=True)
cache_vol = modal.Volume.from_name("sptc-vllm-cache", create_if_missing=True)
results_vol = modal.Volume.from_name("sptc-results", create_if_missing=True)
VOLUMES = {VOL_HF: hf_vol, VOL_CACHE: cache_vol, VOL_RESULTS: results_vol}


def fork_commit() -> str:
    return subprocess.run(["git", "-C", str(FORK), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


def old_client_dir() -> Path:
    """The fork's last commit, exported next to the system temp dir (once per commit)."""
    import tarfile
    import tempfile

    sha = fork_commit()
    out = Path(tempfile.gettempdir()) / f"sptc-spec-ptc-old-{sha[:12]}"
    if not (out / "src").is_dir():
        out.mkdir(parents=True, exist_ok=True)
        tar = subprocess.run(["git", "-C", str(FORK), "archive", "HEAD"], capture_output=True,
                             check=True).stdout
        with tempfile.TemporaryFile() as f:
            f.write(tar)
            f.seek(0)
            with tarfile.open(fileobj=f) as t:
                t.extractall(out, filter="data")
    return out


image = (
    modal.Image.from_registry("nvidia/cuda:13.0.2-devel-ubuntu24.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install("vllm==0.32.0", "pandas", "numpy", "psutil")
    .env({"HF_HOME": VOL_HF, "VLLM_CACHE_ROOT": VOL_CACHE, "PYTHONUNBUFFERED": "1"})
)
if modal.is_local():
    image = (
        image
        .add_local_dir(old_client_dir(), "/opt/spec-ptc-old", copy=True, ignore=SPEC_IGNORE)
        .add_local_dir(FORK, "/opt/spec-ptc-new", copy=True, ignore=SPEC_IGNORE)
        .add_local_dir(SIM, "/opt/sim", copy=True,
                       ignore=[".git", "**/__pycache__", "**/.pytest_cache", "**/.ruff_cache",
                               "**/*.zip", "**/*.png", "data", "mac", "cloud",
                               "results/clog*", "results/census*", "results/corrections",
                               "results/general", "results/t4_run1_analysis", "results/sweep_prep", "results/sweep_runs.csv",
                               "results/calibration.json", "results/run_all.log"])
        # `spec_ptc` is the package name of spec-ptc's src/: one importable copy per client
        .run_commands(
            "for c in old new; do mkdir -p /opt/pkg-$c && "
            "ln -s /opt/spec-ptc-$c/src /opt/pkg-$c/spec_ptc; done",
            "python -m pip install --no-deps -e /opt/sim/integrations",
        )
    )

app = modal.App("sptc-bench", image=image)


def _committer(stop: threading.Event, every: float = 120.0) -> None:
    while not stop.wait(every):
        try:
            results_vol.commit()
        except Exception as e:  # noqa: BLE001 - a missed commit is retried at the next tick
            print(f"[bench] volume commit failed: {e}", flush=True)


@app.function(gpu="T4", cpu=8.0, timeout=BENCH_TIMEOUT_MIN * 60, volumes=VOLUMES, retries=0)
def bench(preset: str = "both_default", client: str = "new", arms: str = "",
          agents: str = "4", run: str = "", pressure_config: str = "fallback",
          extra: str = "") -> str:
    """One sweep of kaggle/vllm_bench.py, then its report. Returns the Pressure table."""
    if client not in ("old", "new"):
        raise ValueError("client must be old or new")
    sys.path.insert(0, "/opt/sim/kaggle")
    import vllm_bench as vb

    run = run or f"{time.strftime('%Y%m%d-%H%M%S')}-{preset}-{client}"
    out = Path(VOL_RESULTS, "bench", run)
    out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": f"/opt/pkg-{client}"}
    base = [sys.executable, "/opt/sim/kaggle/vllm_bench.py"]
    cmd = [*base, "sweep", "--preset", preset, "--agents", agents, "--model", MODEL,
           "--spec-ptc", f"/opt/spec-ptc-{client}", "--launch", "--out", str(out)]
    if arms:
        cmd += ["--arms", arms]
    if preset in ("pressure", "probe"):
        cmd += ["--serve-cmd", vb.PRESSURE_SERVE_CMD, "--pressure-config", pressure_config]
    cmd += extra.split()
    (out / "modal_run.json").write_text(__import__("json").dumps(
        {"cmd": cmd, "client": client, "preset": preset, "gpu": subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True).stdout.strip(),
         "nproc": os.cpu_count(), "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        indent=1))
    print("[bench]", " ".join(cmd), flush=True)
    stop = threading.Event()
    th = threading.Thread(target=_committer, args=(stop,), daemon=True)
    th.start()
    try:
        code = subprocess.run(cmd, env=env).returncode
        subprocess.run([*base, "report", "--out", str(out)], env=env, capture_output=True)
    finally:
        stop.set()
        for v in (hf_vol, cache_vol, results_vol):
            v.commit()
    md = out / "sweep" / "summary.md"
    text = md.read_text() if md.exists() else "no summary"
    start = text.find("## Pressure")
    end = text.find("## Baselines")
    table = text[start:end if end > start else None] if start >= 0 else text[-4000:]
    print(f"[bench] sweep exit code {code}\n{table}", flush=True)
    return table


SUITE_SERVE = ["vllm", "serve", MODEL, "--dtype", "half", "--max-model-len", "8192",
               "--gpu-memory-utilization", "0.90", "--port", "8000"]  # the bench's default
RECORDED = "rec_helper_loop,rec_batched_counter,rec_try_loop"


@app.function(gpu="T4", cpu=8.0, timeout=45 * 60, volumes=VOLUMES, retries=0)
def suite(patterns: str = RECORDED, reps: int = 5, client: str = "new", scout: bool = True,
          run: str = "") -> str:
    """Fixed programs with real sub-calls on one vLLM server: no speculation, spec-ptc as
    it is, and (scout) spec-ptc with its scout pass. The default patterns are the loop
    shapes recorded from the RLM campaign (the fork's benchmark/suite/patterns_v7.py)."""
    import json
    import urllib.request

    run = run or f"{time.strftime('%Y%m%d-%H%M%S')}-suite-{client}"
    out = Path(VOL_RESULTS, "bench", run)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "server.log", "w")
    server = subprocess.Popen(SUITE_SERVE, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 15 * 60
        while True:
            if server.poll() is not None or time.time() > deadline:
                raise RuntimeError("vLLM did not start:\n" + (out / "server.log").read_text()[-3000:])
            try:
                urllib.request.urlopen("http://localhost:8000/v1/models", timeout=3)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(3)
        cmd = [sys.executable, "/opt/sim/kaggle/vllm_bench.py", "suite", "--model", MODEL,
               "--patterns", patterns, "--reps", str(reps), "--out", str(out),
               "--spec-ptc", f"/opt/spec-ptc-{client}", *(["--scout"] if scout else [])]
        print("[suite]", " ".join(cmd), flush=True)
        env = {**os.environ, "PYTHONPATH": f"/opt/pkg-{client}"}
        subprocess.run(cmd, env=env, stdout=open(out / "suite.log", "w"),
                       stderr=subprocess.STDOUT)
    finally:
        server.terminate()
        for v in (hf_vol, cache_vol, results_vol):
            v.commit()
    rows = json.loads((out / "suite.json").read_text())["suite"] if (out / "suite.json").exists() else []
    lines = ["| pattern | mode | runs | wall s, median | launched before the first answer | hits | misses | evicted | score |",
             "|" + "---|" * 9]
    by: dict = {}
    for r in rows:
        by.setdefault((r["pattern"], r["mode"]), []).append(r)
    for (pat, mode), rs in by.items():
        walls = sorted(x["wall_s"] for x in rs)
        med = walls[len(walls) // 2] if len(walls) % 2 else (walls[len(walls) // 2 - 1] + walls[len(walls) // 2]) / 2
        mid = sorted(rs, key=lambda x: x["wall_s"])[len(rs) // 2]
        lines.append(f"| {pat} | {mode} | {len(rs)} | {med:.2f} | {mid.get('launched_before_first_answer')} "
                     f"| {mid.get('hits')} | {mid.get('misses')} | {mid.get('evicted')} | {mid.get('score')} |")
    table = "\n".join(lines)
    (out / "suite.md").write_text(table + "\n")
    results_vol.commit()
    print(table, flush=True)
    return table
