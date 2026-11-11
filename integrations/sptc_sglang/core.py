"""The sptc 'agent' policy for SGLang, written against injected base classes.

plugin.py binds these factories to SGLang v0.5.22's Scheduler and PrefillAdder. Keeping
SGLang out of this module lets the local tests run it without SGLang or a GPU: on fakes
(tests/test_sglang_core.py) and on SGLang's own scheduling code compiled from the vendored
sources (tests/test_sglang_vendored.py). The policy itself (gate, ordering, allowance) is
shared with the vLLM plugin: sptc_vllm/policy.py.

How the policy maps onto SGLang:
- Admission gate. Bets are moved behind all other waiting requests, so SGLang's FCFS loop
  reaches them last. PrefillAdder.add_one_req gates each bet with the state at that point
  (running + already admitted this step, KV usage including this step's admissions). A
  refused bet is skipped, never a `break`, so certain work behind it still runs. After the
  step every bet still waiting is gated again with the end-of-step state: refused -> aborted
  now; gate passes but not admitted -> held, up to bet_hold_steps (a step in which it was
  skipped for the allowance while another bet's prefill used it is not counted, as in
  sptc_vllm). A bet that SGLang's own
  KV reservation refuses (NO_TOKEN) is skipped too, so it never sets batch_is_full. A bet
  SGLang has already failed (to_finish set) is left to SGLang and gets SGLang's error.
- Dropping. SGLang retracts decodes when KV runs out. The retraction order is wrapped so
  bets are retracted first, and a retracted bet is aborted instead of requeued, also when
  pause_generation(mode="retract") retracts it. A bet in the middle of a chunked prefill
  is not in the decode batch, so SGLang cannot retract it: before a decode step that would
  retract, it is dropped through SGLang's own chunked-request abort
  (process_pending_chunked_abort), which frees its KV. An early request in the middle of
  a chunked prefill is not dropped. In a decode step the plugin forced that would retract,
  it is retracted itself (KV freed, requeued) when SGLang's own retraction order would
  have picked it first had it been decoding.
- Prefill allowance. In a step that starts with no normal request waiting, prefill tokens
  of bet and early requests share spec_prefill_budget, applied by capping rem_chunk_tokens
  (and chunked_req_limit) around SGLang's own admission code. With normal work waiting the
  step stalls decoders for a full chunk anyway, so tagged work is left to SGLang's FCFS.
  SGLang keeps at most one partially prefilled (chunked) request: when the cap leaves a
  tagged request chunked, nothing else is admitted in that step, which is what SGLang does
  when a chunk fills the step's budget. prefill_allowance "adaptive" limits a tagged request
  only while a more certain one decodes (running batch): a bet while any non-bet decodes,
  an early request while an untagged one decodes. "off" never limits.
  SGLang runs a prefill step instead of a decode step, so a cap alone would split one long
  stall into back-to-back short ones. After a step that prefilled tagged tokens while
  sequences were decoding and nothing normal waits, one decode step is forced through
  SGLang's own prefill_decode_interval counter. When SGLang mixed the decodes into that
  prefill step (--enable-mixed-chunk, and nothing in the step prevented it: logprobs,
  input embeds, beams, decode KV), they already got their token, so none is forced.
"""

from __future__ import annotations

import dataclasses
import functools
import logging
import math
from collections.abc import Callable
from typing import Any

from sptc_vllm.policy import (
    STOP_REASON_DROPPED,
    STOP_REASON_REJECTED,
    PrefillAllowance,
    SptcClass,
    SptcConfig,
    admit_bet,
    bets_last,
    classify,
    scan_decoders,
)

logger = logging.getLogger("sptc_sglang")

CONFIG_ENV = "SPTC_SGLANG_CONFIG"  # JSON object of SptcConfig knobs; unset = plugin off


# --------------------------------------------------------------------------- requests
def req_class(req: Any) -> SptcClass:
    """Tag from sampling_params.custom_params["sptc_class"] (OpenAI body field custom_params)."""
    return classify(getattr(getattr(req, "sampling_params", None), "custom_params", None))


def is_bet(req: Any) -> bool:
    return req_class(req) is SptcClass.BET


def is_tagged(req: Any) -> bool:
    return req_class(req) is not SptcClass.NORMAL


