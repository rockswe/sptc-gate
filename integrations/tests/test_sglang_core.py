"""sptc_sglang/core.py on fakes: no SGLang import, no GPU.

FakeScheduler and FakeAdder reproduce the control flow of SGLang v0.5.22's
Scheduler._get_new_batch_prefill_raw / get_next_batch_to_run and PrefillAdder that the
plugin relies on (bets reached in queue order, the loop stops on any result other than
CONTINUE, rem_chunk_tokens caps a chunk, a parked chunked request, prefill-first steps).
tests/test_sglang_api_static.py checks that the real sources still have that shape; the
Kaggle smoke test (kaggle/sptc_sglang_smoke.py) checks the real thing end to end.
"""

from __future__ import annotations

import enum
from types import SimpleNamespace

import pytest

from sptc_sglang import core
from sptc_vllm.policy import SptcConfig


class AddReqResult(enum.Enum):
    CONTINUE = enum.auto()
    NO_TOKEN = enum.auto()
    OTHER = enum.auto()


C, NO_TOKEN, OTHER = AddReqResult.CONTINUE, AddReqResult.NO_TOKEN, AddReqResult.OTHER


class Req:
    def __init__(self, rid, prompt=100, cls=None, max_new=16):
        self.rid = rid
        self.n = prompt
        self.max_new = max_new
        self.prefix_len = 0
        self.extend_end = 0
        self.sampling_params = SimpleNamespace(
            custom_params={"sptc_class": cls} if cls else None
        )
        self.return_logprob = False
        self.finished_reason = None
        self.to_finish = None
        self.done = False

    def finished(self):
        return self.done or self.finished_reason is not None

    def __repr__(self):
        return self.rid


class Batch:
    def __init__(self, reqs, extend):
        self.reqs = list(reqs)
        self.forward_mode = SimpleNamespace(is_extend=lambda: extend)
        self.decode_mem_ok = True  # ScheduleBatch.check_decode_mem: KV for one more token

    def check_decode_mem(self, selected_indices=None):
        return self.decode_mem_ok

    @staticmethod
    def _get_decode_retraction_order(reqs):
        """SGLang's sort is left out (the vendored tests run it): list order, with the
        plugin's hook moving bets to the end, which retract_decode pops first."""
        return core.retraction_order(lambda rs: list(range(len(rs))), reqs)


class FakeAdder:
    """PrefillAdder's budget logic, reduced: chunk/input budgets, KV, chunking."""

    def __init__(self, running_batch, rem_input_tokens, rem_chunk_tokens, kv_free):
        self.running_batch = running_batch
        self.rem_input_tokens = rem_input_tokens
        self.rem_chunk_tokens = rem_chunk_tokens
        self.kv_free = kv_free
        self.can_run_list = []
        self.new_chunked_req = None
        self.chunked_req_limit = None
        self.park = False  # add_chunked_req parks the continuation (SGLang: hybrid SWA)

    def budget_state(self):
        if self.kv_free <= 0:
            return NO_TOKEN
        if self.rem_input_tokens <= 0:
            return OTHER
        if self.rem_chunk_tokens is not None and self.rem_chunk_tokens <= 0:
            return OTHER
        return C

    def _charge(self, n):
        self.rem_input_tokens -= n
        if self.rem_chunk_tokens is not None:
            self.rem_chunk_tokens -= n
        self.kv_free -= n

    def add_chunked_req(self, req):
        if self.park:
            return req  # computes nothing this step; stays the chunked request
        rem = self.rem_chunk_tokens
        if self.chunked_req_limit is not None:
            assert self.chunked_req_limit > 0
            rem = min(rem, self.chunked_req_limit)
        left = req.n - req.prefix_len
        new = min(left, rem)
        req.extend_end = req.prefix_len + new
        self.can_run_list.append(req)
        self._charge(new)
        return req if left > new else None

    def add_one_req(self, req, has_chunked_req, truncation_align_size):
        left = req.n - req.prefix_len
        if left + req.max_new > self.kv_free:
            return NO_TOKEN
        ext = left
        if self.rem_chunk_tokens is not None and left > self.rem_chunk_tokens:
            ext = self.rem_chunk_tokens
            if ext <= 0:
                return OTHER
            self.new_chunked_req = req
        req.extend_end = req.prefix_len + ext
        self.can_run_list.append(req)
        self._charge(ext)
        return self.budget_state()


