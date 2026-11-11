"""A vLLM-V1-style continuous-batching server on the virtual clock.

Modeled: iteration-level scheduling with a token budget (chunked prefill),
running-before-waiting order, a paged KV cache with a block-level capacity,
recompute preemption, an LRU prefix cache that can keep an agent's context
across tool gaps (or a TTL pin, Continuum-style, or no cache), request abort
(speculation eviction), and four scheduling policies (below).

KV semantics follow vLLM 0.32 by default (ServerConfig.full_isl, resume_from_cache,
cache_freed_blocks, and content-shared prefixes via Request.prefix_key): whole-sequence
admission, a preempted request finds its own blocks in the prefix cache on resume,
one LRU queue for every freed full block, one copy of a shared system prompt. Results
before 2026-10-20 used LEGACY_KV; results/corrections/corrections.md has both.

  fcfs      vLLM default: arrival order, newest running request is preempted.
  priority  idealized strict priority: root decode > claimed / normal sub-calls >
            speculative sub-calls, for the token budget too; lowest class is
            preempted first. Not what vLLM does (see vllm-priority).
  vllm-priority  vLLM 0.32 --scheduling-policy priority with speculative requests
            sent at a larger priority value (root and normal calls 0, spec 1):
            waiting is ordered by (priority, arrival); running keeps admission
            order (the token budget is not reordered); the victim is
            max(running, key=(priority, arrival)); a waiting request never
            preempts; no promotion. results/sweep_prep/vllm_priority_semantics.md.
  agent     program-level FCFS (oldest agent session first) with speculative
            bets behind all certain work, plus PASTE-style bounded capacity
            for bets: admitted only while few requests run and KV has a
            reserve, with a per-step prefill allowance; claimed or adopted
            bets are promoted.
  agent with plugin_semantics: what the sptc_vllm plugin actually does (see
            ServerConfig.plugin_semantics).

Not modeled: CUDA-graph batch padding, speculative decoding, multi-step
scheduling, swap preemption, tensor-parallel communication, detokenizer
back-pressure. Each would shift constants, not the shape of the results.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from .des import Event, Sim
from .hardware import StepCost

BLOCK = 16

PRIO_ROOT, PRIO_NORMAL, PRIO_SPEC = 0, 1, 2


@dataclass(eq=False)
class Request:
    prompt: int
    out: int
    kind: str = "sub"  # root | sub
    spec: bool = False  # low-priority speculative class (scheduler hint): a bet
    early: bool = False  # dispatched ahead of the real run (certain or not)
    claimed: bool = True  # the real run used the result (False -> wasted work)
    prog_t: float | None = None  # start time of the agent program it belongs to
    session: object = None  # prefix-cache key (root turns of one agent)
    # a leading segment whose text other requests share (e.g. a common system prompt):
    # one cached copy by content, as vLLM's hashed blocks. Whole blocks only.
    prefix_key: object = None
    prefix_tokens: int = 0
    on_token: Callable[[int, float], None] | None = None
    track_itl: bool = False
    tag: str = ""
    # -- state (server-owned) --
    rid: int = -1
    arrival: float = 0.0
    priority: int = PRIO_NORMAL
    need_prefill: int = 0
    ctx: int = 0
    generated: int = 0
    blocks: int = 0
    state: str = "new"  # waiting | running | done | aborted
    cached: int = 0
    hit_tokens: int = 0  # prefix-cache hit at first admission (kept across preemption)
    shared_blocks: int = 0  # blocks of the shared prefix it reads (not in `blocks`)
    prefix_looked: bool = False
    preemptions: int = 0
    t_sched: float | None = None
    t_first: float | None = None
    t_done: float | None = None
    last_tok: float | None = None
    itl: list = field(default_factory=list)
    computed_tokens: int = 0  # all tokens run through the model (incl. recompute)
    done: Event | None = None

    @property
    def ttft(self) -> float:
        return (self.t_first or math.nan) - self.arrival

    @property
    def tpot(self) -> float:
        if self.t_first is None or self.t_done is None or self.out <= 1:
            return math.nan
        return (self.t_done - self.t_first) / (self.out - 1)


@dataclass
class CacheEntry:
    tokens: int  # absolute: the entry covers tokens [base, tokens) of its sequence
    blocks: int
    last_used: float
    pinned_until: float = -1.0
    base: int = 0  # tokens before this entry that live in a shared prefix entry
    dead: bool = False  # freed blocks nobody will look up again (vLLM still caches them)


class KVCache:
    """Block accounting: free blocks + evictable prefix-cache entries (LRU).

    vLLM 0.32 keeps one free-block queue: blocks without a hash are put at its head and
    reused first, freed blocks with a hash go to its tail, and allocation pops the head
    (block_pool.py:774-803, get_new_blocks 666-698). So: plain free blocks first, then
    cached blocks oldest-freed first, tail blocks of a sequence before its head
    (kv_cache_manager.free, 620-629). `entries` is kept in that order: every insert
    is at the current time, so insertion order is LRU order.

    Shared prefixes (`acquire_prefix`): one copy of a prefix that many requests read,
    with a reference count, as vLLM's content-hashed blocks (kv_cache_manager.py:295-299,
    block_pool.touch 752-768). While referenced it is not evictable; at zero references
    it becomes an ordinary LRU entry under ("prefix", key)."""

    def __init__(self, total_blocks: int) -> None:
        self.total = total_blocks
        self.free = total_blocks
        self.entries: dict[object, CacheEntry] = {}
        self.evicted_tokens = 0
        self.cached = 0  # blocks held by entries
        self._pins = False  # any TTL pin ever set (only then is headroom O(entries))
        # shared prefix key -> [blocks, refs, pinned_until]: a TTL pin on a context that
        # reads the prefix pins the prefix too (it is part of that context)
        self.active: dict[object, list] = {}

    def _evictable(self, now: float) -> list[tuple[object, CacheEntry]]:
        if not self._pins:
            return list(self.entries.items())
        return [(k, e) for k, e in self.entries.items() if e.pinned_until < now]

    def headroom(self, now: float) -> int:
        if not self._pins:
            return self.free + self.cached
        return self.free + sum(e.blocks for e in self.entries.values() if e.pinned_until < now)

    def allocate(self, n: int, now: float) -> bool:
        if n <= self.free:
            self.free -= n
            return True
        if n > self.headroom(now):
            return False
        for k, e in self._evictable(now):
            if n <= self.free:
                break
            take = min(e.blocks, n - self.free)
            # trim from the tail: a prefix stays usable
            e.blocks -= take
            self.cached -= take
            if not e.dead:
                self.evicted_tokens += min(e.tokens - e.base, take * BLOCK)
            e.tokens = min(e.tokens, e.base + e.blocks * BLOCK)
            self.free += take
            if e.blocks == 0:
                del self.entries[k]
        self.free -= n
        return True

    def release(self, n: int) -> None:
        self.free += n

    def pop(self, key: object) -> CacheEntry | None:
        """Remove an entry; its blocks become the caller's (not freed)."""
        e = self.entries.pop(key, None)
        if e is not None:
            self.cached -= e.blocks
        return e

    def put(self, key: object, tokens: int, blocks: int, now: float, pin_until: float,
            base: int = 0, dead: bool = False) -> None:
        """Cache `blocks` the caller holds (they stop being the caller's)."""
        old = self.pop(key)
        if old is not None:
            self.free += old.blocks
        if blocks <= 0:
            return
        if pin_until >= 0:
            self._pins = True
        self.entries[key] = CacheEntry(tokens, blocks, now, pin_until, base, dead)
        self.cached += blocks

    def take(self, key: object, prompt: int, base: int = 0) -> tuple[int, int]:
        """Claim a cached prefix for a request of `prompt` tokens that already has `base`
        tokens from a shared prefix: (hit tokens, blocks moved). At most prompt - 1 tokens
        hit (vLLM recomputes the last one for logits), in whole blocks. An entry that
        does not continue at `base` is left alone (vLLM's hash chain breaks there)."""
        e = self.entries.get(key)
        if e is None or e.base != base:
            return 0, 0
        self.pop(key)
        hit = min(e.tokens, prompt - 1)
        hit_blocks = max(0, hit // BLOCK - base // BLOCK)
        self.free += e.blocks - hit_blocks
        return hit_blocks * BLOCK, hit_blocks

    # -- shared prefixes ---------------------------------------------------------------
    def prefix_blocks(self, key: object) -> int:
        a = self.active.get(key)
        if a is not None:
            return a[0]
        e = self.entries.get(("prefix", key))
        return e.blocks if e is not None else 0

    def acquire_prefix(self, key: object, create: bool = False) -> int:
        """Take a reference on shared prefix `key`: its block count (0 and no reference
        when there is none, unless `create`)."""
        a = self.active.get(key)
        if a is None:
            e = self.pop(("prefix", key))
            if e is None and not create:
                return 0
            a = self.active[key] = [e.blocks, 0, e.pinned_until] if e is not None else [0, 0, -1.0]
        a[1] += 1
        return a[0]

    def grow_prefix(self, key: object, blocks: int) -> None:
        """A holder's own computed blocks extend the shared prefix (it keeps reading them)."""
        self.active[key][0] += blocks

    def release_prefix(self, key: object, now: float, pin_until: float = -1.0) -> None:
        a = self.active[key]
        a[1] -= 1
        a[2] = max(a[2], pin_until)
        if a[1] == 0:
            del self.active[key]
            self.put(("prefix", key), a[0] * BLOCK, a[0], now, a[2] if a[2] >= now else -1.0)

    @property
    def used(self) -> int:
        return self.total - self.free


@dataclass
class ServerConfig:
    max_num_seqs: int = 1024  # vLLM V1 online default on >=70 GiB GPUs (H100)
    max_batched_tokens: int = 8192  # same; 2048 on smaller GPUs
    policy: str = "fcfs"  # fcfs | priority | vllm-priority | agent
    kv_policy: str = "lru"  # lru | pin | none
    pin_ttl: float = 10.0
    kv_blocks: int | None = None  # override capacity (None: derive from GPU memory)
    # agent policy knobs (PASTE-style bounded, opportunistic speculative capacity)
    # spare capacity = inside the free-ride window (Q2): admit spec work only while one
    # more decoding sequence keeps the step under spec_knee x the batch-1 step
    spec_knee: float = 1.5
    spec_max_running: int = 10**9  # optional hard cap on running spec requests
    free_window: int | None = None  # sptc_vllm plugin's gate: running + 1 <= free_window
    spec_prefill_budget: int = 512  # total spec prefill tokens per step (protects root ITL)
    # when the allowance applies (the plugins' prefill_allowance knob):
    #   fixed     every step (the plugins' behaviour before the knob existed)
    #   adaptive  only in a step that starts with a more certain stream decoding: a bet
    #             yields to any non-bet decoder, early work only to an untagged one
    #   off       never (same as spec_prefill_budget <= 0)
    spec_prefill_mode: str = "fixed"
    spec_kv_reserve: float = 0.10  # keep this fraction of KV free of speculative work
    spec_max_wait: float = 2.0  # aging: spec work waiting this long becomes normal (inf: never)
    reject_bets: bool = False  # suppress bets: refuse at submit without spare capacity,
    #                            drop (not requeue) when preempted
    # agent policy as the sptc_vllm plugin implements it, where that differs from the
    # idealized policy above: plain FCFS with bets last (not program-level FCFS), no
    # promotion, no eviction of running bets for waiting work, no gate at submit, and (with
    # reject_bets) a waiting bet that fails the gate is rejected in the same step; one that
    # passes but is not admitted is held for at most bet_hold_steps steps.
    plugin_semantics: bool = False
    bet_hold_steps: int = 16
    # the plugin model follows the vLLM adapter after its audit fixes:
    #   #2   a running bet's prefill leaves the allowance that waiting early prefills need
    #   #10  a held step is not counted when the bet was skipped for the allowance while
    #        another bet's prefill used it
    #   #25  a step that schedules no tokens is not counted either
    # False: the adapter before those fixes (what results/prereg_v2 modelled). Applies to
    # plugin_semantics and to GeneralServer's plugin policy.
    plugin_fixes: bool = True
    # agent + reject_bets, where the bet gate runs (audit #45): "submit" (the idealized
    # policy of the report: refused at submit, when the real call issued with it is still
    # waiting, so every decoy is refused by its own sibling) or "schedule" (as the plugin:
    # in the waiting loop, after the certain work ahead of it, then re-gated and held).
    # plugin_semantics implies "schedule".
    bet_gate: str = "submit"
    # vLLM 0.32 KV semantics (2026-10-20). All three are on by default; results
    # before that used LEGACY_KV (all off). See results/corrections/corrections.md.
    #   full_isl            scheduler_reserve_full_isl (config/scheduler.py:190, default
    #                       True): a waiting or preempted request is admitted only if its
    #                       whole sequence fits in free + evictable blocks, not just this
    #                       step's chunk (kv_cache_manager.py:518-538, scheduler.py:1270)
    #   resume_from_cache   a preempted request's full blocks stay in the prefix cache and
    #                       it looks them up again on resume (scheduler.py:960-967:
    #                       num_computed_tokens == 0 after _preempt_request, 1593)
    #   cache_freed_blocks  every freed full block keeps its hash and joins the one LRU
    #                       free queue (block_pool.py:774-803): finished or aborted
    #                       sub-calls' blocks are evicted in free order with the roots'
    #                       cached contexts, not before them. Partial blocks are freed.
    # SPTC_LEGACY_KV=1 in the environment turns all three off by default (explicit values
    # still win), so scripts without a --legacy-sim switch can regenerate their committed
    # results from before the KV fixes: SPTC_LEGACY_KV=1 python experiments/general.py ...
    full_isl: bool = field(default_factory=lambda: not legacy_kv_env())
    resume_from_cache: bool = field(default_factory=lambda: not legacy_kv_env())
    cache_freed_blocks: bool = field(default_factory=lambda: not legacy_kv_env())

    def __post_init__(self) -> None:
        if self.spec_prefill_mode not in ("fixed", "adaptive", "off", "adaptive_u"):
            raise ValueError(f"spec_prefill_mode {self.spec_prefill_mode!r}")
        if self.bet_gate not in ("submit", "schedule"):
            raise ValueError(f"bet_gate {self.bet_gate!r}")


# the KV model every result before the KV fixes used: admit on the first chunk, recompute
# preempted requests from scratch, freed sub-call blocks reused before any cached context
LEGACY_KV = {"full_isl": False, "resume_from_cache": False, "cache_freed_blocks": False}


def legacy_kv_env() -> bool:
    """SPTC_LEGACY_KV set (and not "0"): ServerConfig defaults to LEGACY_KV. Workloads are
    unaffected: run_session's sys_share already defaults to "session" (private prompts)."""
    return os.environ.get("SPTC_LEGACY_KV", "0") not in ("", "0")


class Server:
    def __init__(self, sim: Sim, cost: StepCost, cfg: ServerConfig | None = None) -> None:
        self.sim = sim
        self.cost = cost
        self.cfg = cfg or ServerConfig()
        blocks = self.cfg.kv_blocks or cost.kv_capacity_tokens() // BLOCK
        self.kv = KVCache(blocks)
        self.waiting: list[Request] = []
        self.running: list[Request] = []
        self._wake: Event | None = None
        self._rid = 0
        self.finished: list[Request] = []
        self.aborted: list[Request] = []
        self.steps = 0
        self.busy_time = 0.0
        self.step_log: list[tuple[float, float, int, int, int]] = []  # t, dt, seqs, tokens, kv
        self.log_steps = False
        self._floor = cost.decode_step(1, 0)
        self._n_new = 0
        self._spec_left = 0
        self._preempted_all = False
        self._room = None
        self._held: dict[int, int] = {}  # plugin_semantics: waiting bet rid -> steps held
        self.bets_rejected = 0  # plugin_semantics: bets rejected while waiting
        self.allowance_steps = 0  # steps in which the allowance cut or skipped a request
        self._cut = False
        self._protect: tuple[bool, bool] | None = None
        # plugin_fixes, per step: allowance kept for waiting early prefill (#2), the early
        # requests it was kept for, bets skipped for the allowance and whether a bet
        # prefilled (#10); across steps: early requests kept for but not admitted
        self._early_need: int | None = None
        self._kept_for: list[Request] = []
        self._early_cut = False
        self._early_unadmitted: dict[int, Request] = {}
        self._allow_skipped: set[int] = set()
        self._bet_prefilled = False
        self.full_isl = self.cfg.full_isl
        sim.process(self._loop())

    # -- client API ------------------------------------------------------------
    def submit(self, r: Request) -> Event:
        self._rid += 1
        r.rid = self._rid
        r.arrival = self.sim.now
        r.done = self.sim.event()
        r.need_prefill = r.prompt
        r.priority = PRIO_ROOT if r.kind == "root" else (PRIO_SPEC if r.spec else PRIO_NORMAL)
        r.state = "waiting"
        self.waiting.append(r)
        if self._wake is not None:
            self._wake.succeed()
            self._wake = None
        return r.done

    def _key(self, r: Request) -> object:
        """Its cache entry: the session's context for a root, its own blocks otherwise."""
        return r.session if r.session is not None else ("req", r.rid)

    def _attach_prefix(self, r: Request) -> None:
        """vLLM looks up cached prefix blocks when it schedules a request whose
        num_computed_tokens is 0: a new one, or (resume_from_cache) a preempted one."""
        r.prefix_looked = True
        if self.cfg.kv_policy == "none":
            return
        tokens = r.prompt + r.generated  # vLLM request.num_tokens
        base = 0
        if r.prefix_key is not None:
            want = min(r.prefix_tokens // BLOCK, (tokens - 1) // BLOCK)
            if want > 0:
                have = self.kv.acquire_prefix(r.prefix_key)
                r.shared_blocks = min(have, want)
                base = r.shared_blocks * BLOCK
        if r.session is None and not (r.preemptions and self.cfg.resume_from_cache):
            hit, blocks = 0, 0
        else:
            hit, blocks = self.kv.take(self._key(r), tokens, base)
        r.blocks = blocks
        r.cached = r.ctx = base + hit
        if r.preemptions == 0:
            r.hit_tokens = r.ctx
        r.need_prefill = tokens - r.ctx

    def _drop_prefix_ref(self, r: Request, pin: float = -1.0) -> None:
        if r.shared_blocks:
            self.kv.release_prefix(r.prefix_key, self.sim.now, pin)
            r.shared_blocks = 0

    def _detach_prefix(self, r: Request) -> None:
        """Not admitted after all: hand the cached prefix back to the cache."""
        if r.blocks:
            self.kv.put(self._key(r), r.ctx, r.blocks, self.sim.now, -1.0,
                        base=r.shared_blocks * BLOCK)
        self._drop_prefix_ref(r)
        r.cached = r.ctx = r.blocks = 0
        if r.preemptions == 0:
            r.hit_tokens = 0
        r.need_prefill = r.prompt + r.generated
        r.prefix_looked = False

    def _cache_blocks(self, r: Request, key: object, pin: float = -1.0) -> None:
        """r frees its blocks (cache_freed_blocks): full ones stay cached under `key`,
        tail first in eviction order (one entry, trimmed from its tail); the partial last
        block, which has no hash, is freed. Then its shared prefix reference."""
        full = max(0, r.ctx // BLOCK - r.shared_blocks)
        full = min(full, r.blocks)
        self.kv.release(r.blocks - full)
        self.kv.put(key, r.shared_blocks * BLOCK + full * BLOCK, full, self.sim.now, pin,
                    base=r.shared_blocks * BLOCK,
                    dead=isinstance(key, tuple) and key[:1] == ("dead",))
        r.blocks = 0
        self._drop_prefix_ref(r, pin)

    def _publish_prefix(self, r: Request) -> None:
        """r has computed its shared prefix: from now on there is one copy, as vLLM
        caches each full block when it is computed. Blocks r computed that the shared
        copy already holds are dropped (r reads the shared ones); blocks that extend it
        move into it. Approximation: vLLM would keep r's duplicate until r frees it."""
        sb = r.prefix_tokens // BLOCK
        have = r.shared_blocks
        eb = self.kv.prefix_blocks(r.prefix_key)
        if have == 0:
            eb = self.kv.acquire_prefix(r.prefix_key, create=True)
        dup = max(0, min(eb, sb) - have)
        grow = max(0, sb - max(eb, have))
        r.blocks -= dup + grow
        self.kv.release(dup)
        self.kv.grow_prefix(r.prefix_key, grow)
        r.shared_blocks = sb

    def _in_free_window(self, extra: list[Request] = (), new_ctx: int = 2048) -> bool:
        """Would one more decoding sequence keep the decode step inside the free-ride
        window? Prefill is excluded: it is capped separately (spec_prefill_budget)."""
        seqs = self.running + list(extra)
        if self.cfg.free_window is not None:  # the vLLM plugin's sequence-count gate
            return len(seqs) + 1 <= self.cfg.free_window
        if not seqs:
            return True
        items = [(1, r.ctx) for r in seqs] + [(1, new_ctx)]
        mean_ctx = sum(c for _, c in items) // len(items)
        return self.cost.step_time(items) <= self.cfg.spec_knee * self.cost.decode_step(1, mean_ctx)

    def admits_bet_now(self) -> bool:
        """Spare capacity right now: no certain work waiting, inside the free-ride
        window, under the spec cap, and a KV reserve left. With plugin_semantics there is
        no gate at submit: the plugin gates a bet when its waiting loop reaches it, after
        the certain work queued with it (_schedule)."""
        if self.cfg.plugin_semantics or self.cfg.bet_gate == "schedule":
            return True
        if any(w.priority < PRIO_SPEC for w in self.waiting):
            return False
        if sum(r.priority == PRIO_SPEC for r in self.running) >= self.cfg.spec_max_running:
            return False
        if not self._in_free_window():
            return False
        return self.kv.headroom(self.sim.now) >= self.cfg.spec_kv_reserve * self.kv.total

    def promote(self, r: Request) -> None:
        """A speculation was claimed: it is now on the critical path. The plugin has no
        promotion (a request keeps its tag), so with plugin_semantics this does nothing."""
        if self.cfg.plugin_semantics:
            return
        if self.cfg.policy == "vllm-priority":
            return  # vLLM has no API to change a queued or running request's priority
        r.spec = False
        r.early = False  # on the critical path now: no prefill throttle
        if r.priority == PRIO_SPEC:
            r.priority = PRIO_NORMAL

    def abort(self, r: Request) -> None:
        self._held.pop(r.rid, None)
        if r.state == "waiting":
            self.waiting.remove(r)
        elif r.state == "running":
            self.running.remove(r)
        else:
            return
        if self.cfg.cache_freed_blocks and self.cfg.kv_policy != "none":
            self._cache_blocks(r, ("dead", r.rid))
        else:
            self.kv.release(r.blocks)
            self._drop_prefix_ref(r)
        r.blocks = 0
        r.state = "aborted"
        r.t_done = self.sim.now
        self.aborted.append(r)
        r.done.succeed(r)

    # -- scheduling ------------------------------------------------------------
    def _order(self, r: Request) -> tuple:
        if self.cfg.policy == "fcfs":
            return (r.arrival, r.rid)
        if self.cfg.policy == "agent":
            if self.cfg.plugin_semantics:  # vLLM FCFS with bets moved last
                return (r.priority == PRIO_SPEC, r.arrival, r.rid)
            # program-level FCFS (oldest agent session first, as in Continuum /
            # Agentix), with speculative bets behind all certain work
            prog = r.arrival if r.prog_t is None else r.prog_t
            return (r.priority == PRIO_SPEC, prog, r.arrival, r.rid)
        if self.cfg.policy == "vllm-priority":
            # Request.__lt__: (priority, arrival_time, request_id); spec is sent as 1
            return (r.priority == PRIO_SPEC, r.arrival, r.rid)
        return (r.priority, r.arrival, r.rid)

    def _running_key(self, r: Request) -> tuple:
        return self._order(r)

    def _victim(self) -> Request:
        if self.cfg.policy == "vllm-priority":
            # scheduler.py: max(self.running, key=lambda r: (r.priority, r.arrival_time))
            return max(self.running, key=lambda r: (r.priority == PRIO_SPEC, r.arrival))
        return self.running[-1]  # lowest priority / newest (running is sorted)

    def _preempt(self, victim: Request) -> None:
        if self.cfg.reject_bets and victim.priority == PRIO_SPEC:
            self.abort(victim)  # a suppressed bet is dropped, not recomputed
            victim.preemptions += 1
            return
        self.running.remove(victim)
        cfg = self.cfg
        if cfg.kv_policy != "none" and (cfg.resume_from_cache or cfg.cache_freed_blocks):
            # vLLM frees the blocks; the full ones keep their hashes (block_pool.py:799-803)
            self._cache_blocks(victim, self._key(victim) if cfg.resume_from_cache
                               else ("dead", victim.rid))
        else:
            self.kv.release(victim.blocks)
            self._drop_prefix_ref(victim)
        victim.blocks = 0
        victim.preemptions += 1
        # recompute: everything with KV, plus the last sampled token, re-prefills
        victim.need_prefill = victim.prompt + victim.generated
        victim.ctx = 0
        victim.cached = 0
        victim.state = "waiting"
        # resume_from_cache: num_computed_tokens is 0 again, so vLLM looks its blocks up
        # (they may have been evicted meanwhile). Otherwise: recompute from scratch.
        victim.prefix_looked = not (cfg.resume_from_cache and cfg.kv_policy != "none")
        self.waiting.insert(0, victim)

    def _grow(self, r: Request, new_tokens: int) -> bool:
        have = r.blocks + r.shared_blocks
        if self.full_isl and r.state == "waiting":
            # vLLM 0.32 full_sequence_must_fit: the whole sequence (prompt + output so
            # far), against free + evictable blocks (get_num_free_blocks counts both)
            full = math.ceil((r.ctx + r.need_prefill) / BLOCK) - have
            if full > self.kv.headroom(self.sim.now):
                return False
        need = math.ceil((r.ctx + new_tokens) / BLOCK) - have
        if need <= 0:
            return True
        if self.kv.allocate(need, self.sim.now):
            r.blocks += need
            return True
        return False

    def _spec_admissible(self, r: Request, admitted: list, normal_waiting: bool) -> bool:
        """agent policy: speculative work only on spare capacity."""
        if self.cfg.policy != "agent" or r.priority != PRIO_SPEC:
            return True
        if self.sim.now - r.arrival >= self.cfg.spec_max_wait:
            return True
        if normal_waiting:
            return False
        n_spec = sum(x.priority == PRIO_SPEC for x in self.running + admitted)
        if n_spec >= self.cfg.spec_max_running:
            return False
        # one free-window check per step until another bet is admitted (cheap at scale)
        if self._room is None or self._room[0] != len(admitted):
            self._room = (len(admitted), self._in_free_window(admitted, r.prompt))
        if not self._room[1]:
            return False
        return self.kv.headroom(self.sim.now) >= self.cfg.spec_kv_reserve * self.kv.total

    def _chunk(self, r: Request, budget: int) -> int:
        if r.need_prefill <= 0:
            return 1
        n = min(r.need_prefill, budget)
        if self.cfg.policy == "agent" and (r.priority == PRIO_SPEC or r.early) \
                and self._limited(r):
            left = self._spec_left
            if r.priority == PRIO_SPEC and r.state == "running" and self._mirrors_plugin():
                # audit #2: a running bet comes before the waiting loop; it leaves what
                # waiting early prefill needs (certain work first)
                keep = self._waiting_early_need()
                if keep and min(n, left - keep) < min(n, left):
                    self._early_cut = True
                left -= keep
            m = max(0, min(n, left))  # early prefill shares a small per-step allowance
            self._cut |= m < n
            n = m
        return n

    def _mirrors_plugin(self) -> bool:
        """Model the vLLM adapter's audit fixes (#2, #10, #25)? GeneralServer overrides."""
        return self.cfg.plugin_fixes and self.cfg.plugin_semantics \
            and self.cfg.policy == "agent"

    def _waiting_early_need(self) -> int:
        """sptc_vllm _sptc_waiting_early_need: prefill tokens of the early requests waiting
        now, up to the allowance left, if the allowance limits early work in this step.
        Once per step. Nothing is kept while an early request kept for before is still
        waiting unadmitted, or when every sequence slot is taken."""
        if self._early_need is None:
            need, left = 0, self._spec_left
            probe = next((w for w in self.waiting if w.early and w.priority != PRIO_SPEC
                          and w.state == "waiting"), None)
            if (probe is not None and not self._early_unadmitted
                    and len(self.running) < self.cfg.max_num_seqs and self._limited(probe)):
                for w in self.waiting:
                    if need >= left:
                        break
                    if w.state != "waiting" or not w.early or w.priority == PRIO_SPEC:
                        continue
                    if w.need_prefill > 1:
                        need += w.need_prefill
                        self._kept_for.append(w)
            self._early_need = min(need, left)
        return self._early_need

    def _limited(self, r: Request) -> bool:
        """Does the allowance limit this bet/early prefill in this step? adaptive: only when
        there is a more certain stream decoding to protect. A bet yields to any non-bet
        decoder; early work only to an untagged one. Decided once per step."""
        cfg = self.cfg
        if cfg.spec_prefill_mode == "off" or cfg.spec_prefill_budget <= 0:
            return False
        if cfg.spec_prefill_mode == "fixed":
            return True
        if self._protect is None:
            dec = [x for x in self.running if x.need_prefill <= 0 and x.priority != PRIO_SPEC]
            untagged = any(not x.early for x in dec)
            self._protect = (untagged, bool(dec))
        bet = r.priority == PRIO_SPEC
        if cfg.spec_prefill_mode == "adaptive_u":  # EXPLORATORY: untagged decoders only
            return self._protect[0]
        return self._protect[1] if bet else self._protect[0]

    def _nonbet_waiting(self, admitted: list) -> bool:
        return any(w.priority < PRIO_SPEC and w.state == "waiting" and w not in admitted
                   for w in self.waiting)

    def _regate_bets(self, admitted: list, scheduled: bool = True) -> None:
        """plugin_semantics + reject_bets: every bet still waiting is gated again with the
        end-of-step state. Gate fails: rejected now. Passes: held, at most bet_hold_steps.
        plugin_fixes: a held step is not counted when the step scheduled nothing (#25) or
        the bet was skipped for the allowance while another bet prefilled (#10)."""
        bets = [w for w in self.waiting if w.priority == PRIO_SPEC and w.state == "waiting"
                and w not in admitted]
        if not bets:
            return
        ok = self._bet_gate(admitted, self._nonbet_waiting(admitted))
        for r in bets:
            if ok and not self._hold_counts(r, scheduled):
                self._held.setdefault(r.rid, 0)  # held, this step not counted
                continue
            n = self._held.get(r.rid, 0) + 1
            if ok and n <= self.cfg.bet_hold_steps:
                self._held[r.rid] = n
            else:
                self._reject(r)

    def _hold_counts(self, r: Request, scheduled: bool) -> bool:
        """Does this step count toward a held bet's bet_hold_steps?"""
        if not self._mirrors_plugin():
            return True
        return scheduled and not (r.rid in self._allow_skipped and self._bet_prefilled)

    def _end_step_early(self) -> None:
        """#2 bookkeeping: early requests a running bet's chunk was cut for and that are
        still waiting stop the next steps from keeping allowance (as the adapter)."""
        if self._early_cut:
            for w in self._kept_for:
                if w.state == "waiting":
                    self._early_unadmitted[w.rid] = w

    def _bet_gate(self, admitted: list, nonbet_waiting: bool) -> bool:
        """The plugin's gate (policy.admit_bet), on the sim's state."""
        if nonbet_waiting:
            return False
        if sum(x.priority == PRIO_SPEC for x in self.running + admitted) \
                >= self.cfg.spec_max_running:
            return False
        if not self._in_free_window(admitted):
            return False
        return self.kv.headroom(self.sim.now) >= self.cfg.spec_kv_reserve * self.kv.total

    def _reject(self, r: Request) -> None:
        self._held.pop(r.rid, None)
        if r.blocks:
            self._detach_prefix(r)
        self.bets_rejected += 1
        self.abort(r)

    def _schedule(self) -> list[tuple[Request, int, int]]:
        cfg = self.cfg
        budget = cfg.max_batched_tokens
        self._spec_left = cfg.spec_prefill_budget
        self._protect = None  # adaptive: (untagged decoder, non-bet decoder), at first use
        self._cut = False
        self._early_need = None
        self._kept_for = []
        self._early_cut = False
        self._allow_skipped.clear()
        self._bet_prefilled = False
        if self._early_unadmitted:  # admitted, finished or aborted since: forget
            for rid in [k for k, w in self._early_unadmitted.items() if w.state != "waiting"]:
                del self._early_unadmitted[rid]
        plugin_bets = cfg.policy == "agent" and cfg.reject_bets and (
            cfg.plugin_semantics or cfg.bet_gate == "schedule")
        batch: list[tuple[Request, int, int]] = []
        preempted = False
        if cfg.policy != "vllm-priority":  # vLLM keeps running in admission order
            self.running.sort(key=self._running_key)
        i = 0
        while i < len(self.running) and budget > 0:
            r = self.running[i]
            n = self._chunk(r, budget)
            if n == 0:  # speculative prefill out of this step's allowance
                i += 1
                continue
            while not self._grow(r, n):
                victim = self._victim()
                vi = self.running.index(victim)
                self._preempt(victim)
                preempted = True
                if victim is r:
                    break
                if vi < i:  # already scheduled this step: give its tokens back
                    i -= 1
                    budget += sum(k for b, k, _ in batch if b is victim)
                    batch[:] = [b for b in batch if b[0] is not victim]
            if r.state != "running":
                # r preempted itself: vLLM ends the running loop (new_blocks is None) and,
                # having preempted, skips waiting. Same as before under fcfs, where r is last.
                break
            batch.append((r, n, r.ctx))
            budget -= n
            if (r.priority == PRIO_SPEC or r.early) and r.need_prefill > 0 \
                    and self._limited(r):  # as the plugin: charged only where it applies
                self._spec_left -= n
                self._bet_prefilled |= r.priority == PRIO_SPEC
            i += 1
        self._preempted_all = preempted and not batch
        if preempted:
            if plugin_bets:
                self._regate_bets([], scheduled=bool(batch))
            self.allowance_steps += self._cut
            self._end_step_early()
            return batch
        self._room = None
        if cfg.policy == "agent":  # aging: long-waiting bets become normal work
            for r in self.waiting:
                if r.priority == PRIO_SPEC and self.sim.now - r.arrival >= cfg.spec_max_wait:
                    r.priority = PRIO_NORMAL
        self.waiting.sort(key=self._order)
        admitted = []
        normal_waiting = False
        nonbet_waiting = None  # plugin_semantics: cached at the first bet (bets are last)
        for r in list(self.waiting):  # _preempt_for may push victims onto waiting
            if r.state != "waiting":
                continue
            if budget <= 0 or len(self.running) + len(admitted) >= cfg.max_num_seqs:
                break
            if plugin_bets and r.priority == PRIO_SPEC:
                if nonbet_waiting is None:
                    nonbet_waiting = self._nonbet_waiting(admitted)
                if not self._bet_gate(admitted, nonbet_waiting):
                    self._reject(r)
                    continue
            elif not self._spec_admissible(r, admitted, normal_waiting):
                continue
            if not r.prefix_looked:
                self._attach_prefix(r)
            n = self._chunk(r, budget)
            if n == 0:
                if r.priority == PRIO_SPEC:
                    self._allow_skipped.add(r.rid)
                continue
            if not self._grow(r, n):
                # vLLM never preempts running work for a waiting request; the
                # PASTE-style agent policy reclaims speculative work first.
                if cfg.policy != "agent" or cfg.plugin_semantics \
                        or not self._preempt_for(r, n, batch):
                    if r.ctx or r.shared_blocks:  # vLLM: the hit blocks stay in the cache
                        # Known limit: this re-caches them as most recently used. vLLM's
                        # failed allocate_slots returns before touch() (kv_cache_manager.py
                        # :522-539), so they keep their place in the free queue. Measured
                        # effect on the 4090 headline cell: <= 0.4% on waste1 p50.
                        self._detach_prefix(r)
                    normal_waiting |= r.priority < PRIO_SPEC
                    break
                budget = cfg.max_batched_tokens - sum(k for _, k, _ in batch)
            admitted.append(r)
            batch.append((r, n, r.ctx))
            budget -= n
            if (r.priority == PRIO_SPEC or r.early) and self._limited(r):
                self._spec_left -= n
                self._bet_prefilled |= r.priority == PRIO_SPEC and n > 0
        if plugin_bets:
            self._regate_bets(admitted, scheduled=bool(batch))
            for r in admitted:
                self._held.pop(r.rid, None)
        self.allowance_steps += self._cut
        self._n_new = 0
        for r in admitted:
            self.waiting.remove(r)
            r.state = "running"
            if r.t_sched is None:
                r.t_sched = self.sim.now
                self._n_new += 1
            self.running.append(r)
        self._end_step_early()
        return batch

    def _preempt_for(self, r: Request, n: int, batch: list) -> bool:
        """agent: evict running BETS (never certain work) for a certain request,
        and drop the victims from this step's batch."""
        if r.priority == PRIO_SPEC:
            return False
        while not self._grow(r, n):
            lower = [x for x in self.running if x.priority == PRIO_SPEC]
            if not lower:
                return False
            victim = max(lower, key=self._order)
            self._preempt(victim)
            batch[:] = [b for b in batch if b[0] is not victim]
        return True

    # -- main loop -------------------------------------------------------------
    def _loop(self):
        sim = self.sim
        while True:
            if not self.running and not self.waiting:
                self._wake = sim.event()
                yield self._wake
                continue
            self._n_new = 0
            batch = self._schedule()
            if not batch:
                if self._preempted_all:
                    continue  # vLLM skips WAITING in a preempting step; retry now
                if self._held:
                    # vLLM keeps stepping while requests exist: empty steps used up a held
                    # bet's bet_hold_steps in no time. Since audit #25 (plugin_fixes) a step
                    # that schedules nothing is not counted, so a held bet waits for the
                    # next change; one that can never be allocated is still rejected (vLLM
                    # refuses such a prompt when it is added: KV holds max_model_len).
                    held = [w for w in self.waiting if w.rid in self._held and (
                        not self._mirrors_plugin()
                        or math.ceil(w.need_prefill / BLOCK) > self.kv.total)]
                    if not self._mirrors_plugin():
                        self._held.clear()
                    for r in held:
                        self._reject(r)
                    if held:
                        continue
                if self.waiting and not self.running:
                    big = min(self.waiting, key=self._order)
                    if math.ceil(big.need_prefill / BLOCK) > self.kv.total:
                        raise RuntimeError(
                            f"request needs {big.need_prefill} tokens of KV; capacity "
                            f"{self.kv.total * BLOCK}"
                        )
                self._wake = sim.event()
                t = self._next_timer()
                if t is not None:
                    wake = self._wake
                    sim.call_at(t, lambda w=wake: w.succeed())
                yield self._wake
                self._wake = None
                continue
            dt = self.cost.step_time([(n, c) for (_, n, c) in batch], self._n_new)
            t0 = sim.now
            yield sim.timeout(dt)
            self.steps += 1
            self.busy_time += dt
            if self.log_steps:
                self.step_log.append(
                    (t0, dt, len(batch), sum(n for _, n, _ in batch), self.kv.used)
                )
            for r, n, _ in batch:
                if r.state != "running":
                    continue  # aborted or preempted mid-step: work wasted
                r.computed_tokens += n
                r.ctx += n
                if r.prefix_key is not None and r.shared_blocks < r.prefix_tokens // BLOCK \
                        and r.ctx >= r.prefix_tokens and self.cfg.kv_policy != "none":
                    self._publish_prefix(r)
                if r.need_prefill > 0:
                    r.need_prefill -= n
                    if r.need_prefill > 0:
                        continue
                self._emit(r)

    def _next_timer(self) -> float | None:
        """Earliest future moment blocked work may become schedulable on its own:
        a TTL pin expiring, or a waiting bet aging into normal work."""
        now = self.sim.now
        ts = [e.pinned_until for e in self.kv.entries.values() if e.pinned_until >= now]
        if self.cfg.policy == "agent":
            ts += [r.arrival + self.cfg.spec_max_wait for r in self.waiting
                   if r.priority == PRIO_SPEC]
        ts = [t for t in ts if now < t < math.inf]
        return min(ts) + 1e-9 if ts else None

    def _emit(self, r: Request) -> None:
        now = self.sim.now
        r.generated += 1
        if r.t_first is None:
            r.t_first = now
        elif r.track_itl and r.last_tok is not None:
            r.itl.append(now - r.last_tok)
        r.last_tok = now
        if r.on_token is not None:
            r.on_token(r.generated, now)
        if r.generated >= r.out:
            self._finish(r)

    def _finish(self, r: Request) -> None:
        self.running.remove(r)
        r.state = "done"
        r.t_done = self.sim.now
        cfg = self.cfg
        if cfg.kv_policy != "none" and (r.session is not None or cfg.cache_freed_blocks):
            pin = self.sim.now + cfg.pin_ttl if cfg.kv_policy == "pin" else -1.0
            if r.session is None:
                self._cache_blocks(r, ("dead", r.rid))
            elif cfg.cache_freed_blocks:
                self._cache_blocks(r, r.session, pin)
            else:  # the whole context, partial last block included
                self.kv.put(r.session, r.ctx, r.blocks, self.sim.now, pin,
                            base=r.shared_blocks * BLOCK)
                self._drop_prefix_ref(r, pin)
        else:
            self.kv.release(r.blocks)
            self._drop_prefix_ref(r)
        r.blocks = 0
        self.finished.append(r)
        r.done.succeed(r)