def abort_reason(stop: str, detail: str) -> dict:
    """A graceful abort: no status_code, so SGLang's OpenAI layer returns a normal response
    (finish_reason "abort", matched_stop=stop) instead of an HTTP error, which OpenAI clients
    would retry."""
    return {"type": "abort", "message": f"{stop}: {detail}", "matched": stop}


def _invalid(req: Any) -> bool:
    """SGLang already failed the request (bad grammar, prompt too long, client abort before
    the grammar compiled): it runs one 1-token prefill and returns its own error. A bet in
    that state is left to SGLang, so the client gets that error, not a rejection."""
    return getattr(req, "to_finish", None) is not None


def retraction_order(original: Callable[[list], list[int]], reqs: list) -> list[int]:
    """Wraps ScheduleBatch._get_decode_retraction_order (most-preferred-to-keep first; the
    loop pops from the end), moving bets to the end so they are retracted first."""
    order = original(reqs)
    return bets_last(order, lambda i: is_bet(reqs[i]))


# --------------------------------------------------------------------------- step state
class StepState:
    """Per-scheduler state shared by the scheduler and the step's PrefillAdder."""

    def __init__(self, cfg: SptcConfig, *, allowance: bool, alternate: bool, page_size: int):
        self.cfg = cfg
        self.allowance = PrefillAllowance(
            cfg.spec_prefill_budget if allowance else 0,
            adaptive=cfg.prefill_allowance == "adaptive",
        )
        self.limiting = False  # allowance applies in this pass (no normal request waiting)
        self.alternate = alternate  # force a decode step after an unmixed tagged prefill step
        self.page_size = max(1, page_size)
        self.scheduler: Any = None  # the owning scheduler (its live waiting_queue)
        self.chunked_req: Any = None
        self.kv_usage0 = 0.0  # KV usage at step start (before this step's allocations)
        self.kv_capacity = 1
        self.refused: dict[int, str] = {}  # id(req) -> gate reason, this step
        self.allow_skipped: set[int] = set()  # id(req): bets skipped for the allowance, this step
        self.bet_prefilled = False  # this step: a bet's prefill used the allowance
        self.allow_closed = False  # this step: the allowance left a request chunked (pass closed)
        self.held: dict[str, int] = {}  # rid -> steps a gate-passing bet stayed waiting
        self.tagged_prefill = False  # this step prefilled bet/early requests under the allowance
        self.forced = False  # the plugin, not SGLang's own interval, deferred this step's prefill
        self.counts = {"rejected": 0, "dropped": 0, "admitted": 0}