class FakeScheduler:
    """The parts of Scheduler the plugin overrides or calls, with the same control flow."""

    def __init__(self, *, chunk=2048, max_running=64, kv_cap=100_000, mixed=False):
        self.waiting_queue = []
        self.running_batch = Batch([], extend=False)
        self.running_batch.batch_is_full = False
        self.chunked_req = None
        self._pending_chunked_abort_req = None
        self.park_chunk = False
        self.finishing = []
        self.chunked_prefill_size = chunk
        self.max_running = max_running
        self.max_total_num_tokens = kv_cap
        self.kv_used = 0
        self.is_mixed_chunk = mixed
        self.page_size = 1
        self._prefill_decode_interval_remaining = 0
        self.late_arrivals = []  # appended at the start of the next prefill pass (grammar)
        self.aborted = []
        self.requeued = []
        self.released = []
        self.retracted = []  # retract(): KV freed, reset for a new prefill
        self.retired = []
        self.beam_coordinator = SimpleNamespace(retire_group=lambda req: self.retired.append(req.rid))
        sched = self

        class Streamer:  # the normal output path: only finished requests are recorded
            def stream_output(self, reqs, return_logprob):
                for r in reqs:
                    assert r.finished_reason is not None
                    sched.aborted.append((r.rid, r.finished_reason))

        self.output_streamer = Streamer()

        class Observer:
            def get_pool_stats(self):
                return SimpleNamespace(
                    full_capacity=sched.max_total_num_tokens,
                    get_max_pool_usage=lambda: sched.kv_used / sched.max_total_num_tokens,
                )

        self.pool_stats_observer = Observer()

    # --- what the plugin overrides
    def get_prefill_adder_class(self):
        return FakeAdder

    def _get_new_batch_prefill_raw(self, prefill_delayer_single_pass, running_batch):
        self.waiting_queue.extend(self.late_arrivals)
        self.late_arrivals = []
        if not running_batch.reqs:
            running_batch.batch_is_full = False
        if (running_batch.batch_is_full or not self.waiting_queue) and self.chunked_req is None:
            return None, running_batch
        adder = self.get_prefill_adder_class()(
            running_batch, 16384, self.chunked_prefill_size,
            self.max_total_num_tokens - self.kv_used,
        )
        adder.park = self.park_chunk
        if self.chunked_req is not None:
            self.chunked_req = adder.add_chunked_req(self.chunked_req)
        for req in self.waiting_queue:
            if len(adder.can_run_list) >= self.max_running - len(running_batch.reqs):
                running_batch.batch_is_full = True
            if running_batch.batch_is_full:
                break
            res = adder.add_one_req(
                req, has_chunked_req=self.chunked_req is not None, truncation_align_size=None
            )
            if res != AddReqResult.CONTINUE:
                if res == AddReqResult.NO_TOKEN:
                    running_batch.batch_is_full = bool(adder.can_run_list or running_batch.reqs)
                break
        if not adder.can_run_list:
            return None, running_batch
        run = set(adder.can_run_list)
        self.waiting_queue = [x for x in self.waiting_queue if x not in run]
        if adder.new_chunked_req is not None:
            assert self.chunked_req is None
            self.chunked_req = adder.new_chunked_req
        self.kv_used += sum(r.extend_end - r.prefix_len for r in adder.can_run_list)
        batch = Batch(adder.can_run_list, extend=True)
        batch.decoding_reqs = None
        if self.is_mixed_chunk and running_batch.reqs and not any(
            r.return_logprob for r in running_batch.reqs + batch.reqs
        ):
            batch.decoding_reqs = list(running_batch.reqs)  # decodes ride along
        return batch, running_batch

    def get_next_batch_to_run(self, running_batch, last_batch):
        if self._prefill_decode_interval_remaining:
            self._prefill_decode_interval_remaining -= 1
            new = None
        else:
            new, running_batch = self._get_new_batch_prefill_raw(
                prefill_delayer_single_pass=None, running_batch=running_batch
            )
        if new is not None:
            batch = new
        else:
            batch = self.update_running_batch(running_batch) if running_batch.reqs else None
        return SimpleNamespace(batch_to_run=batch, running_batch=running_batch)

    def update_running_batch(self, batch):
        return batch  # no retraction in the fakes: the vendored-source tests cover it

    def _reqs_finishing_inflight(self, batch):
        return self.finishing  # overlap: requests whose in-flight token is their last

    def process_pending_chunked_abort(self):
        """SGLang's chunked-request abort: finish with discard_output_reason, free, report."""
        req = self._pending_chunked_abort_req
        if req is None or req is not self.chunked_req:
            return
        req.finished_reason = req.discard_output_reason.to_json()
        self.released.append(req.rid)
        self.chunked_req = self._pending_chunked_abort_req = None
        self.aborted.append((req.rid, req.finished_reason))

    def _add_request_to_queue(self, req, is_retracted=False):
        self.requeued.append((req.rid, is_retracted))
        self.waiting_queue.append(req)

    def _release_aborted_request(self, req):
        self.released.append(req.rid)

    # --- test driver
    def finish_prefill(self, batch):
        """End of a prefill step: finished prompts start decoding (prefix catches up)."""
        for r in batch.reqs:
            r.prefix_len = r.extend_end
            if r is not self.chunked_req and r not in self.running_batch.reqs:
                self.running_batch.reqs.append(r)


def finish_abort(req, stop, detail):
    req.finished_reason = core.abort_reason(stop, detail)  # plugin.py: a FINISH_ABORT


def retract(s, req):  # plugin.py: SGLang's retract_all
    s.retracted.append(req.rid)
    req.prefix_len = req.extend_end = 0


def finish_reason(stop, detail):  # plugin.py: SptcFinishAbort
    fr = core.abort_reason(stop, detail)
    return SimpleNamespace(message=fr["message"], status_code=None, to_json=lambda: fr)


def build(cfg=SptcConfig(), fatal=(), no_allowance=(), **kw):
    cls = core.make_scheduler_class(
        FakeScheduler,
        AddReqResult=AddReqResult,
        finish_abort=finish_abort,
        finish_reason=finish_reason, retract=retract,
        cfg_loader=lambda: cfg,
        checks=lambda s: (list(fatal), list(no_allowance)),
    )
    return cls(**kw)


def step(s):
    plan = s.get_next_batch_to_run(s.running_batch, None)
    b = plan.batch_to_run
    if b is not None and b.forward_mode.is_extend():
        s.finish_prefill(b)
    return b


