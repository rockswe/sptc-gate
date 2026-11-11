"""Replay a compiled turn on the virtual clock under a speculation policy.

Policies
  baseline  wait for the whole response, then run the code; calls block.
  literal   Pydantic `speculate` / pi-fabric: launch calls whose arguments
            are all constants when their closing paren streams; real run
            claims them. No shadow.
  shadow    spec-ptc 0.1.1: one shadow thread runs closed statements in
            order and blocks when a statement reads a pending value
            (head-of-line), plus pre-close loop peeks; a 16-worker pool and a
            120k-char in-flight budget; the real run starts after the
            stream ends AND the shadow finishes.
  dataflow  a "never-stall" shadow: same ops,
            but a statement waits only for earlier statements it conflicts
            with (name-level read/write sets), Multilisp-futures style.

`waste_frac` adds decoy speculations (mispredicted arms / unroll overshoot):
for each real speculative dispatch, a decoy of the same size is launched with
that probability and is evicted at turn end. It is the load knob for Q1.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass, field

from .des import Event, Resource, Sim
from .server import Request, Server
from .trace import CallInfo, TurnTrace

CHARS_PER_TOKEN = 4.0
TEMPLATE_TOKENS = 12  # chat template around a sub-call prompt


def _u01(*parts) -> float:
    h = hashlib.sha1(repr(parts).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def _normal(*parts) -> float:
    u1 = max(_u01(*parts, "a"), 1e-12)
    u2 = _u01(*parts, "b")
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


@dataclass
class OutputModel:
    """Output tokens per sub-call: lognormal around `mean`, capped at `cap`.
    Deterministic in (seed, call identity) -> paired across policies."""

    mean: float = 40.0
    sigma: float = 0.35
    cap: int = 96
    seed: int = 0
    per_tool: dict = field(default_factory=dict)  # tool -> (mean, sigma, cap)
    weight: Callable[[CallInfo], float] | None = None  # relative length by prompt template

    def tokens(self, info: CallInfo, salt: str = "") -> int:
        mean, sigma, cap = self.per_tool.get(info.tool, (self.mean, self.sigma, self.cap))
        if self.weight is not None:
            mean *= self.weight(info)
        mu = math.log(max(mean, 1.0)) - sigma**2 / 2
        x = math.exp(mu + sigma * _normal(self.seed, info.rid, salt))
        return int(max(1, min(cap, round(x))))


@dataclass
class ToolLatency:
    """Non-LLM tools: lognormal through (p50, p99), deterministic per call."""

    p50: float = 0.166
    p99: float = 79.0
    seed: int = 0

    def seconds(self, info: CallInfo, salt: str = "") -> float:
        sigma = math.log(self.p99 / self.p50) / 2.326
        return self.p50 * math.exp(sigma * _normal(self.seed, info.rid, salt, "tool"))


class Backend:
    """How a call turns into time. start() returns a handle with .done."""

    def start(self, info: CallInfo, spec: bool, salt: str = "",
              prog_t: float | None = None, early: bool = False,
              tag_early: bool = True) -> CallHandle:
        """spec: low-priority scheduler class. early: dispatched speculatively
        (its work is wasted unless the real run claims it). tag_early: an early call
        carries its early tag to the server; False: the server sees a normal call
        (PolicyCfg.tag_early)."""
        raise NotImplementedError


@dataclass(eq=False)
class CallHandle:
    done: Event
    info: CallInfo
    spec: bool
    t_start: float
    req: Request | None = None
    cancelled: bool = False
    t_done: float | None = None
    backend: Backend | None = None
    promoted: bool = False
    claimed: bool = False
    rejected: bool = False  # the server refused a bet (no spare capacity)

    @property
    def dropped(self) -> bool:
        """Never produced a result although nobody on the agent side evicted it."""
        return self.rejected or (self.req is not None and self.req.state == "aborted"
                                 and not self.cancelled)

    def cancel(self) -> None:
        if self.cancelled or self.done.triggered:
            return
        self.cancelled = True
        if self.req is not None and self.backend is not None:
            self.backend.server.abort(self.req)  # type: ignore[attr-defined]
        else:
            self.done.succeed(None)

    def promote(self) -> None:
        """The call is now on the critical path: raise its server priority."""
        self.promoted = True
        if self.req is not None and self.backend is not None and self.req.spec:
            self.backend.server.promote(self.req)  # type: ignore[attr-defined]

    def claim(self) -> None:
        """The real run used this result (it is not wasted)."""
        self.claimed = True
        self.promote()
        if self.req is not None:
            self.req.claimed = True


class FixedBackend(Backend):
    """Latency from a function of the call (e.g. spec-ptc's MockLM)."""

    def __init__(self, sim: Sim, latency: Callable[[CallInfo], float]) -> None:
        self.sim = sim
        self.latency = latency

    def start(self, info, spec, salt="", prog_t=None, early=False, tag_early=True):
        h = CallHandle(self.sim.event(), info, spec, self.sim.now)

        def fire():
            if not h.cancelled:
                h.t_done = self.sim.now
                h.done.succeed(h)

        self.sim.call_at(self.sim.now + self.latency(info), fire)
        return h


class ServerBackend(Backend):
    """LLM sub-calls go to the shared Server; other tools sleep a sampled latency."""

    def __init__(self, sim: Sim, server: Server, outputs: OutputModel,
                 tool_latency: ToolLatency | None = None, llm_tools=("llm_query",),
                 client_s: float | None = None) -> None:
        self.sim = sim
        self.server = server
        self.outputs = outputs
        self.tool_latency = tool_latency or ToolLatency()
        self.llm_tools = set(llm_tools)
        self.client_s = server.cost.ov.client_s if client_s is None else client_s
        self.requests: list[Request] = []

    def start(self, info, spec, salt="", prog_t=None, early=False, tag_early=True):
        sim = self.sim
        h = CallHandle(sim.event(), info, spec, sim.now, backend=self)
        if info.tool not in self.llm_tools:
            dt = self.tool_latency.seconds(info, salt)

            def fire():
                if not h.cancelled:
                    h.t_done = sim.now
                    h.done.succeed(h)

            sim.call_at(sim.now + dt, fire)
            return h

        def run():
            yield sim.timeout(self.client_s)
            if h.cancelled:
                return
            srv = self.server
            if spec and srv.cfg.reject_bets and srv.cfg.policy == "agent" \
                    and not h.promoted and not srv.admits_bet_now():
                h.rejected = True
                h.done.succeed(h)
                return
            req = Request(
                prompt=int(info.prompt_chars / CHARS_PER_TOKEN) + TEMPLATE_TOKENS,
                out=self.outputs.tokens(info, salt), kind="sub", spec=spec and not h.promoted,
                tag=info.rid, claimed=h.claimed or not early, prog_t=prog_t,
                early=early and tag_early and not h.promoted,
            )
            h.req = req
            self.requests.append(req)
            yield self.server.submit(req)
            if req.state == "aborted":
                if not h.done.triggered:
                    h.done.succeed(None)
                return
            yield sim.timeout(self.client_s)
            h.t_done = sim.now
            h.done.succeed(h)

        sim.process(run())
        return h


# ---------------------------------------------------------------------------
class ScriptedStream:
    """spec-ptc's SuiteEngine.stream_main: 24-char deltas, one per 6/tps s."""

    def __init__(self, sim: Sim, trace: TurnTrace, tps: float, overshoot: float = 0.0) -> None:
        self.sim = sim
        self.t0 = sim.now
        # overshoot: the host's time.sleep() lateness (measured), for replaying real runs
        self.delay = (trace.chunk / CHARS_PER_TOKEN) / tps + overshoot
        self.n = trace.n_deltas

    def delta(self, k: int) -> Event:
        return self.sim.at(self.t0 + (k + 1) * self.delay)

    def end(self) -> Event:
        return self.delta(self.n - 1)


class ServedStream:
    """The root model decodes the response on the shared server. Delta k
    (chunk chars) is out once token ceil((k+1)*chunk/4) has been emitted."""

    def __init__(self, sim: Sim, trace: TurnTrace, server: Server, prompt_tokens: int,
                 session: object = None, think_tokens: int = 0,
                 prog_t: float | None = None, prefix: tuple[object, int] | None = None
                 ) -> None:
        self.sim = sim
        self.chunk = trace.chunk
        self.n = trace.n_deltas
        self.think = think_tokens
        self.out_tokens = think_tokens + max(1, math.ceil(len(trace.text) / CHARS_PER_TOKEN))
        self._waiters: dict[int, Event] = {}
        self.emitted = 0
        self.req = Request(prompt=prompt_tokens, out=self.out_tokens, kind="root",
                           session=session, on_token=self._on_token, track_itl=True,
                           prog_t=prog_t)
        if prefix is not None:  # (content key, tokens) shared with other sessions' roots
            self.req.prefix_key, self.req.prefix_tokens = prefix
        self.done = server.submit(self.req)

    def _token_for_delta(self, k: int) -> int:
        chars = min((k + 1) * self.chunk, self.n * self.chunk)
        return self.think + max(1, math.ceil(chars / CHARS_PER_TOKEN))

    def _on_token(self, i: int, _t: float) -> None:
        self.emitted = i
        for tok in [t for t in self._waiters if t <= i]:
            self._waiters.pop(tok).succeed()

    def delta(self, k: int) -> Event:
        tok = min(self._token_for_delta(k), self.out_tokens)
        if k >= self.n - 1:
            tok = self.out_tokens
        if self.emitted >= tok:
            return self.sim.timeout(0)
        ev = self._waiters.get(tok)
        if ev is None:
            ev = self._waiters[tok] = self.sim.event()
        return ev

    def end(self) -> Event:
        return self.done


# ---------------------------------------------------------------------------
@dataclass
class PolicyCfg:
    name: str = "shadow"
    max_inflight: int = 16  # spec-ptc pool
    char_budget: int = 120_000  # spec-ptc in-flight argument chars
    literal_conc: int | None = None  # pi-fabric: 4
    stmt_overhead: float = 0.0005  # shadow parse + exec of one statement
    exec_overhead: float = 0.0  # real run fixed cost
    batched_workers: int = 8
    waste_frac: float = 0.0
    label_noise: float = 0.0  # P(scheduler label flips): certain<->bet
    decoys_bypass_pool: bool = False  # decoys outside spec-ptc's pool (as kaggle/vllm_bench.py)
    # server hints (only the agent-aware scheduler reads them):
    #   mark_spec "all": every early dispatch is low priority until the real run claims it
    #   mark_spec "guesses": only bets are low priority (literal launches, which may sit in
    #   an untaken arm, and decoys). Shadow dispatches come from closed statements and
    #   loop peeks are retracted only on mutation/early exit, so both count as certain.
    mark_spec: str = "all"
    promote_early: bool = False  # promote when the shadow adopts or forces a speculation
    # the speculative calls that are not bets: True sends them tagged early (the plugin's
    # early class, which shares the prefill allowance); False sends them untagged, so only
    # bets carry a class (the best-effort class as the drafted RFC had it)
    tag_early: bool = True
    # the shadow forces a speculation the server refused or dropped (a bet that was needed):
    #   reissue  re-run it at once as certain work; the shadow goes on
    #   abort    as spec-ptc with the sptc-hints patch: the shadow stops for the rest of the
    #            turn (shadow.py _abort("force-failed")), the real run re-runs the call when
    #            it claims it, and runs the calls the shadow never dispatched as misses.
    #            Shadow policy only
    rejected_force: str = "reissue"
    # a decoy starts inside its real call's worker (after spec-ptc's pool and char budget),
    # just before the real call, as kaggle/vllm_bench.py's LoggedEngine.call starts it; so a
    # gate sees decoy and real call by pairs. False: at dispatch, so a burst's decoys all
    # reach a gate before its real calls (every result before the pressure study). Needs
    # decoys_bypass_pool (the bench's decoys are threads outside spec-ptc's pool)
    decoy_at_call: bool = False

    def __post_init__(self) -> None:
        if self.rejected_force not in ("reissue", "abort"):
            raise ValueError(f"rejected_force {self.rejected_force!r}")
        if self.rejected_force == "abort" and self.name == "dataflow":
            raise ValueError("rejected_force 'abort' models spec-ptc's single shadow thread")
        if self.decoy_at_call and not self.decoys_bypass_pool:
            raise ValueError("decoy_at_call needs decoys_bypass_pool")


@dataclass
class TurnResult:
    policy: str
    t_start: float
    stream_end: float = 0.0
    shadow_done: float = 0.0
    exec_start: float = 0.0
    t_end: float = 0.0
    hits: int = 0
    misses: int = 0
    evicted: int = 0
    decoys: int = 0
    reissued: int = 0
    dispatched: int = 0
    shadow_stop: int | None = None  # rejected_force abort: the seq whose force stopped it
    call_lat: list = field(default_factory=list)
    leads: list = field(default_factory=list)

    @property
    def wall(self) -> float:
        return self.t_end - self.t_start

    @property
    def exec_s(self) -> float:
        return self.t_end - self.exec_start


class _CharBudget:
    def __init__(self, sim: Sim, cap: int) -> None:
        self.sim, self.cap, self.used, self.q = sim, cap, 0, []

    def acquire(self, n: int) -> Event:
        n = min(n, self.cap)
        ev = self.sim.event()
        if self.used + n <= self.cap and not self.q:
            self.used += n
            ev.succeed(n)
        else:
            self.q.append((n, ev))
        return ev

    def release(self, n: int) -> None:
        self.used -= n
        while self.q and self.used + self.q[0][0] <= self.cap:
            m, ev = self.q.pop(0)
            self.used += m
            ev.succeed(m)


def run_turn(sim: Sim, trace: TurnTrace, policy: PolicyCfg, backend: Backend,
             stream, salt: str = "", prog_t: float | None = None):
    """Process: replay one turn; returns TurnResult. prog_t: agent program start."""
    res = TurnResult(policy.name, sim.now)
    prog_t = sim.now if prog_t is None else prog_t
    name = policy.name
    pool = Resource(sim, policy.max_inflight)
    chars = _CharBudget(sim, policy.char_budget)
    handles: dict[int, CallHandle] = {}
    dispatched: dict[int, Event] = {}
    done_ev: dict[int, Event] = {}
    evicted: set[int] = set()
    decoys: list[str] = []
    end_ev = stream.end()

    def sev(table: dict, seq: int) -> Event:
        ev = table.get(seq)
        if ev is None:
            ev = table[seq] = sim.event()
        return ev

    early: set[int] = set()  # seqs the shadow adopted or forced before a worker started
    claimed_early: set[int] = set()
    infos: dict = {}
    reissued: dict = {}

    def ensure(seq, is_claim: bool, stop: bool = False):
        """Wait for a speculation's result. If the server dropped it (a suppressed bet
        that turned out to be needed), re-issue it now as certain work, once; or, with
        stop (rejected_force abort, at a force), stop the shadow instead. True: stopped."""
        yield sev(done_ev, seq)
        h = handles.get(seq)
        if h is None or not h.dropped:
            return False
        if stop:
            res.shadow_stop = seq
            return True
        if seq not in reissued:
            res.reissued += 1
            reissued[seq] = sim.process(call_now(infos[seq]))
        if is_claim:
            res.hits -= 1
            res.misses += 1
        yield reissued[seq]

    def is_bet(source: str, rid: str) -> bool:
        """Scheduler label. 'guesses' labels decoys and literal launches as bets; with
        label_noise, each label flips with that probability (an imperfect classifier)."""
        if policy.mark_spec == "all":
            return True
        bet = source in ("literal", "decoy")
        if policy.label_noise and _u01(salt, "label", rid) < policy.label_noise:
            bet = not bet
        return bet

    def start_call(seq, info: CallInfo, bet: bool) -> CallHandle:
        h = backend.start(info, spec=bet, salt=salt, prog_t=prog_t, early=True,
                          tag_early=bet or policy.tag_early)
        handles[seq] = h
        if seq in early:
            h.promote()
        if seq in claimed_early:
            h.claim()
        return h

    def follow(seq, h: CallHandle):
        """A decoy its real call's worker started (decoy_at_call)."""
        yield h.done
        sev(done_ev, seq).succeed(h)

    def worker(seq, info: CallInfo, gated: Resource | None, use_chars: bool, bet: bool,
               t_disp: float, real: bool, decoy: tuple | None = None):
        """One speculation's lifetime (spec-ptc Launcher.dispatch.run): pool slot,
        argument-char budget, the call itself; eviction is honored at every wait.
        decoy: (key, CallInfo), started here just before the call (decoy_at_call)."""
        if gated is not None:
            yield gated.acquire()
        n = 0
        if use_chars and seq not in evicted:
            n = yield chars.acquire(info.prompt_chars)
        if seq in evicted:
            if use_chars:
                chars.release(n)
            if gated is not None:
                gated.release()
            sev(done_ev, seq).succeed(None)
            return
        if decoy is not None:  # its thread starts first, so it reaches a gate first
            sim.process(follow(decoy[0], start_call(decoy[0], decoy[1],
                                                    is_bet("decoy", decoy[1].rid))))
        h = start_call(seq, info, bet)
        yield h.done
        if use_chars:
            chars.release(n)
        if gated is not None:
            gated.release()
        if real and h.t_done is not None:
            res.call_lat.append(h.t_done - t_disp)  # spec-ptc 'ready' ms: from dispatch
        sev(done_ev, seq).succeed(h)

    def launch(seq: int, info: CallInfo, gated: Resource | None, use_chars: bool,
               source: str = "shadow"):
        infos[seq] = info
        sev(dispatched, seq).succeed()
        res.dispatched += 1
        # decoy: a wrong guess the same size, through the same pool and budgets
        # (spec-ptc's 64-dispatch cap included); never claimed, evicted at turn end
        decoy = None
        if (policy.waste_frac > 0 and res.dispatched + res.decoys < 64
                and _u01(salt, "decoy", info.rid) < policy.waste_frac):
            decoy = (f"decoy:{seq}",
                     CallInfo(info.tool, info.rid + "~decoy", info.prompt_chars, head=info.head))
            decoys.append(decoy[0])
            res.decoys += 1
        sim.process(worker(seq, info, gated, use_chars, is_bet(source, info.rid), sim.now,
                           True, decoy if policy.decoy_at_call else None))
        if decoy is None or policy.decoy_at_call:
            return
        key, d = decoy
        if policy.decoys_bypass_pool:
            sim.process(worker(key, d, None, False, is_bet("decoy", d.rid), sim.now, False))
        else:
            sim.process(worker(key, d, gated, use_chars, is_bet("decoy", d.rid), sim.now,
                               False))

    def promote_seq(seq: int) -> None:
        early.add(seq)
        h = handles.get(seq)
        if h is not None:
            h.promote()

    def evict(seq: int) -> None:
        evicted.add(seq)
        res.evicted += 1
        h = handles.get(seq)
        if h is not None:
            h.cancel()

    def run_ops(ops, wait_dispatch: bool):
        for op in ops:
            if res.shadow_stop is not None:
                return  # rejected_force abort: the rest of the statement never runs
            kind = op[0]
            if kind == "dispatch":
                rec = trace.specs[op[1]]
                launch(op[1], rec.call, pool, True, rec.source)
            elif kind == "force":
                if wait_dispatch:
                    yield sev(dispatched, op[1])
                if policy.promote_early:
                    promote_seq(op[1])
                if (yield from ensure(op[1], is_claim=False,
                                      stop=policy.rejected_force == "abort")):
                    return
            elif kind == "adopt":
                if wait_dispatch:
                    yield sev(dispatched, op[1])
                if policy.promote_early:
                    promote_seq(op[1])
            elif kind == "evict":
                evict(op[1])

    def call_now(info: CallInfo, spec=False):
        h = backend.start(info, spec=spec, salt=salt, prog_t=prog_t)
        yield h.done
        if h.t_done is not None:
            res.call_lat.append(h.t_done - h.t_start)

    def batch_now(infos):
        workers = Resource(sim, policy.batched_workers)

        def one(i):
            yield workers.acquire()
            yield from call_now(i)
            workers.release()

        yield sim.all_of([sim.process(one(i)) for i in infos])

    def real_exec(ops, claims: bool):
        res.exec_start = sim.now
        if policy.exec_overhead:
            yield sim.timeout(policy.exec_overhead)
        for op in ops:
            kind = op[0]
            if kind == "force" and claims and res.shadow_stop is not None \
                    and op[1] not in infos:
                # the shadow stopped before dispatching it: a claim miss, run for real
                res.misses += 1
                yield from call_now(trace.specs[op[1]].call)
            elif kind == "force" and claims:
                seq = op[1]
                res.hits += 1
                claimed_early.add(seq)
                h = handles.get(seq)
                if h is not None:
                    h.claim()
                yield from ensure(seq, is_claim=True)
            elif kind == "run":
                res.misses += claims
                yield from call_now(op[1])
            elif kind == "batch":
                res.misses += len(op[1]) * claims
                yield from batch_now(op[1])

    # ------------------------------------------------------------------ main
    if name == "baseline":
        yield end_ev
        res.stream_end = res.shadow_done = sim.now
        yield from real_exec(trace.base_exec, claims=False)

    elif name == "literal":
        lit_pool = Resource(sim, policy.literal_conc) if policy.literal_conc else None

        def literal_launcher():
            for rec, avail in trace.literal_specs:
                yield stream.delta(trace.delta_of_char(avail))
                launch(rec.seq, rec.call, lit_pool, False, "literal")

        lp = sim.process(literal_launcher())
        yield end_ev
        res.stream_end = res.shadow_done = sim.now
        yield lp
        yield from real_exec(trace.literal_exec, claims=True)
        for seq in trace.literal_end_evict:
            evict(seq)

    elif name == "shadow":

        def shadow():
            for it in trace.items:
                if res.shadow_stop is not None:
                    break  # spec-ptc skips every later segment and peek of the turn
                yield stream.delta(trace.delta_of_char(it.avail_char))
                yield sim.timeout(policy.stmt_overhead)
                yield from run_ops(it.ops, wait_dispatch=False)

        sp = sim.process(shadow())
        yield end_ev
        res.stream_end = sim.now
        if trace.shadow_join:
            yield sp
        res.shadow_done = sim.now
        yield from real_exec(trace.spec_exec, claims=True)
        for seq in trace.spec_end_evict:
            evict(seq)

    elif name == "dataflow":
        procs = []
        for j, it in enumerate(trace.items):
            deps = []
            for i in range(j):
                a = trace.items[i]
                if a.kind != "stmt":
                    continue
                if "*" in a.writes or "*" in it.writes or (a.writes & (it.reads | it.writes)) or (
                    a.reads & it.writes
                ):
                    deps.append(procs[i])

            def item_proc(it=it, deps=deps):
                yield stream.delta(trace.delta_of_char(it.avail_char))
                if deps:
                    yield sim.all_of(deps)
                yield sim.timeout(policy.stmt_overhead)
                yield from run_ops(it.ops, wait_dispatch=True)

            procs.append(sim.process(item_proc()))
        yield end_ev
        res.stream_end = sim.now
        if trace.shadow_join and procs:
            yield sim.all_of(procs)
        res.shadow_done = sim.now
        yield from real_exec(trace.spec_exec, claims=True)
        for seq in trace.spec_end_evict:
            evict(seq)
    else:
        raise ValueError(name)

    for key in decoys:
        evict(key)
        res.evicted -= 1  # decoy evictions are counted in res.decoys
    res.t_end = sim.now
    return res