# --------------------------------------------------------------------------- adder
def make_adder_class(base: type, AddReqResult: Any) -> type:
    """PrefillAdder subclass: gates bets and caps tagged prefill at the step allowance."""

    class SptcPrefillAdder(base):
        def __init__(self, *args, sptc_state: StepState, **kwargs):
            super().__init__(*args, **kwargs)
            self._sptc = st = sptc_state
            self._sptc_seen: tuple | None = None  # gate inputs, see _sptc_gate
            # Built after SGLang appended this pass's grammar-ready requests, so the live
            # queue is the full set of requests this pass can see.
            st.limiting = not st.allowance.unlimited and all(
                is_tagged(r) for r in st.scheduler.waiting_queue
            )

        def _sptc_limits(self, req) -> bool:
            """The allowance limits this tagged request in this pass."""
            st = self._sptc
            return st.limiting and st.allowance.applies(req_class(req), self._sptc_decoders)

        def _sptc_decoders(self) -> tuple[bool, bool]:
            """adaptive allowance: (untagged, non-bet) request decoding. SGLang's running
            batch is the decode batch."""
            rb = self.running_batch
            if rb is None:
                return False, False
            return scan_decoders((req_class(r), not r.finished()) for r in rb.reqs)

        # ---- gate
        def _sptc_gate(self):
            """admit_bet with the state at this point of the pass. The inputs change only
            when SGLang admits a request (can_run_list grows): the waiting queue and the
            running batch are fixed during the loop. So they are recomputed only then, and
            a long run of refused bets costs O(1) each instead of a queue scan (audit #24)."""
            st = self._sptc
            n = len(self.can_run_list)
            if self._sptc_seen is None or self._sptc_seen[0] != n:
                admitted = set(self.can_run_list)
                running = [r for r in self.running_batch.reqs if not r.finished()]
                num_running = len(running) + n
                cr = st.chunked_req
                if cr is not None and cr not in admitted and cr not in running:
                    num_running += 1  # a parked chunked request still holds a running slot
                self._sptc_seen = (
                    n,
                    num_running,
                    # the live queue: it includes requests SGLang appended during this pass
                    # (grammar compiled), which land behind the bets
                    any(not is_bet(r) and r not in admitted for r in st.scheduler.waiting_queue),
                    sum(r.extend_end - r.prefix_len for r in self.can_run_list),
                )
            _, num_running, nonbet_waiting, new_tokens = self._sptc_seen
            return admit_bet(
                num_running=num_running,
                nonbet_waiting=nonbet_waiting,
                kv_usage=st.kv_usage0 + new_tokens / st.kv_capacity,
                cfg=st.cfg,
            )

        # ---- allowance
        def _sptc_cap(self) -> int:
            ps = self._sptc.page_size
            return max(0, self._sptc.allowance.left) // ps * ps

        def _sptc_close(self) -> None:
            """The cap left a tagged request chunked. SGLang tracks one chunked request, so
            admit nothing else in this step (what SGLang does when a chunk fills the step)."""
            self._sptc_closed = True
            self._sptc.allow_closed = True
            self.rem_chunk_tokens = 0

        def add_chunked_req(self, req):
            st = self._sptc
            if not is_tagged(req) or not self._sptc_limits(req):
                return super().add_chunked_req(req)
            # The chunked request is added first in a step, so the allowance is full and
            # the cap is at least one page (_sptc_setup rounds the budget up to a page).
            cap = self._sptc_cap()
            if cap > 0:
                lim = self.chunked_req_limit
                self.chunked_req_limit = cap if lim is None else min(lim, cap)
            before = len(self.can_run_list)
            out = super().add_chunked_req(req)
            if len(self.can_run_list) > before:
                st.allowance.charge(req.extend_end - req.prefix_len)
                st.bet_prefilled |= is_bet(req)
            if out is not None:
                self._sptc_close()
            return out

        def add_one_req(self, req, has_chunked_req, truncation_align_size):
            st = self._sptc
            if getattr(self, "_sptc_closed", False):
                return AddReqResult.OTHER
            cls = req_class(req)
            if cls is SptcClass.NORMAL or _invalid(req):
                return super().add_one_req(req, has_chunked_req, truncation_align_size)
            if cls is SptcClass.BET:
                verdict = self._sptc_gate()
                if not verdict.admit:
                    st.refused[id(req)] = verdict.reason
                    return AddReqResult.CONTINUE  # skipped; aborted after the step
            if not self._sptc_limits(req):
                return self._sptc_add(req, has_chunked_req, truncation_align_size)
            cap = self._sptc_cap()
            if cap < st.page_size:
                if cls is SptcClass.BET:
                    st.allow_skipped.add(id(req))
                return AddReqResult.CONTINUE  # allowance spent: skip, never break
            # A request that fits the cap is admitted whole: SGLang aligns only chunks. One
            # that must be chunked below the alignment gets OTHER from SGLang and is skipped.
            saved = self.rem_chunk_tokens  # not None: the allowance needs chunked prefill
            self.rem_chunk_tokens = min(saved, cap)
            capped = self.rem_chunk_tokens
            before = len(self.can_run_list)
            try:
                res = self._sptc_add(req, has_chunked_req, truncation_align_size)
            finally:
                spent = capped - self.rem_chunk_tokens
                self.rem_chunk_tokens = saved - spent
            if len(self.can_run_list) > before:
                st.allowance.charge(spent)
                st.bet_prefilled |= cls is SptcClass.BET and spent > 0
                if self.new_chunked_req is req:
                    self._sptc_close()
                    return AddReqResult.OTHER
                return self.budget_state()  # the verdict under the real chunk budget
            # Not admitted. NO_TOKEN (KV full) is real; anything else may come from the cap
            # (e.g. a chunk floored to 0 pages), so skip instead of stopping the loop.
            return res if res is AddReqResult.NO_TOKEN else AddReqResult.CONTINUE

        def _sptc_add(self, req, has_chunked_req, truncation_align_size):
            before = len(self.can_run_list)
            res = super().add_one_req(req, has_chunked_req, truncation_align_size)
            if is_bet(req):
                if len(self.can_run_list) > before:
                    self._sptc.counts["admitted"] += 1
                elif res is AddReqResult.NO_TOKEN:
                    # SGLang's own KV reservation refused the bet. Returned as is, SGLang
                    # would stop the pass and set batch_is_full, which blocks certain work
                    # until a running request finishes. Skip it instead: the bet is gated
                    # again after the step and held like any bet the step did not admit.
                    return AddReqResult.CONTINUE
            return res

    SptcPrefillAdder.__name__ = SptcPrefillAdder.__qualname__ = f"Sptc{base.__name__}"
    return SptcPrefillAdder