def decoding(s, n, prefix="d"):
    for i in range(n):
        r = Req(f"{prefix}{i}")
        r.prefix_len = r.extend_end = r.n
        s.running_batch.reqs.append(r)


def reasons(s):
    return {rid: fr["message"].split(": ", 1)[1] for rid, fr in s.aborted}


# --------------------------------------------------------------------------- basics
def test_tags_and_abort_reason():
    assert core.req_class(Req("a", cls="bet")) is core.SptcClass.BET
    assert core.req_class(Req("a", cls="early")) is core.SptcClass.EARLY
    assert core.req_class(Req("a", cls="nonsense")) is core.SptcClass.NORMAL
    assert core.req_class(SimpleNamespace(sampling_params=None)) is core.SptcClass.NORMAL
    fr = core.abort_reason("sptc_bet_rejected", "free_window")
    assert fr == {
        "type": "abort", "message": "sptc_bet_rejected: free_window",
        "matched": "sptc_bet_rejected",
    }
    assert "status_code" not in fr  # graceful: a normal response, not an HTTP error


@pytest.mark.parametrize("mode", ["fixed", "adaptive", "off"])
def test_untagged_traffic_matches_base(mode):
    """Without tags every hook passes through: same admissions, step by step."""

    def run(s):
        out = []
        for i in range(12):
            s.waiting_queue.append(Req(f"r{i}", prompt=300 + 97 * i))
        s.waiting_queue.append(Req("long", prompt=5000))
        for _ in range(12):
            b = step(s)
            out.append(None if b is None else [(r.rid, r.extend_end) for r in b.reqs])
        return out

    base = FakeScheduler(chunk=1024, max_running=8)
    cfg = SptcConfig(prefill_allowance=mode)
    assert run(build(cfg, chunk=1024, max_running=8)) == run(base)


def test_fatal_checks_stop_the_server():
    with pytest.raises(ValueError, match="does not support: DP attention"):
        build(fatal=["DP attention"])


def test_budget_rounded_up_to_page():
    class Paged(FakeScheduler):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.page_size = 64

    cls = core.make_scheduler_class(
        Paged, AddReqResult=AddReqResult, finish_abort=finish_abort, finish_reason=finish_reason, retract=retract,
        cfg_loader=lambda: SptcConfig(spec_prefill_budget=500), checks=lambda s: ([], []),
    )
    assert cls()._sptc.allowance.budget == 512


def test_cap_is_whole_pages():
    """The cap handed to SGLang as rem_chunk_tokens / chunked_req_limit is floored to whole
    pages: SGLang's add_chunked_req does not floor a chunked_req_limit itself, so a ragged cap
    would end a continuation mid-page. (On the supported configs the cap is already whole
    pages there: the continuation comes first, with the full, page-rounded budget.)"""
    class Paged(FakeScheduler):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.page_size = 16

    cls = core.make_scheduler_class(
        Paged, AddReqResult=AddReqResult, finish_abort=finish_abort, finish_reason=finish_reason, retract=retract,
        cfg_loader=lambda: SptcConfig(spec_prefill_budget=512), checks=lambda s: ([], []),
    )
    s = cls()
    ad = _adder(s)
    s._sptc.allowance.charge(290)
    assert ad._sptc_cap() == 208


def test_allowance_off_when_checks_say_so():
    s = build(no_allowance=["chunked prefill is off"])
    assert s._sptc.allowance.unlimited and not s._sptc.alternate


# --------------------------------------------------------------------------- gate
def test_idle_bet_admitted():
    s = build()
    s.waiting_queue.append(Req("b", cls="bet"))
    b = step(s)
    assert [r.rid for r in b.reqs] == ["b"] and not s.aborted
    assert s._sptc.counts["admitted"] == 1


def test_bets_moved_behind_certain_work():
    s = build()
    s.waiting_queue += [Req("b1", cls="bet"), Req("n1"), Req("e1", cls="early"), Req("b2", cls="bet")]
    b = step(s)
    assert [r.rid for r in b.reqs] == ["n1", "e1", "b1", "b2"]


def test_free_window_counts_admissions_in_this_step():
    s = build(SptcConfig(free_window=3))
    decoding(s, 1)
    s.waiting_queue += [Req(f"b{i}", cls="bet") for i in range(4)]
    b = step(s)
    assert [r.rid for r in b.reqs] == ["b0", "b1"]  # 1 running + 2 = window of 3
    assert reasons(s) == {"b2": "free_window", "b3": "free_window"}
    assert s.waiting_queue == []


def test_bet_refused_while_certain_work_waits():
    s = build(chunk=200)
    s.waiting_queue += [Req("n1", 150), Req("n2", 150), Req("n3", 100), Req("b", cls="bet")]
    b = step(s)
    assert [r.rid for r in b.reqs] == ["n1", "n2"]  # n2 chunked; the loop stopped there
    assert reasons(s) == {"b": "nonbet_waiting"}  # n3 still waits


def test_chunked_normal_request_counts_as_running_not_waiting():
    s = build(chunk=200)
    s.waiting_queue += [Req("n1", 150), Req("n2", 150), Req("b", cls="bet")]
    step(s)
    assert s.chunked_req.rid == "n2" and not s.aborted and s._sptc.held == {"b": 1}


