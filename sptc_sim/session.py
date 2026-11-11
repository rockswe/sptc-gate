"""Multi-turn agent sessions on a shared server, and load generators."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np

from .agent import PolicyCfg, ServedStream, ServerBackend, TurnResult, run_turn
from .des import Sim
from .server import BLOCK, Request, Server
from .workloads import TurnSpec


@dataclass
class SessionResult:
    sid: int
    program: str
    t_arrive: float
    t_end: float = 0.0
    turns: list[TurnResult] = field(default_factory=list)
    roots: list[Request] = field(default_factory=list)

    @property
    def latency(self) -> float:
        return self.t_end - self.t_arrive


SYS_SHARE = ("session", "program", "all")


def run_session(sim: Sim, server: Server, backend: ServerBackend, turns: tuple[TurnSpec, ...],
                policy: PolicyCfg, sid: int, sys_prompt: int = 2000, program: str = "",
                sys_share: str = "session"):
    """sys_share: which sessions' roots start with the same system prompt text, so that
    vLLM's content-addressed prefix cache keeps one copy of it (whole blocks, at most
    sys_prompt - 1 tokens, below the first prompt's last token):
      session  none: each session's prompt is its own (before the KV fixes, the only option;
               also what kaggle/bench_general.py sends: a per-agent tag leads the prompt)
      program  sessions running the same program
      all      every session (the local RLM traces share a 10,548-character prefix)"""
    if sys_share not in SYS_SHARE:
        raise ValueError(f"sys_share {sys_share!r}")
    res = SessionResult(sid, program, sim.now)
    prompt = sys_prompt
    shared = (sys_prompt - 1) // BLOCK * BLOCK
    prefix = None if sys_share == "session" or shared <= 0 else (
        (("sys", program) if sys_share == "program" else ("sys",)), shared)
    for k, ts in enumerate(turns):
        stream = ServedStream(sim, ts.trace, server, prompt, session=("agent", sid),
                              think_tokens=ts.think_tokens, prog_t=res.t_arrive,
                              prefix=prefix)
        tr = yield sim.process(
            run_turn(sim, ts.trace, policy, backend, stream, salt=f"{sid}/{k}",
                     prog_t=res.t_arrive))
        res.turns.append(tr)
        res.roots.append(stream.req)
        prompt += stream.out_tokens + ts.exec_out_tokens
    res.t_end = sim.now
    return res


def poisson_arrivals(sim: Sim, rate: float, n: int, seed: int, start):
    """Process: start(i) at Poisson times; returns list of session processes."""
    rng = random.Random(seed)
    procs = []
    for i in range(n):
        yield sim.timeout(rng.expovariate(rate))
        procs.append(start(i))
    return procs


def closed_loop(sim: Sim, n_agents: int, sessions_each: int, start):
    """Process: n_agents run sessions back to back; returns all session results."""
    out = []

    def agent(a):
        for j in range(sessions_each):
            r = yield start(a * 10_000 + j)
            out.append(r)

    yield sim.all_of([sim.process(agent(a)) for a in range(n_agents)])
    return out


def pct(xs, q) -> float:
    xs = [x for x in xs if x == x]
    return float(np.percentile(xs, q)) if xs else math.nan


def summarize(sessions: list[SessionResult], server: Server, backend: ServerBackend,
              horizon: float) -> dict:
    lat = [s.latency for s in sessions]
    roots = [r for s in sessions for r in s.roots]
    subs = list(backend.requests)
    # latency stats over sub-calls the agents actually used; wasted work separately
    used = [r for r in subs if r.state == "done" and r.claimed]
    itl = [x for r in roots for x in r.itl]
    turns = [t for s in sessions for t in s.turns]
    every = server.finished + server.aborted
    wasted = sum(r.computed_tokens for r in every if not r.claimed)
    useful = lambda r: r.prompt - r.hit_tokens + max(0, r.generated - 1)  # noqa: E731
    recompute = sum(max(0, r.computed_tokens - useful(r)) for r in server.finished if r.claimed)
    total = sum(r.computed_tokens for r in every)
    # stability: an open-loop run past capacity keeps getting slower; compare the
    # last third of sessions (by arrival) with the first third
    by_arrival = [s.latency for s in sorted(sessions, key=lambda s: s.t_arrive)]
    k = max(1, len(by_arrival) // 3)
    drift = float(np.mean(by_arrival[-k:]) / np.mean(by_arrival[:k])) if by_arrival else math.nan
    return {
        "sessions": len(sessions),
        "lat_p50": pct(lat, 50), "lat_p90": pct(lat, 90), "lat_p99": pct(lat, 99),
        "lat_mean": float(np.mean(lat)) if lat else math.nan,
        "drift": drift,
        "root_ttft_p50": pct([r.ttft for r in roots], 50),
        "root_ttft_p99": pct([r.ttft for r in roots], 99),
        "root_tpot_p50": pct([r.tpot for r in roots], 50),
        "root_tpot_p99": pct([r.tpot for r in roots], 99),
        "root_itl_p99": pct(itl, 99),
        "sub_ttft_p50": pct([r.ttft for r in used], 50),
        "sub_ttft_p99": pct([r.ttft for r in used], 99),
        "sub_tpot_p50": pct([r.tpot for r in used], 50),
        "sub_tpot_p99": pct([r.tpot for r in used], 99),
        "sub_e2e_p99": pct([r.t_done - r.arrival for r in used], 99),
        "root_cache_hit": (sum(r.hit_tokens for r in roots) / max(1, sum(r.prompt for r in roots))),
        "preemptions": sum(r.preemptions for r in roots + subs),
        "wasted_frac": wasted / total if total else 0.0,
        "recompute_frac": recompute / total if total else 0.0,
        "sub_calls": len(used),
        "hits": sum(t.hits for t in turns), "misses": sum(t.misses for t in turns),
        "evicted": sum(t.evicted for t in turns), "decoys": sum(t.decoys for t in turns),
        "reissued": sum(t.reissued for t in turns),
        # busy = any work scheduled (not spare capacity: a busy engine can still batch more)
        "busy": server.busy_time / horizon if horizon else math.nan,
        "steps": server.steps,
        "kv_evicted_tokens": server.kv.evicted_tokens,
    }