# --------------------------------------------------------------------------- scheduler
def make_scheduler_class(
    base: type,
    *,
    AddReqResult: Any,
    finish_abort: Callable[[Any, str, str], None],
    finish_reason: Callable[[str, str], Any],
    retract: Callable[[Any, Any], None],
    cfg_loader: Callable[[], SptcConfig],
    checks: Callable[[Any], tuple[list[str], list[str]]],
) -> type:
    """Scheduler subclass. `checks(scheduler)` returns (fatal problems, reasons to switch
    the prefill allowance off); `finish_abort(req, stop, detail)` marks a request finished
    with abort_reason(stop, detail); `finish_reason(stop, detail)` is that finish reason
    (a FINISH_ABORT) for SGLang code that takes one; `retract(scheduler, req)` frees a
    request's KV and resets it for a new prefill (SGLang's retract_all). plugin.py supplies
    the SGLang ones."""

    class SptcScheduler(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._sptc_setup()

        def _sptc_setup(self) -> None:
            cfg = cfg_loader()
            fatal, no_allowance = checks(self)
            if fatal:
                raise ValueError("sptc_sglang does not support: " + "; ".join(fatal))
            allowance = cfg.allowance_budget > 0  # spec_prefill_budget, 0 when "off"
            if allowance and no_allowance:
                logger.warning(
                    "sptc: prefill allowance off (%s); gate and dropping stay on",
                    "; ".join(no_allowance),
                )
                allowance = False
            page = max(1, int(self.page_size or 1))
            # SGLang cuts a chunk to whole pages and, with deterministic inference or DSA, to
            # truncation_align_size. A budget below that unit could never chunk a long tagged
            # prompt, so it would wait while only tagged work waits.
            align = int(getattr(self, "truncation_align_size", None) or 1)
            unit = math.lcm(page, align)
            if allowance and cfg.spec_prefill_budget % unit:
                budget = -(-cfg.spec_prefill_budget // unit) * unit
                logger.warning(
                    "sptc: spec_prefill_budget rounded up to %d (page %d, chunk alignment %d)",
                    budget, page, align,
                )
                cfg = dataclasses.replace(cfg, spec_prefill_budget=budget)
            self._sptc = StepState(cfg, allowance=allowance, alternate=allowance, page_size=page)
            self._sptc.scheduler = self
            self._sptc_adders: dict[type, type] = {}
            logger.info("sptc scheduler on: %s (allowance %s)", cfg, "on" if allowance else "off")

        # ---- hooks
        def get_prefill_adder_class(self):
            base_adder = super().get_prefill_adder_class()
            if not hasattr(self, "_sptc"):  # called before __init__ finished: vanilla
                return base_adder
            cls = self._sptc_adders.get(base_adder)
            if cls is None:
                cls = self._sptc_adders[base_adder] = make_adder_class(base_adder, AddReqResult)
            return functools.partial(cls, sptc_state=self._sptc)

        def get_next_batch_to_run(self, running_batch, last_batch):
            if not hasattr(self, "_sptc"):
                return super().get_next_batch_to_run(running_batch, last_batch)
            st = self._sptc
            st.tagged_prefill = False
            try:
                plan = super().get_next_batch_to_run(running_batch, last_batch)
            finally:
                st.forced = False  # read by update_running_batch in this step only
            if st.alternate and st.limiting and st.tagged_prefill and self._sptc_should_force_decode(plan):
                if self._prefill_decode_interval_remaining == 0:  # else SGLang defers anyway
                    self._prefill_decode_interval_remaining = 1
                    st.forced = True
            return plan

        def _sptc_should_force_decode(self, plan) -> bool:
            batch = plan.batch_to_run
            if batch is None or not batch.forward_mode.is_extend():
                return False
            if not any(not r.finished() for r in plan.running_batch.reqs):
                return False  # nothing is decoding: nothing to protect
            return not any(not is_tagged(r) for r in self.waiting_queue)

        def _get_new_batch_prefill_raw(self, prefill_delayer_single_pass, running_batch):
            if not hasattr(self, "_sptc"):
                return super()._get_new_batch_prefill_raw(
                    prefill_delayer_single_pass=prefill_delayer_single_pass,
                    running_batch=running_batch,
                )
            st = self._sptc
            st.allowance.reset()
            st.limiting = False  # set by the adder, if SGLang builds one in this pass
            st.refused.clear()
            st.allow_skipped.clear()
            st.bet_prefilled = False
            st.allow_closed = False
            st.chunked_req = self.chunked_req
            if any(is_bet(r) for r in self.waiting_queue):
                self.waiting_queue = bets_last(self.waiting_queue, is_bet)
            # always: a bet can also join during the pass (grammar compiled), behind the rest
            st.kv_usage0, st.kv_capacity = self._sptc_kv()
            new_batch, running_batch = super()._get_new_batch_prefill_raw(
                prefill_delayer_single_pass=prefill_delayer_single_pass,
                running_batch=running_batch,
            )
            # decoding_reqs is set when SGLang mixed the decodes into this step; with
            # --enable-mixed-chunk it still cannot mix in every step (audit #8)
            if new_batch is not None and getattr(new_batch, "decoding_reqs", None) is None:
                st.tagged_prefill = any(  # prefilled under the allowance
                    is_tagged(r) and st.allowance.applied(req_class(r)) for r in new_batch.reqs
                )
            self._sptc_end_step(new_batch, running_batch)
            return new_batch, running_batch

        def update_running_batch(self, batch):
            if hasattr(self, "_sptc"):
                self._sptc_free_chunked(batch)
            return super().update_running_batch(batch)

        def _add_request_to_queue(self, req, is_retracted: bool = False):
            # A running bet that SGLang retracted is dropped, not requeued: on KV pressure
            # (is_retracted), and on pause_generation(mode="retract"), which requeues every
            # running request without the flag after Req.reset_for_retract set
            # req.is_retracted. Requeued, it would be gated again as a new bet.
            if hasattr(self, "_sptc") and is_bet(req) and (
                is_retracted or getattr(req, "is_retracted", False)
            ):
                detail = "kv_pressure" if is_retracted else "retracted"
                self._sptc_abort(req, STOP_REASON_DROPPED, detail)
                self._sptc.counts["dropped"] += 1
                return
            return super()._add_request_to_queue(req, is_retracted=is_retracted)

        # ---- helpers
        def _sptc_kv(self) -> tuple[float, int]:
            stats = self.pool_stats_observer.get_pool_stats()
            cap = int(getattr(stats, "full_capacity", None) or self.max_total_num_tokens)
            return float(stats.get_max_pool_usage()), max(1, cap)

        def _sptc_end_step(self, new_batch, running_batch) -> None:
            st = self._sptc
            bets = [r for r in self.waiting_queue if is_bet(r) and not _invalid(r)]
            if not bets:
                st.held.clear()
                return
            live: dict[int, Any] = {}
            for r in running_batch.reqs:
                live[id(r)] = r
            if new_batch is not None:
                for r in new_batch.reqs:
                    live[id(r)] = r
            if self.chunked_req is not None:
                live[id(self.chunked_req)] = self.chunked_req
            num_running = sum(1 for r in live.values() if not r.finished())
            nonbet_waiting = any(not is_bet(r) for r in self.waiting_queue)
            kv_usage, _ = self._sptc_kv()  # this step's prefill KV is allocated by now
            rejected = []
            for r in bets:
                reason = st.refused.get(id(r))
                if reason is None:
                    v = admit_bet(
                        num_running=num_running, nonbet_waiting=nonbet_waiting,
                        kv_usage=kv_usage, cfg=st.cfg,
                    )
                    if not v.admit:
                        reason = v.reason
                    elif st.bet_prefilled and (st.allow_closed or id(r) in st.allow_skipped):
                        # kept out by the allowance (skipped, or the pass closed on a chunk
                        # the cap left) while a bet's prefill used it: held, this step not
                        # counted (as sptc_vllm, audit #10 / #38)
                        st.held.setdefault(r.rid, 0)
                    else:
                        held = st.held.get(r.rid, 0) + 1
                        if held > st.cfg.bet_hold_steps:
                            reason = "held_too_long"
                        else:
                            st.held[r.rid] = held
                if reason is not None:
                    rejected.append((r, reason))
            if rejected:
                gone = {id(r) for r, _ in rejected}
                self.waiting_queue = [r for r in self.waiting_queue if id(r) not in gone]
                for r, reason in rejected:
                    self._sptc_abort(r, STOP_REASON_REJECTED, reason)
                    st.held.pop(r.rid, None)
                st.counts["rejected"] += len(rejected)
            waiting = {r.rid for r in self.waiting_queue}
            for rid in [rid for rid in st.held if rid not in waiting]:
                del st.held[rid]

        def _sptc_free_chunked(self, batch) -> None:
            """A tagged request in the middle of a chunked prefill holds KV but is not in the
            decode batch, so retract_decode cannot pick it: in a decode step between its
            chunks (forced by the allowance) SGLang would retract a decoder instead (audit
            #7). When this decode step is about to retract (SGLang's own test: nothing
            finishing in flight, and check_decode_mem fails for the unfinished requests):
            - a bet is dropped, through SGLang's own chunked-request abort;
            - an early request is retracted and requeued, as SGLang's pause(retract) does
              with the chunked request, if the plugin forced this step and SGLang's
              retraction order would pick it first among the decoders plus itself. Stock
              SGLang runs the chunks back to back, then retracts in that order, where a
              long prompt with no output yet goes first.
            Both free the request's KV; SGLang then checks again and retracts only if KV
            is still short."""
            cr = self.chunked_req
            if cr is None or cr.finished() or not is_tagged(cr):
                return
            if not is_bet(cr) and not self._sptc.forced:
                return  # SGLang's own decode step (prefill_decode_interval): stock behaviour
            if not self._sptc_decode_would_retract(batch):
                return
            if is_bet(cr):
                # SGLang finishes it with this reason and sends it to the client (no output yet)
                cr.discard_output_reason = finish_reason(STOP_REASON_DROPPED, "kv_pressure")
                self._pending_chunked_abort_req = cr
                self.process_pending_chunked_abort()
                self._sptc.counts["dropped"] += 1
                logger.debug("sptc: %s %s (chunked, kv_pressure)", STOP_REASON_DROPPED, cr.rid)
                return
            reqs = [r for r in batch.reqs if not r.finished()] + [cr]
            if reqs[batch._get_decode_retraction_order(reqs)[-1]] is not cr:
                return  # SGLang retracts another request first (a bet, with the plugin's order)
            retract(self, cr)
            self.chunked_req = None
            self._add_request_to_queue(cr, is_retracted=True)
            logger.debug("sptc: retracted %s (chunked early request, kv_pressure)", cr.rid)

        def _sptc_decode_would_retract(self, batch) -> bool:
            live = [i for i, r in enumerate(batch.reqs) if not r.finished()]
            if not live or self._reqs_finishing_inflight(batch):
                return False
            return not batch.check_decode_mem(selected_indices=live)

        def _sptc_abort(self, req, stop: str, detail: str) -> None:
            """Finish a request that is not in the waiting queue (any more) and holds no KV:
            the cache-side cleanup of Scheduler.abort_request's "abort method 1", then a
            finished output through the normal path (scheduler -> detokenizer -> tokenizer),
            as Scheduler._reject_sampling_mask_request does. Unlike a direct AbortReq to the
            tokenizer it cannot overtake the request's last tokens, and the detokenizer
            frees its state."""
            self._release_aborted_request(req)
            self.beam_coordinator.retire_group(req)
            finish_abort(req, stop, detail)
            self.output_streamer.stream_output([req], req.return_logprob)
            logger.debug("sptc: %s %s (%s)", stop, req.rid, detail)

    SptcScheduler.__name__ = SptcScheduler.__qualname__ = "SptcScheduler"
    return SptcScheduler