def test_refused_bet_never_blocks_later_certain_work():
    """A normal request that lands behind the bets (grammar ready) still runs."""
    s = build(SptcConfig(free_window=1))
    decoding(s, 1)
    s.waiting_queue += [Req("b", cls="bet")]
    s.late_arrivals = [Req("n_late")]
    b = step(s)
    assert [r.rid for r in b.reqs] == ["n_late"]
    assert reasons(s) == {"b": "nonbet_waiting"}  # refused in the loop, then skipped


def test_kv_reserve():
    s = build(SptcConfig(kv_reserve=0.2))
    s.kv_used = 85_000
    s.waiting_queue.append(Req("b", cls="bet"))
    assert step(s) is None
    assert reasons(s) == {"b": "kv_reserve"}


def test_kv_counts_admissions_in_this_step():
    s = build(SptcConfig(kv_reserve=0.2), kv_cap=10_000)
    s.kv_used = 7_000
    s.waiting_queue += [Req("n", prompt=1_500), Req("b", cls="bet")]
    s.waiting_queue[0].max_new = 0
    b = step(s)
    assert [r.rid for r in b.reqs] == ["n"]
    assert reasons(s) == {"b": "kv_reserve"}  # 0.70 at step start, 0.85 after n


def test_bet_refused_by_sglang_kv_budget_is_skipped_not_a_stop():
    """Audit #21: NO_TOKEN for a bet would make SGLang set batch_is_full and stop the pass."""
    s = build(SptcConfig(bet_hold_steps=2), kv_cap=10_000)
    decoding(s, 1)
    s.waiting_queue += [Req("b_big", prompt=9_990, cls="bet"), Req("b", prompt=10, cls="bet")]
    b = step(s)
    assert [r.rid for r in b.reqs] == ["b"] and not s.running_batch.batch_is_full
    assert s._sptc.held == {"b_big": 1}  # gate passed, SGLang refused: held, re-tried


def test_refused_bets_do_not_rescan_the_queue(monkeypatch):
    """Audit #24: gating each of N refused bets used to scan the waiting queue (O(N^2) per
    pass: about 0.7 s for 1000 bets on the fakes). The gate inputs only change when a
    request is admitted, so the pass stays linear."""
    calls = []
    real = core.is_bet
    monkeypatch.setattr(core, "is_bet", lambda r: calls.append(1) or real(r))
    s = build(SptcConfig(free_window=8), max_running=4096)
    decoding(s, 7)
    n = 400
    s.waiting_queue += [Req(f"b{i}", prompt=50, cls="bet") for i in range(n)]
    step(s)
    assert len(s.aborted) == n - 1 and s._sptc.counts["admitted"] == 1
    assert len(calls) < 12 * n  # was about n * n / 2


def test_bet_rejected_when_batch_full_before_the_loop():
    """SGLang returns before its loop when the batch is full: the end-of-step gate decides."""
    s = build(SptcConfig(free_window=2), max_running=2)
    decoding(s, 2)
    s.running_batch.batch_is_full = True
    s.waiting_queue.append(Req("b", cls="bet"))
    step(s)
    assert reasons(s) == {"b": "free_window"}


def test_gate_passing_bet_is_held_then_rejected():
    """Gate passes but the allowance is spent by early work every step: held, then
    rejected after bet_hold_steps."""
    s = build(SptcConfig(spec_prefill_budget=64, bet_hold_steps=2), chunk=4096)
    s.waiting_queue += [Req("e", prompt=10_000, cls="early"), Req("b", cls="bet")]
    seen = []
    for _ in range(4):
        step(s)
        seen.append(dict(s._sptc.held))
    assert seen[0] == {"b": 1} and seen[1] == {"b": 2}
    assert reasons(s) == {"b": "held_too_long"}


def test_hold_not_counted_while_another_bets_prefill_takes_the_allowance():
    """Audit #38, as sptc_vllm #10: b2 passes the gate every step, but b1's chunked prefill
    uses the whole allowance (and closes the pass: SGLang keeps one chunked request). Those
    steps are not counted, so b2 is not rejected held_too_long; early work taking the
    allowance still counts (test above)."""
    s = build(SptcConfig(spec_prefill_budget=64, bet_hold_steps=2), chunk=4096)
    s.waiting_queue += [Req("b1", prompt=10_000, cls="bet"), Req("b2", cls="bet")]
    for _ in range(5):
        step(s)
    assert s.chunked_req.rid == "b1" and s._sptc.held == {"b2": 0}
    assert not reasons(s) and [r.rid for r in s.waiting_queue] == ["b2"]


def test_hold_zero_rejects_unadmitted_bets_at_once():
    s = build(SptcConfig(spec_prefill_budget=64, bet_hold_steps=0), chunk=4096)
    s.waiting_queue += [Req("e", prompt=10_000, cls="early"), Req("b", cls="bet")]
    step(s)
    assert reasons(s) == {"b": "held_too_long"}


# --------------------------------------------------------------------------- allowance
def test_allowance_caps_tagged_prefill():
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    s.waiting_queue += [
        Req("e1", prompt=400, cls="early"), Req("e2", prompt=400, cls="early"),
        Req("e3", prompt=50, cls="early"),
    ]
    b = step(s)
    assert {r.rid: r.extend_end for r in b.reqs} == {"e1": 400, "e2": 112}
    assert s.chunked_req.rid == "e2"  # chunked at the allowance; nothing else joins
    assert [r.rid for r in s.waiting_queue] == ["e3"]
    assert s._sptc.allowance.left == 0


