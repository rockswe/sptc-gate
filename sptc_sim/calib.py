"""Calibration against spec-ptc's committed suite results (runs.csv).

Setting of those runs: Qwen3-4B-Instruct-2507 sub-calls on a vLLM server
(spec-ptc's benchmark scripts launch vLLM with --enforce-eager), the root
"model" a scripted stream at 60 tok/s, 5 reps per pattern and mode. The GPU
is not recorded in the repo; the blog's runs used an 8xH100 node, so we assume
one H100-SXM.

Unknowns: sub-call output lengths (the CSV has no token counts) and the
framework overheads. Method:
  1. Output length per call = pattern scale x template weight (a fixed prior
     from the prompt's instruction: "one word" is short, "five sentences"
     long) x lognormal noise, capped at the pattern's sub_max_tokens.
  2. For given global overheads, fit each pattern's scale on its BASELINE
     median exec time (serial calls on an idle server). One number per pattern.
  3. Predict the SPECULATIVE median wall time with no further fitting.
  4. Choose the 2 global overheads by leave-one-pattern-out: the overheads
     used to score pattern i are fit on the other 21 patterns' spec error.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from functools import lru_cache

from . import suite
from .agent import OutputModel, PolicyCfg, ScriptedStream, ServerBackend, run_turn
from .des import Sim
from .hardware import GPUS, MODELS, Overheads, StepCost
from .server import Server, ServerConfig
from .trace import CallInfo, compile_turn

_SHORT = ("one word", "one-word", "yes/no", "yes or no", "digit only", "single number",
          "say ok", "random-feeling word", "with a number")
_PHRASE = ("six words", "three-word", "four-word", "five-word", "topic word", "key noun",
           "noun in", "verb in", "opposite of", "length in words", "answer tersely",
           "extract the percentage", "quote the")


def prior_weight(info: CallInfo) -> float:
    """Relative expected output length from the instruction (prior, not fit)."""
    h = info.head.lower()
    if any(k in h for k in _SHORT):
        return 0.15
    if any(k in h for k in _PHRASE):
        return 0.4
    return 1.0


@lru_cache(maxsize=None)
def trace_of(name: str, chunk: int = 24):
    return compile_turn(suite.response_text(name), suite.context(), chunk=chunk)


def default_cost(ov: Overheads | None = None) -> StepCost:
    return StepCost(GPUS["H100-SXM"], MODELS["Qwen3-4B"], ov=ov or Overheads())


@dataclass
class SimOut:
    wall: float
    exec_s: float
    call_med: float


def simulate(name: str, policy: str, cost: StepCost, scale: float, sigma: float,
             reps: int = 7, tps: float = 60.0, weight=prior_weight,
             cfg: ServerConfig | None = None) -> list[SimOut]:
    p = suite.patterns()[name]
    trace = trace_of(name)
    outs = []
    for rep in range(reps):
        sim = Sim()
        server = Server(sim, cost, cfg or ServerConfig())
        om = OutputModel(mean=scale, sigma=sigma, cap=p.sub_max_tokens, seed=rep, weight=weight)
        be = ServerBackend(sim, server, om)
        proc = sim.process(run_turn(sim, trace, PolicyCfg(policy), be,
                                    ScriptedStream(sim, trace, tps), salt=str(rep)))
        sim.run(until=proc)
        r = proc.value
        cm = statistics.median(r.call_lat) if r.call_lat else 0.0
        outs.append(SimOut(r.wall, r.exec_s, cm))
    return outs


def med(xs: list[SimOut], attr: str) -> float:
    return statistics.median(getattr(x, attr) for x in xs)


def fit_scale(name: str, cost: StepCost, sigma: float, target_exec: float, reps: int = 7,
              lo: float = 0.5, hi: float = 1500.0, iters: int = 18) -> tuple[float, float]:
    """Bisection on the pattern's output scale so median baseline exec matches."""
    best = (lo, float("inf"))
    for _ in range(iters):
        mid = (lo * hi) ** 0.5
        got = med(simulate(name, "baseline", cost, mid, sigma, reps), "exec_s")
        if abs(got - target_exec) < abs(best[1] - target_exec):
            best = (mid, got)
        if got < target_exec:
            lo = mid
        else:
            hi = mid
    return best
