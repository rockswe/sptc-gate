"""Workloads where best-effort ("bet") requests are common, beyond code-mode sPTC.

The census (results/census/SUMMARY.md) found that real code-mode agents make almost no bets.
These workloads are the places where speculative or opportunistic work is the norm:

  (a) react    classic one-call-per-step agents (ReAct) with prediction-based speculation
               on the SAME server as the agent's own calls:
      action   SPAgent / Speculative Actions style: each step, k short candidate calls
               guess the next action; a guessed action's tool starts at once, and a hit
               hides the tool behind the root's own decode. Misses are short waste.
      next     deeper speculation: while a tool runs, k guesses of the NEXT step's full LLM
               call start on predicted observations; a hit means that call is already
               (partly) decoded when the observation arrives. Misses are full-size waste.
  (b) branch   code-mode programs with literal calls in both arms of an `if`, launched by
               a literal scanner (Pydantic CodeMode / pi-fabric): agent.py's `literal`
               policy on a branch-dense program; the untaken arm is waste.
  (c) batch    offline background jobs (evals, summarization) sharing the server with
               interactive agents, under each scheduler's way of tagging them, plus a
               distinct background class.

`GeneralServer` adds what these need to the base server without changing it:
  - policy `agent` follows the sptc_vllm plugin rather than the simulator's own agent
    policy: plain FCFS with bets last (no program-level order), running bets are not
    evicted for waiting work, and no promotion (the plugin cannot change a running
    request's class, so a claimed bet stays a bet);
  - policy `priority` is vLLM's `--scheduling-policy priority` with a client that sets
    two levels (bets 1, everything else 0); the simulator's own `priority` policy also
    ranks roots above sub-calls, which a vLLM client cannot express without tagging
    every request;
  - `running` stays in admission order, as in vLLM, which never sorts it: priority picks
    only the waiting order and the preemption victim, never who gets the token budget
    first (the plugin only moves running bets last);
  - vLLM 0.32's full-sequence admission (`scheduler_reserve_full_isl`, on by default): a
    waiting or preempted request starts only if its whole prompt (plus output so far)
    fits in KV. The base server now has it too (`ServerConfig.full_isl`); before the KV fixes
    only this server had it, so results/general used full_isl with the rest of LEGACY_KV;
  - a background class next to bets: gated like a bet, but requeued, never dropped;
  - a shared prefix for speculative calls (they reuse the agent's cached history), so
    their steps read the full context's KV but allocate only their own blocks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .agent import _normal, _u01
from .des import Event, Sim
from .server import (BLOCK, PRIO_NORMAL, PRIO_SPEC, Request, Server,
                     ServerConfig, legacy_kv_env)
from .trace import CallInfo, compile_turn
from .workloads import FINAL, PROBE, TOOLS, TurnSpec, make_context, output_weight


# ----------------------------------------------------------------------------- server
@dataclass(eq=False)
class GRequest(Request):
    shared: int = 0  # cached prefix tokens it reads but does not own (agent history)
    bg: bool = False  # background class (only meaningful with spec=True)
    cache_as: object = None  # on finish, extend this session's cached prefix with its KV
    cut: bool = False  # a batch job cut off when the run ended (its result is still needed)


class GeneralServer(Server):
    """Server with the plugin's agent policy, vLLM-style two-level priority, no
    promotion, and a background class."""

    def __init__(self, sim: Sim, cost, cfg: ServerConfig | None = None,
                 promote_bets: bool = False, bg_window: int | None = None,
                 evict_bets_for_waiting: bool = False, evict_bg_for_waiting: bool = True,
                 reserve_full_isl: bool | None = None) -> None:
        super().__init__(sim, cost, cfg)
        if reserve_full_isl is None and legacy_kv_env():
            reserve_full_isl = True  # GeneralServer had full-ISL admission before the KV fixes
        if reserve_full_isl is not None:  # None: ServerConfig.full_isl (default True)
            self.full_isl = reserve_full_isl
        self.promote_bets = promote_bets
        self.bg_window = bg_window  # background admission window (None: same as bets)
        self.evict_bets_for_waiting = evict_bets_for_waiting  # plugin: no
        self.evict_bg_for_waiting = evict_bg_for_waiting
        self.bet_hold_steps = 16  # the plugin's default
        self._held: dict[int, int] = {}

    def submit(self, r: Request) -> Event:
        ev = super().submit(r)
        if self.cfg.policy == "priority" and r.kind == "root":
            r.priority = PRIO_NORMAL  # client priority: bets low, everything else equal
        return ev

    def promote(self, r: Request) -> None:
        if self.promote_bets:
            super().promote(r)

    def _order(self, r: Request) -> tuple:
        if self.cfg.policy == "agent":  # the plugin: vanilla FCFS, bets last
            return (r.priority == PRIO_SPEC, r.arrival, r.rid)
        return super()._order(r)

    def _running_key(self, r: Request) -> tuple:
        # vLLM never sorts `running`: it stays in admission order (a stable sort on a
        # constant key). The plugin moves running bets last so that running[-1] is a bet.
        return (self.cfg.policy == "agent" and r.priority == PRIO_SPEC,)

    def _victim(self) -> Request:
        if self.cfg.policy == "priority":  # vLLM: max(running, key=(priority, arrival_time))
            return max(self.running, key=lambda r: (r.priority, r.arrival))
        return self.running[-1]  # vLLM FCFS: running.pop()

    def _preempt(self, victim: Request) -> None:
        if getattr(victim, "bg", False) and self.cfg.reject_bets:
            self.cfg.reject_bets = False  # background work is requeued, never dropped
            try:
                super()._preempt(victim)
            finally:
                self.cfg.reject_bets = True
            return
        super()._preempt(victim)

    def _preempt_for(self, r: Request, n: int, batch: list) -> bool:
        if r.priority == PRIO_SPEC:
            return False
        while not self._grow(r, n):
            lower = [x for x in self.running if x.priority == PRIO_SPEC and (
                self.evict_bg_for_waiting if getattr(x, "bg", False)
                else self.evict_bets_for_waiting)]
            if not lower:
                return False
            victim = max(lower, key=self._order)
            self._preempt(victim)
            batch[:] = [b for b in batch if b[0] is not victim]
        return True

    # -- the plugin's bet gate: at admission, not at submit -------------------------
    def _is_bet(self, r: Request) -> bool:
        return (self.cfg.policy == "agent" and self.cfg.reject_bets
                and r.priority == PRIO_SPEC and not getattr(r, "bg", False))

    def admits_bet_now(self) -> bool:
        """Clients submit bets unconditionally: the plugin gates them when vLLM's
        waiting loop reaches them (after this step's normal admissions)."""
        if self.cfg.policy == "agent" and self.cfg.reject_bets:
            return True
        return super().admits_bet_now()

    def _reject(self, r: Request) -> None:
        r.sptc_rejected = True  # the client sees an aborted, zero-token response
        self._held.pop(r.rid, None)
        self.abort(r)

    def _spec_admissible(self, r: Request, admitted: list, normal_waiting: bool) -> bool:
        if getattr(r, "bg", False) and self.bg_window is not None and self.cfg.policy == "agent":
            if normal_waiting or len(self.running) + len(admitted) + 1 > self.bg_window:
                return False
            return self.kv.headroom(self.sim.now) >= self.cfg.spec_kv_reserve * self.kv.total
        ok = super()._spec_admissible(r, admitted, normal_waiting)
        if not ok and self._is_bet(r):
            self._reject(r)  # the gate ran and failed: rejected in the same step
        return ok

    def _mirrors_plugin(self) -> bool:
        return self.cfg.plugin_fixes and self.cfg.policy == "agent" and self.cfg.reject_bets

    def _schedule(self):
        batch = super()._schedule()
        if self.cfg.policy == "agent" and self.cfg.reject_bets:
            # end of step: re-gate every waiting bet with the end-of-step state; a bet
            # that passes stays queued, at most bet_hold_steps steps (counted as the
            # adapter counts them: ServerConfig.plugin_fixes)
            gate = (not any(w.priority < PRIO_SPEC for w in self.waiting)
                    and self._in_free_window()
                    and self.kv.headroom(self.sim.now) >= self.cfg.spec_kv_reserve * self.kv.total)
            for r in list(self.waiting):
                if not self._is_bet(r):
                    continue
                if gate and not self._hold_counts(r, bool(batch)):
                    self._held.setdefault(r.rid, 0)  # held, this step not counted
                    continue
                self._held[r.rid] = self._held.get(r.rid, 0) + 1
                if not gate or self._held[r.rid] > self.bet_hold_steps:
                    self._reject(r)
        # the batch's third field only feeds the step cost: add the shared prefix
        return [(r, n, c + getattr(r, "shared", 0)) for r, n, c in batch]

    def _finish(self, r: Request) -> None:
        key = getattr(r, "cache_as", None)
        if key is None or self.cfg.kv_policy == "none":
            super()._finish(r)
            return
        # vLLM's prefix cache is content-addressed: a guess that turns out right leaves
        # the next prompt's prefix cached. Extend the session entry if it still covers
        # the shared prefix; otherwise keep it as it is.
        old = self.kv.entries.get(key)
        blocks = r.blocks
        if old is not None and old.tokens + BLOCK >= r.shared:  # block-level approximation
            self.kv.pop(key)
            self.kv.put(key, min(old.tokens, r.shared) + r.ctx, old.blocks + blocks,
                        self.sim.now, -1.0)
        elif self.cfg.cache_freed_blocks:  # its own blocks: cached, never looked up
            self._cache_blocks(r, ("dead", r.rid))
        else:
            self.kv.release(blocks)
        r.cache_as = None
        r.session = None
        r.blocks = 0
        self.running.remove(r)
        r.state = "done"
        r.t_done = self.sim.now
        self.finished.append(r)
        r.done.succeed(r)


def plugin_config(free_window: int = 8, **kw) -> dict:
    """ServerConfig knobs of the sptc_vllm plugin as the experiments run it."""
    return dict(policy="agent", reject_bets=True, spec_max_wait=math.inf,
                free_window=free_window, spec_kv_reserve=0.10, spec_prefill_budget=512, **kw)


class Call:
    """One client request on the shared server. `done` fires with 'ok', 'rejected'
    (a bet refused at submit: no spare capacity), 'dropped' (aborted by the server)
    or 'cancelled' (aborted by the client)."""

    def __init__(self, sim: Sim, server: Server, req: GRequest, client_s: float,
                 log: list | None = None) -> None:
        self.sim, self.server, self.req = sim, server, req
        self.client_s = client_s
        self.done = sim.event()
        self.cancelled = False
        self.submitted = False
        if log is not None:
            log.append(self)
        sim.process(self._run())

    def _run(self):
        sim, srv, r = self.sim, self.server, self.req
        yield sim.timeout(self.client_s)
        if self.cancelled:
            self.done.succeed("cancelled")
            return
        if (r.spec and not r.bg and srv.cfg.reject_bets and srv.cfg.policy == "agent"
                and not srv.admits_bet_now()):
            r.state = "rejected"
            self.done.succeed("rejected")
            return
        self.submitted = True
        yield srv.submit(r)
        if r.state == "aborted":
            self.done.succeed("cancelled" if self.cancelled else
                              "rejected" if getattr(r, "sptc_rejected", False) else "dropped")
            return
        yield sim.timeout(self.client_s)
        self.done.succeed("ok")

    @property
    def refused(self) -> bool:
        return self.done.triggered and self.done.value in ("rejected", "dropped")

    def cancel(self) -> None:
        if self.cancelled or self.done.triggered:
            return
        self.cancelled = True
        if self.submitted:
            self.server.abort(self.req)


def _first(sim: Sim, *evs: Event) -> Event:
    ev = sim.event()
    for e in evs:
        e.add_callback(lambda _e: ev.succeed())
    return ev


def _len(mean: float, sigma: float, *key) -> int:
    mu = math.log(max(mean, 1.0)) - sigma ** 2 / 2
    return max(1, int(round(math.exp(mu + sigma * _normal(*key)))))


# ----------------------------------------------------------------------------- (a) react
@dataclass
class ReactCfg:
    """A ReAct-style agent: each step one LLM call (thought + action), then one tool.
    Cited: SPAgent (arXiv 2511.20048) search tool ~1.5 s per call, k=3 candidate
    actions of "fewer than ten tokens", 40% average hit rate; PASTE v3 (2603.18897)
    top-1 accuracy at most 27.8%, top-3 recall 43.9%. Everything else is assumed."""

    steps: int = 6
    sys_prompt: int = 1200  # system prompt + question + tool descriptions
    step_out: float = 120.0  # thought + action tokens per step (mean)
    answer_out: float = 80.0  # final step: the answer
    obs_tokens: int = 300  # tool observation appended to the context
    out_sigma: float = 0.3
    tool_p50: float = 1.5
    tool_p99: float = 6.0
    mode: str = "none"  # none | action | next
    k: int = 3  # speculative candidates per step
    hit: float = 0.40  # P(one candidate matches the real action / observation) per step
    cand_out: int = 8  # action-only candidate output tokens
    cand_suffix: int = 60  # uncached instruction tokens of a candidate request
    bet: bool = True  # tag speculative calls as bets (the scheduler decides what that means)
    stall_s: float = 1.0  # a claimed guess with no token for this long is re-issued


# the workload variants of experiments/general.py and kaggle/bench_general.py
REACT_MODES = {
    "none": dict(mode="none"),
    # SPAgent's setting: 3 short candidates, 40% average hit rate
    "action": dict(mode="action", k=3, hit=0.40),
    # one guess of the next full call; PASTE's top-1 tool accuracy (at most 27.8%) as an
    # optimistic stand-in: guessing the next call also needs the observation right
    "next": dict(mode="next", k=1, hit=0.278),
    # three guesses, PASTE's top-3 recall (43.9%)
    "next3": dict(mode="next", k=3, hit=0.439),
}


def react_plan(cfg: ReactCfg, seed: int, sid: int) -> list[tuple[int, float, bool]]:
    """Per step: (output tokens, tool seconds, speculation hit). Deterministic in
    (seed, sid), so every scheduler and mode sees the same session; the Kaggle client
    (kaggle/bench_general.py) draws the same plan."""
    sigma = math.log(cfg.tool_p99 / cfg.tool_p50) / 2.326
    out = []
    for i in range(cfg.steps):
        mean = cfg.answer_out if i == cfg.steps - 1 else cfg.step_out
        n = _len(mean, cfg.out_sigma, seed, sid, i, "out")
        tool = cfg.tool_p50 * math.exp(sigma * _normal(seed, sid, i, "tool"))
        out.append((n, tool, _u01(seed, sid, i, "hit") < cfg.hit))
    return out


@dataclass
class GenSession:
    sid: int
    kind: str
    t_arrive: float
    t_end: float = 0.0
    roots: list = field(default_factory=list)  # the request that served each step
    hits: int = 0  # steps whose speculation guessed right
    spec_used: int = 0  # steps where a right guess actually saved time
    bets: int = 0

    @property
    def latency(self) -> float:
        return self.t_end - self.t_arrive


def react_session(sim: Sim, server: Server, cfg: ReactCfg, sid: int, seed: int,
                  client_s: float, log: list):
    """Process: one ReAct session; returns GenSession."""
    res = GenSession(sid, cfg.mode, sim.now)
    plan = react_plan(cfg, seed, sid)
    ctx = cfg.sys_prompt
    sess = ("agent", sid)
    carried: Call | None = None  # 'next' mode: a right guess that is this step's call

    def root_call(prompt: int, out: int, i: int) -> Call:
        return Call(sim, server, GRequest(prompt=prompt, out=out, kind="root", session=sess,
                                          track_itl=True, prog_t=res.t_arrive,
                                          tag=f"root:{sid}/{i}"), client_s, log)

    def bet_call(prompt: int, shared: int, out: int, tag: str, cache_as=None) -> Call:
        res.bets += 1
        return Call(sim, server, GRequest(prompt=prompt, out=out, kind="sub", spec=cfg.bet,
                                          early=cfg.bet, claimed=False, shared=shared,
                                          cache_as=cache_as, prog_t=res.t_arrive, tag=tag),
                    client_s, log)

    def keep(c: Call):
        """Wait for a claimed guess; give up on it (False) if the server refused it or
        it made no progress for stall_s (queued or preempted behind other work)."""
        t_claim = sim.now
        while not c.done.triggered:
            yield _first(sim, c.done, sim.timeout(cfg.stall_s / 4))
            if c.done.triggered:
                break
            if sim.now - max(t_claim, c.req.last_tok or 0.0) >= cfg.stall_s:
                c.cancel()
                return False
        return c.done.value == "ok"

    for i, (out, tool_s, hit) in enumerate(plan):
        last = i == len(plan) - 1
        root = None
        if carried is not None:
            if (yield from keep(carried)):
                root = carried
                res.spec_used += 1
            else:
                carried.req.claimed = False  # refused or stalled: re-issued untagged
            carried = None
        cands: list[Call] = []
        if root is None:
            root = root_call(ctx, out, i)
            if cfg.mode == "action" and not last:
                # vLLM caches a request's full blocks when it is scheduled, not when they
                # are computed (kv_cache_manager.allocate_slots), so the root registers
                # ctx (observation included) and each candidate prefills only its suffix
                # plus ctx's partial last block
                own = cfg.cand_suffix + ctx % BLOCK
                cands = [bet_call(own, ctx - ctx % BLOCK, cfg.cand_out,
                                  f"cand:{sid}/{i}/{j}") for j in range(cfg.k)]
            yield root.done
        res.roots.append(root.req)
        ctx += out
        if last:
            break
        # ---- the tool --------------------------------------------------------
        t_tool = sim.now
        res.hits += hit and cfg.mode != "none"
        for j, c in enumerate(cands):
            if hit and j == 0 and c.done.triggered and c.done.value == "ok":
                c.req.claimed = True  # the guessed action's tool started early
                t_tool = min(t_tool, c.req.t_done + client_s)
                res.spec_used += 1
            c.cancel()
        tool_end = t_tool + tool_s
        if cfg.mode == "next":
            guesses = [bet_call(cfg.obs_tokens, ctx, plan[i + 1][0], f"next:{sid}/{i + 1}/{j}",
                                cache_as=sess if hit and j == 0 else None)
                       for j in range(cfg.k)]
            yield sim.at(max(sim.now, tool_end))
            for j, g in enumerate(guesses):
                if hit and j == 0 and not g.refused:
                    g.req.claimed = True  # the guessed observation was right
                    carried = g
                else:
                    g.cancel()
        else:
            yield sim.at(max(sim.now, tool_end))
        ctx += cfg.obs_tokens
    res.t_end = sim.now
    return res


# ----------------------------------------------------------------------------- (b) branch
# Branch-dense code-mode programs: every arm holds literal sub-agent calls, so a
# literal scanner launches both arms while the condition is still being computed.
BRANCH_PROGRAMS: dict[str, str] = {
    "triage": (
        "I will check two conditions on the records and prepare the matching documents for "
        "each outcome.\n"
        "```repl\n"
        "chunks = [context[i:i + {chunk}] for i in range(0, len(context), {chunk})]\n"
        "outage = llm_query('Think step by step, then answer yes or no: do these records "
        "mention an outage?\\n' + chunks[0])\n"
        "if 'yes' in str(outage).lower():\n"
        "    plan = llm_query('Write the outage escalation checklist for the on-call "
        "engineer, ten numbered steps.')\n"
        "    notice = llm_query('Draft a customer-facing outage notice in five sentences.')\n"
        "else:\n"
        "    plan = llm_query('Write the routine weekly support digest outline, ten numbered "
        "items.')\n"
        "    notice = llm_query('Draft a short all-clear note for the support channel in five "
        "sentences.')\n"
        "refunds = llm_query('Think step by step, then answer yes or no: is any record below "
        "a refund request?\\n' + chunks[1])\n"
        "if 'yes' in str(refunds).lower():\n"
        "    policy = llm_query('Write the refund escalation policy summary in eight "
        "bullets.')\n"
        "else:\n"
        "    policy = llm_query('Write the billing FAQ summary in eight bullets.')\n"
        "result = llm_query('Combine into one briefing: ' + str(plan) + ' ' + str(notice) + "
        "' ' + str(policy))\n"
        "```\n"
    ),
}

BRANCH_TOKENS = [
    ("outage escalation checklist", 260),
    ("customer-facing outage notice", 150),
    ("weekly support digest", 240),
    ("all-clear note", 110),
    ("refund escalation policy", 200),
    ("billing faq", 200),
    ("combine into one briefing", 280),
]


def branch_weight(info: CallInfo) -> float:
    h = info.head.lower()
    for key, toks in BRANCH_TOKENS:
        if key in h:
            return float(toks)
    return output_weight(info)


_BRANCH_CACHE: dict = {}


def branch_turns(program: str = "triage", chunk_chars: int = 8000, think: int = 200,
                 trace_chunk: int = 4) -> tuple[TurnSpec, ...]:
    key = (program, chunk_chars, think, trace_chunk)
    if key not in _BRANCH_CACHE:
        ctx = make_context(800)
        body = BRANCH_PROGRAMS[program].replace("{chunk}", str(chunk_chars))
        t1 = compile_turn(PROBE, ctx, TOOLS, chunk=trace_chunk)
        t2 = compile_turn(body, ctx, TOOLS, chunk=trace_chunk,
                          real_locals=t1.notes["real_locals"])
        t3 = compile_turn(FINAL, ctx, TOOLS, chunk=trace_chunk,
                          real_locals=t2.notes["real_locals"])
        _BRANCH_CACHE[key] = (TurnSpec("probe", t1, think, 150),
                              TurnSpec(program, t2, think, 200),
                              TurnSpec("final", t3, think // 2, 20))
    return _BRANCH_CACHE[key]


# ----------------------------------------------------------------------------- (c) batch
@dataclass
class BatchCfg:
    """Offline jobs (eval prompts, document summaries) from a closed-loop pool of
    `workers` clients that runs while the interactive agents do. Sizes are assumptions."""

    workers: int = 16
    prompt: int = 1500
    out: float = 250.0
    out_sigma: float = 0.3
    # how the client tags its jobs and what it does when the server refuses one:
    #   normal   untagged (FCFS)
    #   low      vLLM priority 1 (requeued by vLLM on preemption)
    #   bet      the sptc_vllm bet class: on reject/drop, back off and retry as a bet
    #   reissue  the plugin README's rule for bets: on reject/drop, re-issue untagged
    #   bg       a distinct background class: queued on spare capacity, requeued
    tag: str = "normal"
    backoff: float = 1.0


@dataclass
class BatchStats:
    jobs: int = 0
    out_tokens: int = 0
    rejected: int = 0
    dropped: int = 0
    lat: list = field(default_factory=list)


def batch_worker(sim: Sim, server: Server, cfg: BatchCfg, wid: int, seed: int,
                 client_s: float, stop: Event, stats: BatchStats, log: list):
    """Process: one batch client issuing jobs back to back until `stop` fires."""
    j = 0
    while not stop.triggered:
        out = _len(cfg.out, cfg.out_sigma, seed, wid, j, "bg")
        t0 = sim.now
        tag = cfg.tag
        while not stop.triggered:
            spec = tag in ("low", "bet", "reissue", "bg")
            c = Call(sim, server, GRequest(prompt=cfg.prompt, out=out, kind="sub", spec=spec,
                                           early=spec, bg=tag == "bg", tag=f"bg:{wid}/{j}"),
                     client_s, log)
            yield _first(sim, c.done, stop)
            if not c.done.triggered:
                c.cancel()
                c.req.cut = True  # unfinished at the end of the run: neither used nor wasted
                return
            v = c.done.value
            if v == "ok":
                stats.jobs += 1
                stats.out_tokens += out
                stats.lat.append(sim.now - t0)
                break
            c.req.claimed = False
            stats.rejected += v == "rejected"
            stats.dropped += v == "dropped"
            if tag == "reissue":
                tag = "normal"
            else:
                yield _first(sim, sim.timeout(cfg.backoff), stop)
        j += 1