def _adder(s):
    """A PrefillAdder for scheduler s, as SGLang builds it for one pass."""
    s._sptc.allowance.reset()
    return s.get_prefill_adder_class()(s.running_batch, 16384, s.chunked_prefill_size, 10**6)


def test_one_chunked_request_per_step():
    """After the cap leaves a tagged request chunked, nothing else is admitted in the pass
    (SGLang tracks a single chunked request), whatever the rest of the chunk budget."""
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    ad = _adder(s)
    assert s._sptc.limiting
    assert ad.add_one_req(s.waiting_queue[0], False, None) is OTHER
    assert ad.new_chunked_req.rid == "e" and ad.rem_chunk_tokens == 0
    assert ad.add_one_req(Req("n", prompt=10), True, None) is OTHER
    assert [r.rid for r in ad.can_run_list] == ["e"]


def test_unfinished_tagged_continuation_closes_the_pass():
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    e = Req("e", prompt=1500, cls="early")
    e.prefix_len = 512
    s.chunked_req = e
    ad = _adder(s)
    assert ad.add_chunked_req(e) is e and e.extend_end == 1024
    assert ad.add_one_req(Req("n", prompt=10), True, None) is OTHER


def test_no_cap_while_normal_work_waits():
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    s.waiting_queue += [Req("e1", prompt=400, cls="early"), Req("e2", prompt=400, cls="early"),
                        Req("n", prompt=900)]
    b = step(s)
    assert {r.rid: r.extend_end for r in b.reqs} == {"e1": 400, "e2": 400, "n": 900}


def test_spent_allowance_skips_tagged_requests_never_breaks():
    s = build(SptcConfig(spec_prefill_budget=256), chunk=2048)
    s.waiting_queue += [Req("e1", prompt=256, cls="early"), Req("e2", prompt=100, cls="early")]
    ad = _adder(s)
    assert ad.add_one_req(s.waiting_queue[0], False, None) is C
    assert ad.add_one_req(s.waiting_queue[1], False, None) is C  # skipped, not a stop
    assert ad.add_one_req(Req("n", prompt=50), False, None) is C  # admitted behind it
    assert [r.rid for r in ad.can_run_list] == ["e1", "n"]
    assert ad.rem_chunk_tokens == 2048 - 256 - 50  # the cap was undone


def test_spent_allowance_in_a_full_step():
    s = build(SptcConfig(spec_prefill_budget=256), chunk=2048)
    s.waiting_queue += [Req("e1", prompt=256, cls="early"), Req("e2", prompt=100, cls="early"),
                        Req("b", cls="bet")]
    b = step(s)
    assert [r.rid for r in b.reqs] == ["e1"]
    assert [r.rid for r in s.waiting_queue] == ["e2"]  # skipped by the allowance, waits
    assert reasons(s) == {"b": "nonbet_waiting"}  # early work waiting counts, as on vLLM


def test_chunked_tagged_request_capped_by_allowance():
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    decoding(s, 1)
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    ends = []
    for _ in range(6):
        b = step(s)
        if b is not None and b.forward_mode.is_extend():
            ends.append(b.reqs[0].extend_end)
    assert ends == [512, 1024, 1500]


def test_decode_step_forced_after_tagged_prefill():
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    decoding(s, 1)
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    modes = []
    for _ in range(6):
        b = step(s)
        modes.append("P" if b is not None and b.forward_mode.is_extend() else "D")
    assert modes == ["P", "D", "P", "D", "P", "D"]


def test_no_forced_decode_without_decoders_or_with_normal_waiting_or_mixed():
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    step(s)
    assert s._prefill_decode_interval_remaining == 0  # nothing was decoding

    s = build(SptcConfig(spec_prefill_budget=512), chunk=1000)
    decoding(s, 1)
    s.waiting_queue += [Req("e", prompt=1500, cls="early"), Req("n", prompt=3000)]
    step(s)  # normal work waits: no cap, no forced decode
    assert s._prefill_decode_interval_remaining == 0

    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048, mixed=True)
    decoding(s, 1)
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    step(s)  # the decode rode along in the prefill step
    assert s._prefill_decode_interval_remaining == 0


def test_mixed_chunk_step_that_could_not_mix_forces_a_decode():
    """Audit #8: with --enable-mixed-chunk SGLang still runs a prefill-only step when it
    cannot mix (here a decoder asked for logprobs): a decode step is forced after it."""
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048, mixed=True)
    decoding(s, 1)
    s.running_batch.reqs[0].return_logprob = True
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    assert _modes(s) == ["P", "D", "P", "D", "P", "D"]


def test_untagged_prefill_never_forces_decode():
    s = build(SptcConfig(spec_prefill_budget=512), chunk=512)
    decoding(s, 1)
    s.waiting_queue.append(Req("n", prompt=1500))
    modes = []
    for _ in range(3):
        b = step(s)
        modes.append("P" if b is not None and b.forward_mode.is_extend() else "D")
    assert modes == ["P", "P", "P"]


def _modes(s, n=6):
    modes = []
    for _ in range(n):
        b = step(s)
        modes.append("P" if b is not None and b.forward_mode.is_extend() else "D")
    return modes


def test_allowance_off_mode():
    s = build(SptcConfig(prefill_allowance="off"))
    assert s._sptc.allowance.unlimited and not s._sptc.alternate
    decoding(s, 1)
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    b = step(s)
    assert {r.rid: r.extend_end for r in b.reqs} == {"e": 1500}
    assert s._prefill_decode_interval_remaining == 0


