"""vLLM v0.32.0 scheduler plugin: the sptc 'agent' policy (docs/report.md sections 3, 4.2).

    vllm serve MODEL --scheduler-cls sptc_vllm.scheduler.SptcScheduler \
        --additional-config '{"sptc": {"free_window": 8, "kv_reserve": 0.1,
                                       "spec_prefill_budget": 512, "bet_hold_steps": 16,
                                       "prefill_allowance": "fixed"}}'

SptcScheduler picks its async or sync variant from scheduler_config.async_scheduling (vLLM's
default is async), so one class name works for both. SptcAsyncScheduler is the explicit async
variant and refuses to run with async scheduling off.

Requests are tagged with SamplingParams.extra_args["sptc_class"] in {"bet", "early"}
(OpenAI API: extra_body={"vllm_xargs": {"sptc_class": ...}}). Untagged requests get vanilla
FCFS. Only the narrow hooks below are overridden; no block of Scheduler.schedule() is copied.
"""

from __future__ import annotations

from collections import Counter

from vllm.logger import init_logger
from vllm.v1.core.sched.async_scheduler import AsyncScheduler
from vllm.v1.core.sched.interface import PauseState
from vllm.v1.core.sched.output import SchedulerOutput
from vllm.v1.core.sched.request_queue import SchedulingPolicy
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.engine import EngineCoreOutput, EngineCoreOutputs, FinishReason
from vllm.v1.request import Request, RequestStatus

from sptc_vllm import policy

# Under vLLM's logger namespace: vLLM configures only the "vllm" logger, so a plain
# init_logger(__name__) dropped the startup line on the T4 run (sptc_out/vllm_plugin.log).
logger = init_logger(f"vllm.{__name__}")

_BLOCKED = (
    RequestStatus.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR,
    RequestStatus.WAITING_FOR_REMOTE_KVS,
    RequestStatus.WAITING_FOR_STREAMING_REQ,
)
_QUEUED = (RequestStatus.WAITING, RequestStatus.PREEMPTED)  # in a waiting queue, admissible
BET, EARLY, NORMAL = policy.SptcClass.BET, policy.SptcClass.EARLY, policy.SptcClass.NORMAL


