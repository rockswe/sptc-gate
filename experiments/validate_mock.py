"""Validation layer 1: agent-side fidelity.

Run REAL spec-ptc 0.1.1 (threads, wall clock) on the 22 suite patterns with a
mock engine whose sub-call latency is a deterministic function of the prompt,
streamed exactly like spec-ptc's SuiteEngine (24-char deltas at 60 tok/s).
Then replay the same patterns in the simulator with the same latency function.
Any gap is agent-side modeling error (segmenter/shadow/peek/claim timing), not
server error.

  .venv/bin/python experiments/validate_mock.py [--reps 3] [--sim-only]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sptc_sim import suite
from sptc_sim.agent import FixedBackend, PolicyCfg, ScriptedStream, run_turn
from sptc_sim.des import Sim
from sptc_sim.trace import compile_turn

OUT = Path(__file__).resolve().parents[1] / "results" / "validate_mock.json"
TPS = 60.0


def mock_latency_of_hash(h: str) -> float:
    """0.25 s + up to 0.5 s, from the call's identity hash."""
    return 0.25 + (int(h[:6], 16) % 1000) / 1000 * 0.5


def _hash(tool: str, args: tuple) -> str:
    return hashlib.sha1(repr((tool, args)).encode()).hexdigest()[:8]


class MockSuiteEngine:
    """spec-ptc's SuiteEngine with the HTTP call replaced by a timed sleep.
    Outputs mirror sptc_sim.trace._Results so prompts (and hashes) line up."""

    def __init__(self, tps: float = TPS) -> None:
        self.tps = tps
        self.occ: Counter = Counter()
        self.lock = threading.Lock()

    def stream_main(self, text: str):
        chunk = 24
        delay = (chunk / 4) / self.tps
        for i in range(0, len(text), chunk):
            time.sleep(delay)
            yield text[i:i + chunk]

    def _call(self, prompt, _spec=None, tool="llm_query"):
        h = _hash(tool, (prompt,))
        with self.lock:
            n = self.occ[h]
            self.occ[h] += 1
        end = time.perf_counter() + mock_latency_of_hash(h)
        while time.perf_counter() < end:
            if _spec is not None and _spec.state == "evicted":
                raise RuntimeError("evicted")
            time.sleep(min(0.01, max(0.0, end - time.perf_counter())))
        out = f"<{h}#{n}> ok"
        low = str(prompt).lower()
        if "yes or no" in low or "yes/no" in low:
            out += " yes" if int(h, 16) % 2 else " no"
        return out

    def make_tools(self, reg, bus) -> None:
        def single(prompt, _spec=None):
            return self._call(prompt, _spec)

        single.wants_spec = True
        reg.register("llm_query", single, speculatable=True, pure=True, latency_hint_ms=1500)

        def batched(prompts, **kw):
            with ThreadPoolExecutor(max_workers=8) as pool:
                return list(pool.map(self._call, prompts))

        reg.register("llm_query_batched", batched, speculatable=True, pure=True, batched=True)
        self.notes = []
        reg.register("log_note", self.notes.append)
        reg.register("env_probe", lambda k: "[x=cloud spend]")

        def fragile(prompt, _spec=None):
            if "BOOM" in str(prompt):
                raise ValueError("tool failure: BOOM")
            return self._call(prompt, _spec, tool="llm_query_fragile")

        fragile.wants_spec = True
        reg.register("llm_query_fragile", fragile, speculatable=True, pure=True)


def run_real(name: str, mode: str) -> float:
    from spec_ptc import EventBus, Harness

    eng = MockSuiteEngine()
    h = Harness(eng, mode, bus=EventBus(), context=suite.context())
    t0 = time.perf_counter()
    h.run_turn(eng.stream_main(suite.response_text(name)))
    wall = time.perf_counter() - t0
    h.launcher.shutdown()
    return wall


def sleep_overshoot(n: int = 20, dt: float = 0.1) -> float:
    """Median lateness of time.sleep on this host at the stream's own delay (macOS ~5 ms)."""
    xs = []
    for _ in range(n):
        t = time.perf_counter()
        time.sleep(dt)
        xs.append(time.perf_counter() - t - dt)
    return statistics.median(xs)


OVERSHOOT = 0.0


def run_sim(name: str, mode: str) -> float:
    trace = compile_turn(suite.response_text(name), suite.context())
    sim = Sim()
    lat = lambda info: mock_latency_of_hash(info.rid.split(":")[1].split("#")[0]) + OVERSHOOT
    be = FixedBackend(sim, lat)
    stream = ScriptedStream(sim, trace, TPS, overshoot=OVERSHOOT)
    proc = sim.process(run_turn(sim, trace, PolicyCfg(mode), be, stream))
    sim.run()
    return proc.value.wall


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--sim-only", action="store_true")
    ap.add_argument("--rerun", default="", help="comma list of patterns to re-measure")
    args = ap.parse_args()
    global OVERSHOOT
    OVERSHOOT = sleep_overshoot()
    print(f"host sleep overshoot: {1000 * OVERSHOOT:.2f} ms", flush=True)
    names = sorted(suite.measured_medians().pattern.unique())
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    for n in filter(None, args.rerun.split(",")):
        for mode in ("baseline", "spec"):
            old.pop(f"{n}|{mode}", None)
    rows = []
    for n in names:
        for mode, sim_mode in (("baseline", "baseline"), ("spec", "shadow")):
            key = f"{n}|{mode}"
            if args.sim_only or key in old:
                real = old.get(key, {}).get("real", [])
            else:
                real = [run_real(n, mode) for _ in range(args.reps)]
            simv = run_sim(n, sim_mode)
            rows.append({"pattern": n, "mode": mode, "real": real, "sim": simv})
            old[key] = {"real": real, "sim": simv, "overshoot": OVERSHOOT}
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps(old, indent=1))
            if real:
                med = statistics.median(real)
                print(f"{n:22s} {mode:8s} real={med:6.3f}s sim={simv:6.3f}s "
                      f"err={100 * (simv - med) / med:+6.1f}%", flush=True)


if __name__ == "__main__":
    main()