def test_adaptive_without_an_untagged_decoder_does_not_cap():
    s = build(SptcConfig(spec_prefill_budget=512, prefill_allowance="adaptive"), chunk=2048)
    s.waiting_queue += [Req("e1", prompt=400, cls="early"), Req("e2", prompt=400, cls="early")]
    b = step(s)  # nothing decoding: nothing to protect
    assert {r.rid: r.extend_end for r in b.reqs} == {"e1": 400, "e2": 400}
    assert not s._sptc.tagged_prefill and s._prefill_decode_interval_remaining == 0


def _early_decoder(s):
    d = Req("d_early", cls="early")
    d.prefix_len = d.extend_end = d.n
    s.running_batch.reqs.append(d)


def test_adaptive_early_decoder_does_not_protect_against_early_prefill():
    s = build(SptcConfig(spec_prefill_budget=512, prefill_allowance="adaptive"), chunk=2048)
    _early_decoder(s)
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    assert _modes(s, 2) == ["P", "D"]  # one uncapped prefill step, then decodes
    assert s.chunked_req is None and s.running_batch.reqs[-1].extend_end == 1500


def test_adaptive_early_decoder_protects_against_bet_prefill():
    s = build(SptcConfig(spec_prefill_budget=512, prefill_allowance="adaptive"), chunk=2048)
    _early_decoder(s)
    s.waiting_queue.append(Req("b", prompt=1500, cls="bet"))
    assert _modes(s) == ["P", "D", "P", "D", "P", "D"]  # capped, decodes forced between


def test_adaptive_mixed_pass_limits_only_the_bet():
    # only early work decodes: the early prefill runs uncapped, the bet behind it is capped
    s = build(SptcConfig(spec_prefill_budget=512, prefill_allowance="adaptive"), chunk=4096)
    _early_decoder(s)
    s.waiting_queue += [Req("e", prompt=1500, cls="early"), Req("b", prompt=1500, cls="bet")]
    b = step(s)
    assert {r.rid: r.extend_end for r in b.reqs} == {"e": 1500, "b": 512}
    assert s.chunked_req.rid == "b" and s._prefill_decode_interval_remaining == 1


def test_adaptive_with_an_untagged_decoder_is_fixed():
    for mode in ("fixed", "adaptive"):
        s = build(SptcConfig(spec_prefill_budget=512, prefill_allowance=mode), chunk=2048)
        decoding(s, 1)
        s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
        assert _modes(s) == ["P", "D", "P", "D", "P", "D"], mode


def test_adaptive_finished_untagged_decoder_is_not_protected():
    s = build(SptcConfig(spec_prefill_budget=512, prefill_allowance="adaptive"), chunk=2048)
    decoding(s, 1)
    s.running_batch.reqs[0].done = True  # finished, not yet filtered out of the batch
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    b = step(s)
    assert {r.rid: r.extend_end for r in b.reqs} == {"e": 1500}


# --------------------------------------------------------------------------- dropping
def test_retraction_order_puts_bets_last_stably():
    reqs = [Req("n0"), Req("b0", cls="bet"), Req("e0", cls="early"), Req("b1", cls="bet"), Req("n1")]
    order = core.retraction_order(lambda rs: [4, 3, 2, 1, 0], reqs)
    assert [reqs[i].rid for i in order] == ["n1", "e0", "n0", "b1", "b0"]
    assert core.retraction_order(lambda rs: [0, 4, 2], reqs) == [0, 4, 2]


def test_retracted_bet_dropped_others_requeued():
    s = build()
    s._add_request_to_queue(Req("b", cls="bet"), is_retracted=True)
    s._add_request_to_queue(Req("e", cls="early"), is_retracted=True)
    s._add_request_to_queue(Req("b_new", cls="bet"))  # a new bet is queued normally
    assert s.requeued == [("e", True), ("b_new", False)]
    assert s.aborted == [("b", core.abort_reason("sptc_bet_dropped", "kv_pressure"))]
    assert s.released == ["b"] and s._sptc.counts["dropped"] == 1


def test_invalid_bet_left_to_sglang():
    """Audit #23: a bet SGLang already failed (to_finish set) is neither gated nor rejected."""
    s = build(chunk=200)
    bad = Req("bad", prompt=1, cls="bet")
    bad.to_finish = {"type": "abort", "status_code": 400}
    s.waiting_queue += [Req("n1", 150), Req("n2", 150), Req("n3", 100), bad]
    step(s)
    assert not s.aborted and bad in s.waiting_queue
    s2 = build(SptcConfig(free_window=0))
    bad2 = Req("bad", prompt=1, cls="bet")
    bad2.to_finish = {"type": "abort", "status_code": 400}
    s2.waiting_queue.append(bad2)
    assert [r.rid for r in step(s2).reqs] == ["bad"] and not s2.aborted


def test_bet_requeued_by_pause_retract_is_dropped():
    """pause_generation(mode="retract") requeues without is_retracted; Req.reset_for_retract
    has set req.is_retracted (audit #37)."""
    s = build()
    b, n = Req("b", cls="bet"), Req("n")
    b.is_retracted = n.is_retracted = True
    s._add_request_to_queue(b)
    s._add_request_to_queue(n)
    assert s.requeued == [("n", False)] and reasons(s) == {"b": "retracted"}