class SptcScheduler(Scheduler):
    """Entry point. Constructing it with async scheduling on yields a SptcAsyncScheduler."""

    def __new__(cls, *args, **kwargs):
        if cls is SptcScheduler:
            vllm_config = kwargs.get("vllm_config", args[0] if args else None)
            if vllm_config is not None and vllm_config.scheduler_config.async_scheduling:
                cls = SptcAsyncScheduler
        return super().__new__(cls)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.policy != SchedulingPolicy.FCFS:
            raise ValueError("sptc scheduler supports --scheduling-policy fcfs only")
        async_on = bool(self.scheduler_config.async_scheduling)
        if async_on != isinstance(self, AsyncScheduler):
            raise ValueError(
                f"async scheduling is {'on' if async_on else 'off'} but "
                f"{type(self).__name__} is the {'async' if not async_on else 'sync'} variant: "
                "use sptc_vllm.scheduler.SptcScheduler (it picks the right one)"
            )
        self.sptc_config = policy.config_from_additional(self.vllm_config.additional_config)
        if self.sptc_config.free_window >= self.max_num_active_reqs:
            # Bets may then fill every sequence slot and keep normal work out until one
            # ends. Kept as set (a benchmark may want exactly that); only warned about.
            logger.warning(
                "sptc: free_window %d >= max_num_seqs %d: bets can take every sequence "
                "slot; normal work then waits until a bet ends",
                self.sptc_config.free_window, self.max_num_active_reqs,
            )
        budget = self.sptc_config.allowance_budget  # 0 when prefill_allowance is "off"
        if budget > 0 and not self.scheduler_config.enable_chunked_prefill:
            logger.warning("sptc: chunked prefill is off; spec_prefill_budget disabled")
            budget = 0
        if budget > 0 and (
            self.need_mamba_block_aligned_split
            or self.vllm_config.model_config.supports_multimodal_inputs
        ):
            # Capping a chunk after vLLM's mamba-align / encoder-input planning could break
            # their invariants; run without the allowance rather than risk it.
            logger.warning(
                "sptc: spec_prefill_budget disabled for hybrid-align or multimodal models"
            )
            budget = 0
        if 0 < budget < self.num_prefill_lookahead:
            # Multi-module MTP: a step's allowance below the prefill lookahead L counts as
            # spent at once (short_of), so no tagged prefill would ever be scheduled.
            logger.warning(
                "sptc: spec_prefill_budget %d is below the MTP prefill lookahead %d; using %d",
                budget, self.num_prefill_lookahead, self.num_prefill_lookahead,
            )
            budget = self.num_prefill_lookahead
        self._sptc_allow = policy.PrefillAllowance(
            budget, adaptive=self.sptc_config.prefill_allowance == "adaptive"
        )
        self._sptc_waiting_bets: dict[str, Request] = {}  # bets in waiting/kv_holding_waiting
        self._sptc_running_bets: dict[str, Request] = {}  # bets admitted to running
        self._sptc_held: dict[str, int] = {}  # waiting bet -> steps held with the gate passing
        # Bets vLLM admitted into an async KV-connector load: their blocks are allocated, so
        # they are never gated again (until they run, finish or are dropped).
        self._sptc_loading: dict[str, Request] = {}
        self._sptc_readmit: set[str] = set()  # bets requeued by vLLM after they were admitted
        self._sptc_reject: dict[str, str] = {}  # this step: id -> gate reason
        self._sptc_nonbet_waiting: bool | None = None  # this step: cached at the first bet
        self._sptc_defer = False  # this step: vLLM defers prefills (DP prefill throttle)
        self._sptc_passed: list[Request] = []  # this step: bets passed by the gate (connector)
        self._sptc_allow_skipped: set[str] = set()  # this step: bets skipped for the allowance
        self._sptc_bet_prefilled = False  # this step: a bet's prefill used the allowance
        self._sptc_early_need: int | None = None  # this step: allowance kept for early work
        self._sptc_kept_for: list[Request] = []  # this step: early requests counted in it
        self._sptc_early_cut = False  # this step: keeping it cut a running bet's chunk
        # Early requests a bet's chunk was cut for that vLLM then did not admit (KV, a
        # normal request's break, LoRA, ...): while any is still queued, no allowance is
        # kept for early work, so a bet is never held at 0 tokens for work that cannot start.
        self._sptc_early_unadmitted: dict[str, Request] = {}
        self._sptc_in_schedule = False
        self._sptc_pending: list[tuple[int, EngineCoreOutput]] = []
        self.sptc_counters: Counter[str] = Counter()
        logger.info(
            "sptc scheduler (%s): %s, prefill allowance %s",
            type(self).__name__,
            self.sptc_config,
            "unlimited" if budget <= 0 else f"{budget} ({self.sptc_config.prefill_allowance})",
        )

    # -- classification ---------------------------------------------------------------
    @staticmethod
    def _sptc_class(request: Request) -> policy.SptcClass:
        sp = request.sampling_params
        if sp is None or request.resumable:  # pooling / streaming-input sessions: normal
            return NORMAL
        return policy.classify(sp.extra_args)

    # -- intake -----------------------------------------------------------------------
    def add_request(self, request: Request) -> None:
        is_new = request.request_id not in self.requests
        super().add_request(request)
        if is_new and self._sptc_class(request) is BET:
            self._sptc_waiting_bets[request.request_id] = request

    # -- one scheduling step ----------------------------------------------------------
    def schedule(self, throttle_prefills: bool = False) -> SchedulerOutput:
        self._sptc_begin_step(throttle_prefills)
        self._sptc_in_schedule = True
        try:
            out = super().schedule(throttle_prefills)
        finally:
            self._sptc_in_schedule = False
        if self._sptc_early_cut:
            for r in self._sptc_kept_for:
                if r.status in _QUEUED:  # still queued: vLLM did not admit it this step
                    self._sptc_early_unadmitted[r.request_id] = r
                    self.sptc_counters["early_kept_not_admitted"] += 1
        self._sptc_end_step(out.total_num_scheduled_tokens > 0)
        return out

    def _sptc_begin_step(self, throttle_prefills: bool) -> None:
        self._sptc_allow.reset()
        self._sptc_reject.clear()
        self._sptc_nonbet_waiting = None
        # vLLM's own defer_prefills test, read before schedule() changes either input
        self._sptc_defer = (
            throttle_prefills
            and not self.prefill_capacity_bound
            and any(not r.is_prefill_chunk for r in self.running)
        )
        self._sptc_passed.clear()
        self._sptc_allow_skipped.clear()
        self._sptc_bet_prefilled = False
        self._sptc_early_need = None
        self._sptc_kept_for = []
        self._sptc_early_cut = False
        ue = self._sptc_early_unadmitted
        if ue:  # admitted, finished or blocked since: forget
            for rid in [rid for rid, r in ue.items() if r.status not in _QUEUED]:
                del ue[rid]
        self._sptc_capacity_set = False
        rb = self._sptc_running_bets
        if rb:
            for rid in [rid for rid, r in rb.items() if r.status != RequestStatus.RUNNING]:
                del rb[rid]  # finished normally or aborted by the client
        if rb:  # FCFS victim is running[-1]: keep bets last so they are dropped first
            self.running = policy.order_by_rank(self.running, self._sptc_running_rank)
        wb = self._sptc_waiting_bets
        if wb:  # bets behind all certain work, so the scan reaches every non-bet first
            items = list(self.waiting)
            ordered = policy.bets_last(items, lambda r: r.request_id in wb)
            if ordered is not items:
                self.waiting.clear()  # FCFSRequestQueue is a deque (FCFS asserted in __init__)
                self.waiting.extend(ordered)

    def _sptc_running_rank(self, r: Request) -> int:
        """0 non-bet, 1 bet that finishes on output already in flight, 2 other bet. The FCFS
        victim running[-1] is then the newest bet that still needs compute."""
        if r.request_id not in self._sptc_running_bets:
            return 0
        return 1 if self._sptc_finishes_in_flight(r) else 2

    @staticmethod
    def _sptc_finishes_in_flight(r: Request) -> bool:
        return policy.finishes_in_flight(
            num_output_placeholders=r.num_output_placeholders,
            num_computed_tokens=r.num_computed_tokens,
            num_prompt_tokens=r.num_prompt_tokens,
            max_tokens=r.max_tokens,
            num_tokens=r.num_tokens,
            num_in_flight_tokens=r.num_in_flight_tokens,
        )

    def _sptc_end_step(self, scheduled: bool = True) -> None:
        """Every waiting bet that was not admitted this step and not already rejected by the
        gate is gated again with the end-of-step state. Gate fails: rejected now. Gate
        passes (only the token budget, the allowance, DP throttling or a transient vLLM skip
        kept it out): held and re-gated next step, at most bet_hold_steps times. A held
        step is not counted when vLLM deferred prefills (DP throttle), when the step
        scheduled no tokens (an idle engine iteration), or when the bet was skipped for the
        allowance while another bet's prefill used it."""
        reject: dict[str, str] = {}
        gate: policy.BetVerdict | None = None  # same inputs for every bet: computed once
        paused = self._pause_state != PauseState.UNPAUSED
        for rid, r in list(self._sptc_waiting_bets.items()):
            if r.status == RequestStatus.RUNNING:
                del self._sptc_waiting_bets[rid]
                self._sptc_held.pop(rid, None)
                self._sptc_loading.pop(rid, None)
                self._sptc_running_bets[rid] = r
                if rid in self._sptc_readmit:
                    self._sptc_readmit.discard(rid)
                    self.sptc_counters["bet_readmitted"] += 1
                else:
                    self.sptc_counters["bet_admitted"] += 1
                continue
            if r.is_finished():  # client abort, or finished on in-flight output
                self._sptc_forget(rid)
                continue
            if r.status == RequestStatus.WAITING_FOR_REMOTE_KVS or rid in self._sptc_loading:
                # Admitted into an async KV load (vLLM allocated its blocks after the gate
                # passed): not gated again, so the transfer is not thrown away.
                if rid not in self._sptc_loading:
                    self._sptc_loading[rid] = r
                    self._sptc_held.pop(rid, None)
                    self.sptc_counters["bet_kv_load"] += 1
                continue
            if rid in self.grammar_compile_error_reqs or self._sptc_grammar_failed(r):
                continue  # vLLM finishes it as FINISHED_ERROR; not a rejection
            reason = self._sptc_reject.get(rid)
            if reason is None:
                if r.num_stale_output_tokens and not r.drop_stale_output:
                    continue  # requeued in _preempt_request: finishes on its in-flight output
                blocked = r.status in _BLOCKED and not self._sptc_blocked_ready(r)
                if paused and not blocked:
                    reason = "paused"  # nothing new is admitted while paused
                else:
                    if gate is None:
                        gate = self._sptc_gate(self._sptc_scan_nonbet_waiting())
                    if not gate.admit:
                        if not (self._sptc_defer and gate.reason == "nonbet_waiting"):
                            reason = gate.reason
                        # else: vLLM held this step's prefills back (DP throttle), so the
                        # non-bets may wait for the cadence, not for capacity: hold.
                    elif (
                        not blocked
                        and not self._sptc_defer
                        and scheduled
                        and not (rid in self._sptc_allow_skipped and self._sptc_bet_prefilled)
                    ):
                        n = self._sptc_held.get(rid, 0) + 1
                        if n > self.sptc_config.bet_hold_steps:
                            reason = "held_too_long"
                        else:
                            self._sptc_held[rid] = n
            if reason is not None:
                reject[rid] = reason
        if not reject:
            return
        stop: dict[str, str] = {}
        for rid, reason in reject.items():
            del self._sptc_waiting_bets[rid]
            self._sptc_held.pop(rid, None)
            if rid in self._sptc_readmit:
                # Requeued by vLLM after it was admitted (and may have streamed tokens): to
                # the client it is a dropped bet, not a refused one.
                self._sptc_readmit.discard(rid)
                self.sptc_counters["bet_dropped_requeued:" + reason] += 1
                stop[rid] = policy.STOP_REASON_DROPPED
            else:
                self.sptc_counters["bet_rejected:" + reason] += 1
        for r in self.finish_requests(list(reject), RequestStatus.FINISHED_ABORTED):
            self._sptc_pending.append(
                (
                    r.client_index,
                    self._sptc_abort_output(
                        r, stop.get(r.request_id, policy.STOP_REASON_REJECTED)
                    ),
                )
            )
        if self._sptc_capacity_set:
            # vLLM's DP throttle signal was computed with the rejected bets still queued;
            # recompute it as if they had never arrived (same expression as schedule()).
            _, num_waiting = self.get_request_counts()
            self.prefill_capacity_bound = num_waiting > len(self.deferred_waiting)
        logger.debug("sptc: rejected %d bet(s); counters %s", len(reject), dict(self.sptc_counters))

    def _sptc_forget(self, rid: str) -> None:
        self._sptc_waiting_bets.pop(rid, None)
        self._sptc_held.pop(rid, None)
        self._sptc_loading.pop(rid, None)
        self._sptc_readmit.discard(rid)

    def _sptc_blocked_ready(self, r: Request) -> bool:
        """A blocked bet that vLLM would promote to WAITING on its next visit (the visit only
        happens if the waiting loop reaches it). Bets waiting for a remote KV load are
        handled before this (never gated again)."""
        if r.status == RequestStatus.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR:
            so = r.structured_output_request
            return so is not None and so.grammar is not None and not isinstance(
                so.grammar, Exception
            )
        return False

    @staticmethod
    def _sptc_grammar_failed(r: Request) -> bool:
        """Grammar compile failed: vLLM reports FINISHED_ERROR once its loop visits it."""
        if r.status != RequestStatus.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR:
            return False
        so = r.structured_output_request
        return so is not None and isinstance(so.grammar, Exception)

    # -- DP prefill throttle signal: note when schedule() sets it -----------------------
    @property
    def prefill_capacity_bound(self) -> bool:
        return self._sptc_capacity_bound

    @prefill_capacity_bound.setter
    def prefill_capacity_bound(self, value: bool) -> None:
        self._sptc_capacity_bound = value
        self._sptc_capacity_set = True

    # -- waiting-loop hook: bet gate + allowance deferral -----------------------------
    def _handle_blocked_waiting_request(self, request: Request) -> bool:
        if not super()._handle_blocked_waiting_request(request):
            return False
        if request.num_stale_output_tokens and not request.drop_stale_output:
            return True  # vLLM skips it right after this (deliverable stale output)
        cls = self._sptc_class(request)
        if cls is NORMAL:
            return True
        if cls is BET and request.request_id not in self._sptc_loading:
            if self.kv_holding_waiting and self.kv_holding_waiting.peek_request() is request:
                # kv_holding_waiting is drained before `waiting`, so the non-bets queued in
                # `waiting` have not been visited yet: scan now, do not cache.
                nonbet_waiting = self._sptc_scan_nonbet_waiting()
            else:
                if self._sptc_nonbet_waiting is None:
                    self._sptc_nonbet_waiting = self._sptc_scan_nonbet_waiting()
                nonbet_waiting = self._sptc_nonbet_waiting
            v = self._sptc_gate(nonbet_waiting)
            if not v.admit:
                self._sptc_reject[request.request_id] = v.reason  # finished after schedule()
                return False
            if self.connector is not None:
                self._sptc_passed.append(request)  # may become an async KV load
        if (
            self._sptc_allow.short_of(self.num_prefill_lookahead)
            and policy.is_prefill(request.num_tokens, request.num_computed_tokens)
            and self._sptc_allow.applies(cls, self._sptc_decoders)
        ):
            # Skip (never break): normal work behind it still gets its turn. Short of the
            # MTP prefill lookahead counts as spent: such a chunk could be cut to 0 tokens,
            # which the waiting loop treats as `break`.
            if cls is BET:
                self._sptc_allow_skipped.add(request.request_id)
            return False
        return True

    def _sptc_gate(self, nonbet_waiting: bool) -> policy.BetVerdict:
        num_running = len(self.running)  # includes this step's admissions
        if self.connector is not None:
            # Bets in an async KV load hold their blocks but are not in `running` yet.
            num_running += sum(
                1 for r in self._sptc_loading.values()
                if r.status != RequestStatus.RUNNING and not r.is_finished()
            ) + sum(
                1 for r in self._sptc_passed
                if r.status == RequestStatus.WAITING_FOR_REMOTE_KVS
                and r.request_id not in self._sptc_loading
            )
        return policy.admit_bet(
            num_running=num_running,
            nonbet_waiting=nonbet_waiting,
            kv_usage=self.kv_cache_manager.usage,  # before the bet's own allocation
            cfg=self.sptc_config,
        )

    def _sptc_scan_nonbet_waiting(self) -> bool:
        """Any certain (non-bet) work waiting, including early requests held back by the
        allowance and requests vLLM skipped this step (deferred_waiting). In the waiting loop
        it is cached at the first bet from `waiting`: bets were moved behind all non-bets,
        so every non-bet there has been admitted or skipped by then. Idle streaming sessions
        are not work waiting for capacity."""
        for q in (self.kv_holding_waiting, self.waiting, self.deferred_waiting):
            for r in q:
                if (
                    r.status != RequestStatus.WAITING_FOR_STREAMING_REQ
                    and not r.is_finished()
                    and self._sptc_class(r) is not BET
                ):
                    return True
        return False

    # -- chunk-size hook: shared bet/early prefill allowance --------------------------
    def _sptc_decoders(self) -> tuple[bool, bool]:
        """adaptive allowance: (untagged, non-bet) request decoding in this step. Asked once
        per step, at the first tagged prefill (running loop: the running set at step start;
        waiting loop: plus this step's admissions, which are prefills and do not count)."""
        return policy.scan_decoders(
            (self._sptc_class(r), not policy.is_prefill(r.num_tokens, r.num_computed_tokens))
            for r in self.running
        )

    def _reserve_prefill_lookahead(
        self, request: Request, num_computed_tokens: int, num_new_tokens: int
    ) -> int:
        cls = NORMAL if self._sptc_allow.unlimited else self._sptc_class(request)
        if (
            cls is NORMAL
            or not policy.is_prefill(request.num_tokens, num_computed_tokens)
            or not self._sptc_allow.applies(cls, self._sptc_decoders)
        ):
            return super()._reserve_prefill_lookahead(
                request, num_computed_tokens, num_new_tokens
            )
        # A running bet's prefill comes before the waiting loop: it leaves what waiting
        # early prefill needs (certain work first). Waiting requests are never RUNNING here.
        keep = (
            self._sptc_waiting_early_need()
            if cls is BET and request.status == RequestStatus.RUNNING
            else 0
        )
        capped = self._sptc_allow.cap(num_new_tokens, keep)
        if keep and capped < self._sptc_allow.cap(num_new_tokens):
            self._sptc_early_cut = True
        # Cap first, then keep vLLM's multi-module MTP lookahead rule on the capped chunk.
        n = super()._reserve_prefill_lookahead(request, num_computed_tokens, capped)
        self._sptc_allow.charge(n)
        if cls is BET and n > 0:
            self._sptc_bet_prefilled = True
        return n

    def _sptc_waiting_early_need(self) -> int:
        """Prefill tokens of the early requests waiting now, up to the allowance left, if
        the allowance limits early work in this step. Computed once per step, at the first
        running bet prefill, so steps without one pay nothing. Counted before the prefix
        lookup (the whole uncomputed prompt), so it may keep more than the early requests
        use; the rest of the step's allowance then goes unused, never to a bet.
        Only requests vLLM's waiting loop can reach count: none while paused (PAUSED_NEW
        admits kv_holding_waiting only) or when every sequence slot is taken. Nothing is
        kept while an early request kept for before is still queued unadmitted
        (_sptc_early_unadmitted): vLLM's waiting loop stops at the first request it cannot
        allocate, so the ones behind it would mostly not start either. A cut that admits
        nothing therefore costs a bet one step, and the next such step needs that early
        request to start first. Without this, a bet that held the KV an early request
        needed was cut to 0 on every step and the engine stalled."""
        if self._sptc_early_need is None:
            need = 0
            left = self._sptc_allow.left
            pause = self._pause_state
            if (
                self._sptc_allow.applied(EARLY)
                and not self._sptc_early_unadmitted
                and pause != PauseState.PAUSED_ALL
                and len(self.running) + self.num_waiting_for_streaming_input
                < self.max_num_active_reqs
            ):
                queues = (
                    (self.kv_holding_waiting, self.waiting)
                    if pause == PauseState.UNPAUSED
                    else (self.kv_holding_waiting,)
                )
                for q in queues:
                    for r in q:
                        if need >= left:
                            break
                        if (
                            r.status in _BLOCKED
                            or r.is_finished()
                            or (r.num_stale_output_tokens and not r.drop_stale_output)
                            or self._sptc_class(r) is not EARLY
                        ):
                            continue
                        if policy.is_prefill(r.num_tokens, r.num_computed_tokens):
                            need += r.num_tokens - r.num_computed_tokens
                            self._sptc_kept_for.append(r)
            self._sptc_early_need = min(need, left)
        return self._sptc_early_need

    # -- preemption: drop bets instead of requeueing them -----------------------------
    def _preempt_request(
        self, request: Request, timestamp: float, drop_stale_output: bool = False
    ) -> None:
        if self._sptc_class(request) is not BET:
            return super()._preempt_request(request, timestamp, drop_stale_output)
        rid = request.request_id
        if not self._sptc_in_schedule or (
            not drop_stale_output and self._sptc_finishes_in_flight(request)
        ):
            # reset_prefix_cache(reset_running_requests=True), or an async bet whose step in
            # flight completes it: keep vLLM's requeue. In the second case vLLM delivers the
            # in-flight tokens and finishes the request normally; dropping it would throw a
            # finished result away. Ordered before other bets, it is only a victim when no
            # bet that still needs compute is left.
            super()._preempt_request(request, timestamp, drop_stale_output)
            self._sptc_running_bets.pop(rid, None)
            self._sptc_waiting_bets[rid] = request  # re-gated next step (if not finished)
            self._sptc_readmit.add(rid)  # if the re-gate fails, the client sees a drop
            if self._sptc_in_schedule:
                self.sptc_counters["bet_requeued_finishing"] += 1
            return
        # Inside schedule()'s running loop. The caller already popped the bet from running
        # after checking that its blocks can be freed now. Finishing it frees the blocks for
        # the retried allocate_slots, puts its id in this step's finished_req_ids, and makes
        # update_from_output discard any of its tokens still in flight (async scheduling).
        assert request.status == RequestStatus.RUNNING, "only running bets are dropped"
        request.status = RequestStatus.FINISHED_ABORTED
        self._free_request(request)
        self._sptc_running_bets.pop(rid, None)
        self._sptc_pending.append(
            (request.client_index, self._sptc_abort_output(request, policy.STOP_REASON_DROPPED))
        )
        self.sptc_counters["bet_dropped"] += 1

    # -- client-visible finishes -------------------------------------------------------
    @staticmethod
    def _sptc_abort_output(r: Request, stop_reason: str) -> EngineCoreOutput:
        return EngineCoreOutput(
            request_id=r.request_id,
            new_token_ids=[],
            finish_reason=FinishReason.ABORT,
            stop_reason=stop_reason,
            events=r.take_events(),
            trace_headers=r.trace_headers,
        )

    def update_from_output(self, scheduler_output, model_runner_output):
        outputs = super().update_from_output(scheduler_output, model_runner_output)
        rb = self._sptc_running_bets
        if rb:  # drop bets that finished in this step right away (begin-step also sweeps)
            for rid in [rid for rid, r in rb.items() if r.is_finished()]:
                del rb[rid]
        if self._sptc_pending:
            pending, self._sptc_pending = self._sptc_pending, []
            for client_index, out in pending:
                eco = outputs.get(client_index)
                if eco is None:
                    outputs[client_index] = EngineCoreOutputs(outputs=[out])
                else:
                    eco.outputs = [*eco.outputs, out]  # never mutate a shared list in place
        return outputs


class SptcAsyncScheduler(SptcScheduler, AsyncScheduler):
    """Async variant (vLLM's default). MRO: SptcAsyncScheduler -> SptcScheduler ->
    AsyncScheduler -> Scheduler, so every super() call in SptcScheduler reaches
    AsyncScheduler's placeholder bookkeeping."""