def test_chunked_bet_dropped_before_a_decode_step_that_would_retract():
    """Audit #7: a chunked bet is not in the decode batch, so SGLang would retract a
    decoding request instead. It is dropped first, through SGLang's chunked-request abort."""
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    decoding(s, 2)
    s.waiting_queue.append(Req("b", prompt=1500, cls="bet"))
    step(s)
    assert s.chunked_req.rid == "b"
    step(s)  # forced decode step, KV fine: nothing happens
    assert s.chunked_req.rid == "b" and not s.aborted
    step(s)  # next chunk
    s.running_batch.decode_mem_ok = False
    b = step(s)  # decode step that would retract
    assert [r.rid for r in b.reqs] == ["d0", "d1"]
    assert s.chunked_req is None and s.released == ["b"] and s._sptc.counts["dropped"] == 1
    assert reasons(s) == {"b": "kv_pressure"}
    assert s.aborted[0][1]["matched"] == "sptc_bet_dropped"


def test_chunked_bet_kept_when_sglang_would_not_retract():
    """SGLang skips the decode step without retracting when a request finishes on its
    in-flight token (overlap): no retraction, so the chunked bet is kept."""
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    decoding(s, 2)
    s.waiting_queue.append(Req("b", prompt=1500, cls="bet"))
    step(s)
    s.running_batch.decode_mem_ok = False
    s.finishing = [s.running_batch.reqs[0]]
    step(s)
    assert s.chunked_req.rid == "b" and not s.aborted


def test_chunked_early_request_retracted_not_dropped():
    """A chunked early request is never dropped. In a decode step the plugin forced that
    would retract, it is retracted itself (KV freed, requeued), as SGLang would retract it
    first if it were decoding (no output yet)."""
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    decoding(s, 1)
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    step(s)
    s.running_batch.decode_mem_ok = False
    b = step(s)  # the forced decode step
    assert [r.rid for r in b.reqs] == ["d0"]
    assert s.chunked_req is None and s.retracted == ["e"] and s.requeued == [("e", True)]
    assert [r.rid for r in s.waiting_queue] == ["e"] and not s.aborted


def test_chunked_early_request_kept_in_sglangs_own_decode_step():
    """A decode step that SGLang deferred the prefill for (prefill_decode_interval), not the
    plugin, is stock behaviour: the chunked early request is left alone."""
    s = build(SptcConfig(prefill_allowance="off"), chunk=2048)
    decoding(s, 1)
    s.waiting_queue.append(Req("e", prompt=3000, cls="early"))
    step(s)
    s._prefill_decode_interval_remaining = 1
    s.running_batch.decode_mem_ok = False
    step(s)
    assert s.chunked_req.rid == "e" and not s.retracted


def test_chunked_early_request_kept_while_a_bet_decodes():
    """With a bet decoding, SGLang's retraction (bets first) frees KV from the bet: the
    chunked early request keeps its KV."""
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048)
    decoding(s, 1)
    decoding(s, 1, prefix="b")
    s.running_batch.reqs[-1].sampling_params.custom_params = {"sptc_class": "bet"}
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    step(s)
    s.running_batch.decode_mem_ok = False
    step(s)
    assert s.chunked_req.rid == "e" and not s.retracted


def test_rejected_bets_released_and_removed_from_queue():
    s = build(SptcConfig(free_window=0))
    s.waiting_queue += [Req("b", cls="bet"), Req("n")]
    step(s)
    assert s.released == ["b"] and s.waiting_queue == []
    assert s.aborted[0][1]["matched"] == "sptc_bet_rejected"


def test_late_bet_gated_with_current_kv():
    """A bet that joins during the pass (grammar compiled) sees this step's KV usage."""
    s = build(SptcConfig(kv_reserve=0.2), chunk=16_384)
    s.kv_used = 75_000  # below the threshold at step start (audit #31)
    s.waiting_queue.append(Req("n", prompt=10_000))
    s.waiting_queue[0].max_new = 0
    s.late_arrivals = [Req("b", cls="bet")]
    b = step(s)
    assert [r.rid for r in b.reqs] == ["n"]
    assert reasons(s) == {"b": "kv_reserve"}  # 0.75 + n's 0.10 crosses 0.80


# --------------------------------------------------------------------------- end of step
def test_finished_requests_left_in_the_running_batch_do_not_count():
    """Audit #28: SGLang filters finished requests out of the running batch only at the
    next update, so the gate must skip them, in the pass and after it."""
    s = build(SptcConfig(free_window=2))
    decoding(s, 2)
    s.running_batch.reqs[0].done = True
    s.waiting_queue.append(Req("b", cls="bet"))
    assert [r.rid for r in step(s).reqs] == ["b"]  # 1 live + the bet = 2

    s = build(SptcConfig(free_window=3), chunk=200)
    decoding(s, 2)
    s.running_batch.reqs[0].done = True
    s.waiting_queue += [Req("n", prompt=500), Req("b", cls="bet")]  # n chunked: loop stops
    step(s)
    assert s._sptc.held == {"b": 1} and not s.aborted  # 1 live + n + the bet = 3


def test_end_step_counts_this_steps_admissions():
    """Audit #42 (M4): requests SGLang admitted in this step are running at the end."""
    s = build(SptcConfig(free_window=3), chunk=200)
    decoding(s, 1)
    s.waiting_queue += [Req("n1", prompt=50), Req("n2", prompt=500), Req("b", cls="bet")]
    step(s)  # n1 whole, n2 chunked: the loop stops before the bet
    assert reasons(s) == {"b": "free_window"}  # 1 + n1 + n2 + the bet = 4 > 3


def test_end_step_sees_this_steps_kv():
    """Audit #42 (M3): the end-of-step gate reads KV after this step's allocations."""
    s = build(SptcConfig(kv_reserve=0.2), chunk=12_000)
    s.kv_used = 75_000
    s.waiting_queue += [Req("n1", prompt=10_000), Req("n2", prompt=5_000), Req("b", cls="bet")]
    s.waiting_queue[0].max_new = 0
    step(s)  # n2 chunked at 2000: the loop stops before the bet
    assert reasons(s) == {"b": "kv_reserve"}  # 0.75 at the start, 0.87 at the end


def test_held_count_forgotten_once_the_bet_is_admitted():
    """Audit #42 (M2): a held bet that is admitted later leaves `held`, also while another
    bet is still held."""
    s = build(SptcConfig(spec_prefill_budget=64, bet_hold_steps=4), chunk=4096, kv_cap=10_000)
    s.waiting_queue += [Req("e", prompt=100, cls="early"), Req("b1", prompt=20, cls="bet"),
                        Req("b2", prompt=9_950, cls="bet")]
    step(s)  # e takes the allowance; both bets pass the gate and are held
    assert s._sptc.held == {"b1": 1, "b2": 1}
    step(s)  # e's last 36 tokens, b1 fits the rest, b2 does not fit SGLang's KV budget
    assert s._sptc.held == {"b2": 2} and s._sptc.counts["admitted"] == 1 and not s.aborted


def test_early_request_out_of_kv_still_stops_the_pass():
    """NO_TOKEN for certain work keeps SGLang's meaning under the allowance: KV is full,
    stop the pass (only a bet's NO_TOKEN is skipped)."""
    s = build(SptcConfig(spec_prefill_budget=512), chunk=2048, kv_cap=10_000)
    decoding(s, 1)
    s.waiting_queue += [Req("e1", prompt=9_990, cls="early"), Req("e2", prompt=10, cls="early")]
    assert step(s) is None or not s.waiting_queue[0].extend_end
    assert [r.rid for r in s.waiting_queue] == ["e1", "e2"] and s.running_batch.batch_is_full


def test_parked_chunked_request():
    """Audit #30: SGLang can park the chunked request (add_chunked_req returns it without
    admitting it; hybrid SWA). A parked tagged chunk closes the limited pass, as one left
    chunked by the cap does, and holds a running slot for the gate, in and after the pass."""
    s = build(SptcConfig(spec_prefill_budget=512, free_window=3), chunk=2048)
    decoding(s, 2)
    s.waiting_queue.append(Req("e", prompt=1500, cls="early"))
    step(s)
    assert s.chunked_req.rid == "e"
    s._prefill_decode_interval_remaining = 0
    s.park_chunk = True
    s.waiting_queue += [Req("e2", prompt=10, cls="early")]
    assert not step(s).forward_mode.is_extend()  # closed: e2 waits, the decoders run
    assert s.chunked_req.rid == "e" and [r.rid for r in s.waiting_queue] == ["e2"]
    s.waiting_queue = [Req("b", cls="bet")]
    step(s)  # end of step: d0 + d1 + parked e + the bet = 4 > 3
    assert reasons(s) == {"b": "free_window"}

    s = build(SptcConfig(free_window=1), chunk=2048)
    s.waiting_queue.append(Req("n", prompt=3000))
    step(s)
    s.park_chunk = True
    s.waiting_queue.append(Req("b", cls="bet"))
    step(s)  # in the pass: parked n + the bet = 2 > 1
    assert reasons(s) == {"b": "free_window"}


def test_hooks_pass_through_before_setup():
    cls = core.make_scheduler_class(
        FakeScheduler, AddReqResult=AddReqResult, finish_abort=finish_abort,
        finish_reason=finish_reason, retract=retract,
        cfg_loader=SptcConfig, checks=lambda s: ([], []),
    )
    s = cls.__new__(cls)
    FakeScheduler.__init__(s)  # base state only, no _sptc yet
    s.waiting_queue.append(Req("b", cls="bet"))
    assert s.get_prefill_adder_class() is FakeAdder
    b = s.get_next_batch_to_run(s.running_batch, None).batch_to_run
    assert [r.rid for r in b.reqs] == ["b"]
    s._add_request_to_queue(Req("b2", cls="bet"), is_retracted=True)
    assert s.requeued == [("b2", True)]



def test_grammar_ready_normal_request_counts_as_waiting():
    """A normal request appended during the pass lands behind the bets;
    the gate must still see it, and the allowance must not apply in that pass."""
    s = build(SptcConfig(spec_prefill_budget=64), chunk=2048)
    s.waiting_queue += [Req("e", prompt=500, cls="early"), Req("b", cls="bet")]
    s.late_arrivals = [Req("n_late", prompt=100)]
    b = step(s)
    assert {r.rid: r.extend_end for r in b.reqs} == {"e": 500, "n_late": 100}  # no cap
    assert reasons(s) == {"b": "nonbet_waiting"}


def test_dropped_and_rejected_bets_finish_through_the_output_path():
    s = build(SptcConfig(free_window=0))
    s.waiting_queue.append(Req("b", cls="bet"))
    step(s)
    s._add_request_to_queue(Req("d", cls="bet"), is_retracted=True)
    assert [rid for rid, _ in s.aborted] == ["b", "d"]
    assert s.released == ["b", "d"] and s.retired == ["b", "d"]
