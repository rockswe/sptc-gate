"""sptc scheduler against the real vLLM v0.32.0 Scheduler/AsyncScheduler (modeled on
tests/v1/core/test_scheduler.py). Run on a machine with vLLM installed:

    pip install vllm==0.32.0 pytest
    pytest sptc-sim/integrations/tests_vllm -q -p no:cacheprovider
"""

import pytest

pytest.importorskip("vllm")

from _helpers import (  # noqa: E402
    build,
    client_outs,
    make_sched,
    new_ids,
    req,
    runner_output,
    step,
)
from types import SimpleNamespace  # noqa: E402

from vllm.v1.core.sched.async_scheduler import AsyncScheduler  # noqa: E402
from vllm.v1.core.sched.interface import PauseState  # noqa: E402
from vllm.v1.engine import FinishReason  # noqa: E402
from vllm.v1.request import RequestStatus  # noqa: E402

from sptc_vllm.scheduler import SptcAsyncScheduler, SptcScheduler  # noqa: E402

ASYNC = pytest.mark.parametrize("async_scheduling", [False, True], ids=["sync", "async"])


def sptc_outs(outs):
    return [o for o in client_outs(outs) if str(o.stop_reason or "").startswith("sptc_")]


def assert_rejected(s, r, outs, reason):
    assert r.status == RequestStatus.FINISHED_ABORTED
    assert r.request_id not in s.requests
    assert r not in s.waiting and r not in s.kv_holding_waiting and r not in s.deferred_waiting
    assert s.sptc_counters["bet_rejected:" + reason] == 1, dict(s.sptc_counters)
    (o,) = client_outs(outs, r.request_id)
    assert o.finish_reason == FinishReason.ABORT
    assert o.stop_reason == "sptc_bet_rejected"
    assert o.new_token_ids == []


# =============================================================================== gate
@ASYNC
def test_idle_bet_admitted_and_finishes_normally(async_scheduling):
    s = make_sched(async_scheduling=async_scheduling)
    bet = req("bet", 10, "bet", max_tokens=3)
    s.add_request(bet)
    finals = []
    for _ in range(10):
        out = s.schedule()
        finals += [o for o in client_outs(step(s, out), "bet") if o.finish_reason is not None]
        if bet.is_finished():
            break
    (final,) = finals
    assert final.finish_reason == FinishReason.LENGTH and final.stop_reason is None
    assert s.sptc_counters["bet_admitted"] == 1
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)
    assert not s._sptc_waiting_bets and not s._sptc_running_bets


@ASYNC
def test_bet_rejected_outside_free_window(async_scheduling):
    s = make_sched({"free_window": 2}, async_scheduling=async_scheduling)
    n0, n1, bet = req("n0", 10), req("n1", 10), req("bet", 10, "bet")
    for r in (n0, n1, bet):
        s.add_request(r)
    out = s.schedule()
    assert set(out.num_scheduled_tokens) == {"n0", "n1"}
    assert len(s.waiting) == 0
    assert_rejected(s, bet, step(s, out), "free_window")


def test_second_bet_rejected_when_first_fills_window():
    s = make_sched({"free_window": 1})
    b1, b2 = req("b1", 10, "bet"), req("b2", 10, "bet")
    s.add_request(b1)
    s.add_request(b2)
    out = s.schedule()
    assert list(out.num_scheduled_tokens) == ["b1"]
    assert_rejected(s, b2, step(s, out), "free_window")
    assert s.sptc_counters["bet_admitted"] == 1


@ASYNC
@pytest.mark.parametrize("prompt,admitted", [(300, False), (270, True)])
def test_bet_kv_reserve(async_scheduling, prompt, admitted):
    # 21 blocks = 20 usable (block 0 is the null block). 300 tokens -> 19 blocks (0.95 used),
    # 270 tokens -> 17 blocks (0.85 used); default reserve 0.10.
    s = make_sched(num_blocks=21, async_scheduling=async_scheduling)
    s.add_request(req("norm", prompt, max_tokens=8))
    step(s, s.schedule())
    bet = req("bet", 16, "bet")
    s.add_request(bet)
    out = s.schedule()
    outs = step(s, out)
    if admitted:
        assert "bet" in out.num_scheduled_tokens and bet.status == RequestStatus.RUNNING
    else:
        assert "bet" not in out.num_scheduled_tokens
        assert_rejected(s, bet, outs, "kv_reserve")


def test_bet_rejected_when_nonbet_waiting_not_reached():
    s = make_sched(max_num_seqs=2)
    s.add_request(req("n0", 10))
    s.add_request(req("n1", 10))
    step(s, s.schedule())
    n2, bet = req("n2", 10), req("bet", 10, "bet")
    s.add_request(n2)
    s.add_request(bet)
    out = s.schedule()  # waiting loop breaks at max_num_active_reqs before reaching anyone
    assert set(out.num_scheduled_tokens) == {"n0", "n1"}
    assert n2.status == RequestStatus.WAITING and n2 in s.waiting
    # never visited: gated at the end of the step, n2 is still waiting
    assert_rejected(s, bet, step(s, out), "nonbet_waiting")


def test_bet_rejected_when_nonbet_skipped_by_hook_path():
    s = make_sched()
    g = req("g", 10)
    g.status = RequestStatus.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR  # never compiles: skipped
    s.add_request(g)
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    out = s.schedule()
    assert "bet" not in out.num_scheduled_tokens
    assert_rejected(s, bet, step(s, out), "nonbet_waiting")
    assert s.finish_requests("g", RequestStatus.FINISHED_ABORTED)


@ASYNC
def test_bets_ordered_behind_later_normal(async_scheduling):
    s = make_sched(async_scheduling=async_scheduling)
    s.add_request(req("bet", 10, "bet"))
    s.add_request(req("norm", 10))
    out = s.schedule()
    assert new_ids(out) == ["norm", "bet"]


def test_bet_held_when_only_the_token_budget_ran_out():
    s = make_sched(max_num_batched_tokens=64)
    s.add_request(req("norm", 64))
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"norm": 64}
    # spare capacity by the gate's definition (nothing waiting, window, KV): kept waiting
    assert bet.status == RequestStatus.WAITING and s._sptc_held == {"bet": 1}
    assert not sptc_outs(step(s, out))
    out = s.schedule()
    assert out.num_scheduled_tokens == {"norm": 1, "bet": 10}
    assert s.sptc_counters["bet_admitted"] == 1 and not s._sptc_held
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)


@ASYNC
def test_bet_held_while_running_prefill_fills_the_budget(async_scheduling):
    # norm's 200-token prompt is chunked 64 per step by its running-loop chunk: the waiting
    # loop is not entered for 3 steps. The bet arriving meanwhile survives and is admitted.
    s = make_sched(max_num_batched_tokens=64, async_scheduling=async_scheduling)
    s.add_request(req("norm", 200))
    step(s, s.schedule())
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    seen = []
    for _ in range(4):
        out = s.schedule()
        seen.append(dict(out.num_scheduled_tokens))
        assert not sptc_outs(step(s, out))
        if "bet" in out.num_scheduled_tokens:
            break
    assert seen == [{"norm": 64}, {"norm": 64}, {"norm": 8, "bet": 10}], seen
    assert bet.status == RequestStatus.RUNNING
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)


def test_bet_rejected_after_bet_hold_steps():
    s = make_sched({"bet_hold_steps": 2}, max_num_batched_tokens=64)
    s.add_request(req("norm", 400))
    step(s, s.schedule())
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    step(s, s.schedule())
    step(s, s.schedule())
    assert s._sptc_held == {"bet": 2}
    out = s.schedule()
    assert_rejected(s, bet, step(s, out), "held_too_long")


def test_bet_hold_steps_zero_rejects_at_once():
    s = make_sched({"bet_hold_steps": 0}, max_num_batched_tokens=64)
    s.add_request(req("norm", 64))
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    assert_rejected(s, bet, step(s, s.schedule()), "held_too_long")


def test_bet_held_through_transient_vllm_skip():
    # e.g. an encoder prefetch still in flight (or a KV connector that cannot answer yet):
    # vLLM skips the request for this step only. The bet passed the gate: it must survive.
    # The step scheduled no tokens (an idle engine iteration), so it is not counted.
    s = make_sched({"bet_hold_steps": 0})
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    pending = {"bet"}
    s._ec_transfer_pending = lambda r, n: r.request_id in pending
    out = s.schedule()
    assert out.total_num_scheduled_tokens == 0
    assert "bet" not in out.num_scheduled_tokens and bet in s.deferred_waiting
    assert bet.status == RequestStatus.WAITING and not s._sptc_held
    step(s, out)
    pending.clear()
    out = s.schedule()
    assert "bet" in out.num_scheduled_tokens and bet.status == RequestStatus.RUNNING


def test_bet_held_on_dp_throttled_step_without_counting():
    s = make_sched({"bet_hold_steps": 0})
    s.add_request(req("n0", 10, max_tokens=50))
    step(s, s.schedule())
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    out = s.schedule(throttle_prefills=True)  # DP non-cadence step: prefills deferred
    assert out.num_scheduled_tokens == {"n0": 1}
    assert bet.status == RequestStatus.WAITING and not s._sptc_held  # not counted
    step(s, out)
    out = s.schedule()
    assert "bet" in out.num_scheduled_tokens and bet.status == RequestStatus.RUNNING


def test_unreached_rejected_bet_not_counted_in_dp_capacity_signal():
    s = make_sched({"free_window": 2}, max_num_seqs=2)
    s.add_request(req("n0", 10, max_tokens=50))
    s.add_request(req("n1", 10, max_tokens=50))
    step(s, s.schedule())
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    out = s.schedule()  # loop breaks at max_num_seqs; the bet then fails the window
    assert_rejected(s, bet, step(s, out), "free_window")
    assert s.prefill_capacity_bound is False  # as if the bet had never arrived


def test_bet_rejected_while_paused():
    s = make_sched()
    s.set_pause_state(PauseState.PAUSED_NEW)
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    assert_rejected(s, bet, step(s, s.schedule()), "paused")


def test_early_waiting_on_allowance_counts_as_nonbet_waiting():
    s = make_sched()
    e0, e1 = req("e0", 2000, "early"), req("e1", 2000, "early")
    s.add_request(e0)
    s.add_request(e1)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"e0": 512}  # e1 waits for the allowance
    step(s, out)
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"e0": 512}
    assert e1.status == RequestStatus.WAITING
    assert_rejected(s, bet, step(s, out), "nonbet_waiting")


def test_blocked_bet_ready_but_unreached_is_gated_like_any_waiting_bet():
    s = make_sched({"bet_hold_steps": 0}, max_num_batched_tokens=64)
    s.add_request(req("norm", 64))
    ready, compiling = req("ready", 10, "bet"), req("compiling", 10, "bet")
    for r, grammar in ((ready, object()), (compiling, None)):
        r.status = RequestStatus.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR
        r.structured_output_request = SimpleNamespace(grammar=grammar)
        s.add_request(r)
    out = s.schedule()  # norm takes the whole budget: neither bet is visited
    assert out.num_scheduled_tokens == {"norm": 64}
    outs = step(s, out)
    # grammar ready: would be promoted on its next visit, so it is a waiting bet
    assert ready.status == RequestStatus.FINISHED_ABORTED
    assert s.sptc_counters["bet_rejected:held_too_long"] == 1
    assert [o.stop_reason for o in client_outs(outs, "ready")] == ["sptc_bet_rejected"]
    # still compiling: kept (not counted) until it is unblocked
    assert compiling.status == RequestStatus.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR
    assert "compiling" in s._sptc_waiting_bets and not s._sptc_held
    s.finish_requests("compiling", RequestStatus.FINISHED_ABORTED)


def test_nonbet_cache_not_poisoned_by_kv_holding_bet():
    # kv_holding_waiting is drained before `waiting`: a bet there is gated while the
    # non-bets in `waiting` are still unvisited. That verdict must not be cached.
    s = make_sched()
    kvb, norm, b = req("kvb", 32, "bet"), req("norm", 10), req("b", 10, "bet")
    for r in (kvb, norm, b):
        s.add_request(r)
    s.waiting.remove_requests([kvb])
    s.kv_holding_waiting.add_request(kvb)  # as after a finished async KV load
    s._sptc_begin_step(False)
    assert s._handle_blocked_waiting_request(kvb) is False
    assert s._sptc_reject == {"kvb": "nonbet_waiting"} and s._sptc_nonbet_waiting is None
    s.kv_holding_waiting.remove_requests([kvb])  # skipped
    s.waiting.remove_requests([norm])  # admitted
    assert s._handle_blocked_waiting_request(b) is True  # nothing non-bet is waiting now


# =============================================================================== drop
SMALL = dict(max_num_seqs=2, max_num_batched_tokens=200, num_blocks=5, block_size=16)


def test_newest_bet_dropped_first_and_normal_untouched():
    # b1, b2: 14-token bets (1 block each); norm: 32 tokens (2 blocks). 4 usable blocks.
    s = make_sched(max_num_seqs=4, max_num_batched_tokens=200, num_blocks=5)
    b1, b2 = req("b1", 14, "bet", max_tokens=50), req("b2", 14, "bet", max_tokens=50)
    s.add_request(b1)
    s.add_request(b2)
    step(s, s.schedule())
    norm = req("norm", 32, max_tokens=50)
    s.add_request(norm)
    out = s.schedule()
    assert set(out.num_scheduled_tokens) == {"b1", "b2", "norm"}
    assert s.kv_cache_manager.block_pool.get_num_free_blocks() == 0
    step(s, out)
    out = s.schedule()  # norm's decode needs a 3rd block: the newest bet goes
    assert set(out.num_scheduled_tokens) == {"norm", "b1"}
    assert b2.status == RequestStatus.FINISHED_ABORTED and b1.status == RequestStatus.RUNNING
    assert s.sptc_counters["bet_dropped"] == 1
    step(s, out)
    out = s.schedule()  # b1's decode needs a 2nd block: b1 goes, norm keeps running
    assert set(out.num_scheduled_tokens) == {"norm"}
    assert b1.status == RequestStatus.FINISHED_ABORTED
    assert s.sptc_counters["bet_dropped"] == 2
    assert norm.status == RequestStatus.RUNNING and norm.num_preemptions == 0
    assert not out.preempted_req_ids


def _fill(s):
    """bet (30 tokens, 2 blocks) runs, then norm (32 tokens, 2 blocks) takes the last free
    blocks. Next decode of norm needs a third block."""
    bet = req("bet", 30, "bet", max_tokens=50)
    s.add_request(bet)
    step(s, s.schedule())
    norm = req("norm", 32, max_tokens=50)
    s.add_request(norm)
    out = s.schedule()
    assert set(out.num_scheduled_tokens) == {"bet", "norm"}
    assert s.kv_cache_manager.block_pool.get_num_free_blocks() == 0
    return bet, norm, out


def test_preemption_drops_running_bet():
    s = make_sched(**SMALL)
    bet, norm, out = _fill(s)
    step(s, out)
    out = s.schedule()
    assert list(out.num_scheduled_tokens) == ["norm"]
    assert bet.status == RequestStatus.FINISHED_ABORTED
    assert bet not in s.waiting and "bet" not in s.requests and bet not in s.running
    assert "bet" in out.finished_req_ids and "bet" not in out.preempted_req_ids
    assert s.sptc_counters["bet_dropped"] == 1
    (o,) = client_outs(step(s, out), "bet")
    assert o.finish_reason == FinishReason.ABORT and o.stop_reason == "sptc_bet_dropped"
    assert norm.status == RequestStatus.RUNNING


def test_vanilla_control_preempts_the_normal_request():
    s = build(**SMALL)  # stock Scheduler, same steps
    bet, norm, out = _fill(s)
    step(s, out)
    out = s.schedule()
    assert list(out.num_scheduled_tokens) == ["bet"]
    assert norm.status == RequestStatus.PREEMPTED


def test_async_drop_with_inflight_output():
    s = make_sched(async_scheduling=True, **SMALL)
    assert isinstance(s, SptcAsyncScheduler)
    bet = req("bet", 30, "bet", max_tokens=50)
    s.add_request(bet)
    step(s, s.schedule())
    s.add_request(req("norm", 32, max_tokens=50))
    out1 = s.schedule()  # bet decode + norm prefill, in flight
    assert set(out1.num_scheduled_tokens) == {"bet", "norm"}
    out2 = s.schedule()  # norm's next decode needs a block: the in-flight bet is dropped
    assert list(out2.num_scheduled_tokens) == ["norm"]
    assert "bet" in out2.finished_req_ids
    outs1 = s.update_from_output(out1, runner_output(s, out1))  # includes a token for bet
    outs2 = s.update_from_output(out2, runner_output(s, out2))
    got = client_outs(outs1, "bet") + client_outs(outs2, "bet")
    assert len(got) == 1, got
    (o,) = got
    assert o.finish_reason == FinishReason.ABORT and o.stop_reason == "sptc_bet_dropped"
    assert o.new_token_ids == []


def test_async_bet_finishing_in_flight_is_requeued_not_dropped():
    # bet max_tokens=2: its decode in flight in out2 is its last token. When norm needs a
    # block in out3, the bet is the victim (before norm), but through vLLM's requeue: the
    # in-flight token is delivered and the bet finishes normally.
    s = make_sched(async_scheduling=True, **SMALL)
    bet = req("bet", 30, "bet", max_tokens=2)
    s.add_request(bet)
    step(s, s.schedule())
    norm = req("norm", 32, max_tokens=50)
    s.add_request(norm)
    out2 = s.schedule()
    assert set(out2.num_scheduled_tokens) == {"bet", "norm"}
    ro2 = runner_output(s, out2)
    out3 = s.schedule()
    assert out3.num_scheduled_tokens == {"norm": 1}
    assert bet.status == RequestStatus.PREEMPTED and "bet" in out3.preempted_req_ids
    assert s.sptc_counters["bet_requeued_finishing"] == 1 and "bet_dropped" not in s.sptc_counters
    outs = s.update_from_output(out2, ro2)
    (o,) = client_outs(outs, "bet")
    assert o.finish_reason == FinishReason.LENGTH and o.stop_reason is None
    assert o.new_token_ids == [7]
    assert bet.is_finished() and bet not in s.waiting
    assert not sptc_outs(s.update_from_output(out3, runner_output(s, out3)))
    assert norm.status == RequestStatus.RUNNING
    s.schedule()
    assert not s._sptc_waiting_bets and not s._sptc_running_bets


@ASYNC
def test_vanilla_preemption_without_bets(async_scheduling):
    s = make_sched(async_scheduling=async_scheduling, **SMALL)
    a = req("a", 30, max_tokens=50)
    s.add_request(a)
    step(s, s.schedule())
    b = req("b", 32, max_tokens=50)
    s.add_request(b)
    step(s, s.schedule())
    out = s.schedule()
    assert list(out.num_scheduled_tokens) == ["a"]
    assert b.status == RequestStatus.PREEMPTED and b in s.waiting
    assert not sptc_outs(step(s, out)) and not s.sptc_counters


def test_reset_prefix_cache_requeues_bet():
    s = make_sched()
    bet = req("bet", 20, "bet", max_tokens=20)
    s.add_request(bet)
    step(s, s.schedule())
    assert s.reset_prefix_cache(reset_running_requests=True)
    assert bet.status == RequestStatus.PREEMPTED and bet in s.waiting
    out = s.schedule()  # re-gated on an idle server: resumed
    assert "bet" in out.num_scheduled_tokens and bet.status == RequestStatus.RUNNING
    assert s.sptc_counters["bet_admitted"] == 1 and s.sptc_counters["bet_readmitted"] == 1
    assert "bet_dropped" not in s.sptc_counters
    assert not sptc_outs(step(s, out))


# ========================================================================== allowance
@ASYNC
def test_spec_prefill_budget_shared_per_step(async_scheduling):
    s = make_sched(async_scheduling=async_scheduling)
    e2 = req("e2", 2000, "early")
    for r in (req("norm", 2000), req("e1", 2000, "early"), e2):
        s.add_request(r)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"norm": 2000, "e1": 512}
    assert e2.status == RequestStatus.WAITING
    step(s, out)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"norm": 1, "e1": 512}


def test_allowance_does_not_block_normal_behind_early():
    s = make_sched()
    for r in (req("e1", 2000, "early"), req("e2", 2000, "early"), req("norm", 2000)):
        s.add_request(r)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"e1": 512, "norm": 2000}


@ASYNC
def test_decode_not_charged(async_scheduling):
    s = make_sched(async_scheduling=async_scheduling)
    s.add_request(req("e_short", 10, "early"))
    step(s, s.schedule())
    out = s.schedule()
    assert out.num_scheduled_tokens == {"e_short": 1}
    if not async_scheduling:
        step(s, out)  # async: leave it in flight, so the next decode has placeholders
    s.add_request(req("e_long", 2000, "early"))
    out = s.schedule()
    assert out.num_scheduled_tokens == {"e_short": 1, "e_long": 512}


def test_spec_prefill_budget_knob_applies():
    s = make_sched({"spec_prefill_budget": 64})
    s.add_request(req("e1", 2000, "early"))
    s.add_request(req("norm", 300))
    assert s.schedule().num_scheduled_tokens == {"e1": 64, "norm": 300}


def test_kv_reserve_knob_applies():
    # same KV state as test_bet_kv_reserve's admitted case (0.85 used), reserve 0.3
    s = make_sched({"kv_reserve": 0.3}, num_blocks=21)
    s.add_request(req("norm", 270, max_tokens=8))
    step(s, s.schedule())
    bet = req("bet", 16, "bet")
    s.add_request(bet)
    out = s.schedule()
    assert "bet" not in out.num_scheduled_tokens
    assert_rejected(s, bet, step(s, out), "kv_reserve")


def test_allowance_short_of_mtp_lookahead_skips_instead_of_breaking():
    # Multi-module MTP lookahead 4. e1 leaves 2 of the 6-token allowance; capping e2 to 2
    # would be cut to 0 by vLLM's lookahead rule, and 0 means `break` in the waiting loop.
    s = make_sched({"spec_prefill_budget": 6})
    s.num_prefill_lookahead = 4
    e2 = req("e2", 4, "early")
    for r in (req("e1", 4, "early"), e2, req("norm", 10)):
        s.add_request(r)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"e1": 4, "norm": 10}
    assert e2.status == RequestStatus.WAITING


def test_bet_deferred_by_allowance_stays_waiting_then_admitted():
    s = make_sched()
    e1, bet = req("e1", 2000, "early"), req("bet", 600, "bet")
    s.add_request(e1)
    s.add_request(bet)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"e1": 512}
    assert bet.status == RequestStatus.WAITING and s._sptc_held == {"bet": 1}
    seen = []
    for _ in range(6):
        step(s, out)
        out = s.schedule()
        seen.append(dict(out.num_scheduled_tokens))
        if "bet" in out.num_scheduled_tokens:
            break
    # e1: 512 x 3, then its last 464; the 48 tokens left go to the bet in the same step
    assert seen[-1] == {"e1": 464, "bet": 48}, seen
    assert bet.status == RequestStatus.RUNNING
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)


def test_bet_deferred_by_allowance_rejected_once_window_fills():
    s = make_sched({"free_window": 2})
    e1, bet = req("e1", 2000, "early"), req("bet", 600, "bet")
    s.add_request(e1)
    s.add_request(bet)
    out = s.schedule()
    assert s._sptc_held == {"bet": 1}
    step(s, out)
    s.add_request(req("n0", 10))
    s.add_request(req("n1", 10))
    out = s.schedule()
    assert set(out.num_scheduled_tokens) == {"e1", "n0", "n1"}
    assert_rejected(s, bet, step(s, out), "free_window")


def test_unlimited_budget_with_zero():
    s = make_sched({"spec_prefill_budget": 0})
    for r in (req("e1", 2000, "early"), req("e2", 2000, "early")):
        s.add_request(r)
    assert s.schedule().num_scheduled_tokens == {"e1": 2000, "e2": 2000}


# ============================================================ allowance: adaptive / off
def test_allowance_off_mode_does_not_cap():
    s = make_sched({"prefill_allowance": "off"})
    assert s._sptc_allow.unlimited
    for r in (req("e1", 2000, "early"), req("e2", 2000, "early")):
        s.add_request(r)
    assert s.schedule().num_scheduled_tokens == {"e1": 2000, "e2": 2000}


@ASYNC
def test_adaptive_does_not_cap_without_an_untagged_decoder(async_scheduling):
    s = make_sched({"prefill_allowance": "adaptive"}, async_scheduling=async_scheduling)
    for r in (req("e1", 2000, "early"), req("b", 2000, "bet")):
        s.add_request(r)
    out = s.schedule()  # nothing decoding: nothing to protect
    assert out.num_scheduled_tokens == {"e1": 2000, "b": 2000}


@ASYNC
def test_adaptive_caps_while_an_untagged_request_decodes(async_scheduling):
    s = make_sched({"prefill_allowance": "adaptive"}, async_scheduling=async_scheduling)
    s.add_request(req("norm", 10, max_tokens=50))
    out = s.schedule()
    if not async_scheduling:
        step(s, out)  # async: leave its first token in flight (placeholders)
    for r in (req("e1", 2000, "early"), req("e2", 2000, "early")):
        s.add_request(r)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"norm": 1, "e1": 512}


@ASYNC
@pytest.mark.parametrize("cls,chunk", [("early", 2000), ("bet", 512)])
def test_adaptive_early_decoder_protects_only_against_bets(async_scheduling, cls, chunk):
    # an early request decoding is certain work: a bet's prefill yields to it, another
    # early request's prefill does not
    s = make_sched({"prefill_allowance": "adaptive"}, async_scheduling=async_scheduling)
    s.add_request(req("e_short", 10, "early", max_tokens=50))
    out = s.schedule()
    if not async_scheduling:
        step(s, out)
    s.add_request(req("x", 2000, cls))
    out = s.schedule()
    assert out.num_scheduled_tokens == {"e_short": 1, "x": chunk}


@pytest.mark.parametrize("mode,early_chunk", [("fixed", 512), ("adaptive", 548)])
def test_adaptive_untagged_prefill_is_not_protected(mode, early_chunk):
    # norm is still prefilling (chunked at the 1024-token step budget) when e arrives:
    # nothing decodes, so adaptive lets e use what is left of the step budget
    s = make_sched({"prefill_allowance": mode}, max_num_batched_tokens=1024)
    s.add_request(req("norm", 1500))
    out = s.schedule()
    assert out.num_scheduled_tokens == {"norm": 1024}
    step(s, out)
    s.add_request(req("e", 2000, "early"))
    out = s.schedule()
    assert out.num_scheduled_tokens == {"norm": 476, "e": early_chunk}


def test_adaptive_decided_once_per_step():
    # the first tagged prefill decides for the whole step; the next step decides again
    s = make_sched({"prefill_allowance": "adaptive", "spec_prefill_budget": 100})
    calls = []
    orig = s._sptc_decoders

    def spy():
        calls.append(1)
        return orig()

    s._sptc_decoders = spy
    s.add_request(req("n", 10, max_tokens=50))
    out = s.schedule()
    assert not calls  # untagged-only step: never asked
    step(s, out)
    for r in (req("e1", 300, "early"), req("e2", 300, "early")):
        s.add_request(r)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"n": 1, "e1": 100} and len(calls) == 1
    step(s, out)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"n": 1, "e1": 100} and len(calls) == 2


# ================================================================ lifecycle / config
@ASYNC
def test_client_abort_of_bet_emits_nothing(async_scheduling):
    s = make_sched(async_scheduling=async_scheduling)
    s.add_request(req("bet_w", 10, "bet"))
    s.finish_requests("bet_w", RequestStatus.FINISHED_ABORTED)  # aborted while waiting
    s.add_request(req("bet_r", 10, "bet", max_tokens=50))
    outs = [step(s, s.schedule())]
    assert "bet_r" in s._sptc_running_bets
    s.finish_requests("bet_r", RequestStatus.FINISHED_ABORTED)  # aborted while running
    s.add_request(req("norm", 10, max_tokens=2))
    for _ in range(4):
        outs.append(step(s, s.schedule()))
    assert not any(sptc_outs(o) for o in outs)
    assert not s._sptc_waiting_bets and not s._sptc_running_bets
    assert not any(k.startswith(("bet_rejected", "bet_dropped")) for k in s.sptc_counters)


def test_config_and_class_selection():
    with pytest.raises(ValueError, match="unknown sptc knob"):
        make_sched({"free_windw": 3})
    with pytest.raises(ValueError, match="fcfs"):
        make_sched(scheduling_policy="priority")
    with pytest.raises(ValueError, match="async scheduling is off"):
        build(SptcAsyncScheduler, sptc={}, async_scheduling=False)
    s = make_sched(async_scheduling=True)
    assert isinstance(s, SptcAsyncScheduler) and isinstance(s, AsyncScheduler)
    s = make_sched(async_scheduling=False)
    assert type(s) is SptcScheduler and not isinstance(s, AsyncScheduler)
    s = make_sched(
        {"free_window": 3, "kv_reserve": 0.2, "spec_prefill_budget": 64, "bet_hold_steps": 4}
    )
    assert (s.sptc_config.free_window, s.sptc_config.kv_reserve) == (3, 0.2)
    assert s.sptc_config.bet_hold_steps == 4
    assert s._sptc_allow.budget == 64 and not s._sptc_allow.adaptive
    assert make_sched(enable_chunked_prefill=False)._sptc_allow.unlimited
    assert make_sched({"prefill_allowance": "adaptive"})._sptc_allow.adaptive
    assert make_sched({"prefill_allowance": "off"})._sptc_allow.unlimited
    with pytest.raises(ValueError, match="prefill_allowance"):
        make_sched({"prefill_allowance": "sometimes"})
    # no additional_config["sptc"] at all: defaults
    assert build(SptcScheduler).sptc_config.free_window == 8


def test_startup_line_reaches_vllm_log_handler():
    # On the T4 run the plugin's INFO lines never reached the server log: a logger outside
    # the "vllm" namespace has no handler under vLLM's logging config.
    import logging

    from vllm.config.logging import LoggingConfig
    from vllm.logger import configure_logging

    from sptc_vllm import scheduler as mod

    # vLLM 0.32 configures logging when a server or engine core starts, not on import, so
    # apply the default config here as the engine-core process does
    configure_logging(LoggingConfig())
    lg = mod.logger
    assert lg.name.startswith("vllm.") and lg.isEnabledFor(logging.INFO)
    up = lg
    while up is not None and not up.handlers and up.propagate:
        up = up.parent
    assert up is not None and up.handlers and up.name == "vllm", (
        "no vLLM handler above the sptc logger: the startup line would be dropped"
    )


# ================================================================ audit follow-up fixes
@ASYNC
def test_running_bet_prefill_leaves_the_allowance_to_waiting_early(async_scheduling):
    # audit #2: a running bet's prefill (running loop) took the whole allowance before the
    # waiting loop, so a waiting early request was skipped for as long as the bet prefilled
    s = make_sched(max_num_batched_tokens=2048, async_scheduling=async_scheduling)
    s.add_request(req("bet", 1800, "bet"))
    out = s.schedule()
    assert out.num_scheduled_tokens == {"bet": 512}
    step(s, out)
    s.add_request(req("early", 300, "early"))
    out = s.schedule()
    assert out.num_scheduled_tokens == {"bet": 212, "early": 300}
    step(s, out)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"bet": 512, "early": 1}


def test_running_bet_keeps_the_allowance_without_waiting_early():
    s = make_sched(max_num_batched_tokens=2048)
    s.add_request(req("bet", 1800, "bet"))
    step(s, s.schedule())
    s.add_request(req("norm", 300))
    assert s.schedule().num_scheduled_tokens == {"bet": 512, "norm": 300}


def test_bet_not_held_at_zero_for_early_work_that_cannot_be_admitted():
    # follow-up to #2: 101 blocks = 100 usable. After two chunks the bet holds 64; the early
    # request needs 38 for its full prompt (scheduler_reserve_full_isl), 36 are free, so
    # the waiting loop breaks on it. The kept share used to cut the bet to 0 on every step
    # and nothing ran again. Now the bet loses one step (not one per early request queued
    # behind the first), then finishes and frees the KV.
    s = make_sched(max_num_batched_tokens=2048, num_blocks=101)
    s.add_request(req("bet", 1500, "bet", max_tokens=50))
    step(s, s.schedule())
    step(s, s.schedule())
    early = req("early", 600, "early", max_tokens=5)
    s.add_request(early)
    s.add_request(req("early2", 600, "early", max_tokens=5))
    out = s.schedule()
    assert out.num_scheduled_tokens == {} and early.status == RequestStatus.WAITING
    step(s, out)
    out = s.schedule()
    assert out.num_scheduled_tokens == {"bet": 476}
    step(s, out)
    assert s.sptc_counters["early_kept_not_admitted"] == 1
    for _ in range(100):
        if not s.has_requests():
            break
        step(s, s.schedule())
    assert not s.has_requests()
    assert early.status == RequestStatus.FINISHED_LENGTH_CAPPED
    assert s.sptc_counters["early_kept_not_admitted"] == 1


def test_no_allowance_kept_for_early_work_while_paused():
    # PAUSED_NEW admits nothing from `waiting`, and the pause drains only when running
    # requests finish: a running bet keeps its whole allowance
    s = make_sched(max_num_batched_tokens=2048)
    s.add_request(req("bet", 1800, "bet"))
    step(s, s.schedule())
    s.add_request(req("early", 600, "early"))
    s.set_pause_state(PauseState.PAUSED_NEW)
    for _ in range(2):
        out = s.schedule()
        assert out.num_scheduled_tokens == {"bet": 512}
        step(s, out)


def test_no_allowance_kept_for_early_work_while_every_slot_is_taken():
    s = make_sched({"free_window": 2}, max_num_batched_tokens=2048, max_num_seqs=2)
    s.add_request(req("norm", 10, max_tokens=100))
    step(s, s.schedule())
    s.add_request(req("bet", 1800, "bet"))
    step(s, s.schedule())
    s.add_request(req("early", 300, "early"))
    assert s.schedule().num_scheduled_tokens == {"norm": 1, "bet": 512}


def test_small_bet_behind_long_bet_prefill_not_held_too_long():
    # audit #10: steps where the allowance went to another bet's prefill are not counted
    s = make_sched({"bet_hold_steps": 1}, max_num_batched_tokens=2048)
    s.add_request(req("b1", 1800, "bet"))
    step(s, s.schedule())
    b2 = req("b2", 64, "bet")
    s.add_request(b2)
    seen = []
    for _ in range(5):
        out = s.schedule()
        seen.append(dict(out.num_scheduled_tokens))
        assert not sptc_outs(step(s, out)), seen
        if "b2" in out.num_scheduled_tokens:
            break
    assert seen == [{"b1": 512}, {"b1": 512}, {"b1": 264, "b2": 64}], seen
    assert b2.status == RequestStatus.RUNNING


def test_bet_with_failed_grammar_is_an_error_not_a_rejection():
    # audit #3: vLLM reports a grammar that failed to compile as FINISHED_ERROR; the gate
    # must not abort the bet first
    s = make_sched(max_num_batched_tokens=64)
    s.add_request(req("norm", 64))
    b = req("b", 10, "bet")
    b.status = RequestStatus.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR
    b.structured_output_request = SimpleNamespace(grammar=ValueError("bad schema"))
    s.add_request(b)
    s.add_request(req("norm2", 10))  # non-bet waiting: the gate would fail
    got = []
    for _ in range(4):
        got += client_outs(step(s, s.schedule()), "b")
        if b.is_finished():
            break
    (o,) = got
    assert o.finish_reason == FinishReason.ERROR and o.stop_reason is None
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)


def test_budget_below_mtp_lookahead_is_raised_to_it(monkeypatch):
    # audit #4: with multi-module MTP lookahead L, a budget below L counted as spent at once
    from vllm.v1.core.sched.scheduler import Scheduler

    orig = Scheduler.__init__

    def init(self, *args, **kwargs):  # vLLM's own lookahead as with 4-module MTP
        orig(self, *args, **kwargs)
        self.num_prefill_lookahead = 4

    monkeypatch.setattr(Scheduler, "__init__", init)
    s = make_sched({"spec_prefill_budget": 2})
    assert s.num_prefill_lookahead == 4 and s._sptc_allow.budget == 4


def test_throttle_flag_without_deferral_counts_the_hold():
    # audit #5: nothing decodes, so vLLM defers nothing although throttling was requested
    s = make_sched({"bet_hold_steps": 0}, max_num_batched_tokens=64)
    s.add_request(req("norm", 64))
    bet = req("bet", 10, "bet")
    s.add_request(bet)
    out = s.schedule(throttle_prefills=True)
    assert out.num_scheduled_tokens == {"norm": 64}
    assert_rejected(s, bet, step(s, out), "held_too_long")


def test_bet_arriving_with_its_real_call_survives_a_deferred_step():
    # audit #34: on a DP-deferred step the real call waits for the cadence, not capacity
    s = make_sched({"bet_hold_steps": 0})
    s.add_request(req("n0", 10, max_tokens=50))
    step(s, s.schedule())
    real, bet = req("real", 10), req("bet", 10, "bet")
    s.add_request(real)
    s.add_request(bet)
    out = s.schedule(throttle_prefills=True)
    assert out.num_scheduled_tokens == {"n0": 1}
    assert not sptc_outs(step(s, out))
    assert bet.status == RequestStatus.WAITING and not s._sptc_held
    out = s.schedule()
    assert {"real", "bet"} <= set(out.num_scheduled_tokens)


def test_bet_requeued_by_reset_and_not_readmitted_is_reported_dropped():
    # audit #19: a bet that already streamed, requeued by reset_prefix_cache, then refused
    s = make_sched(max_num_batched_tokens=100)
    s.add_request(req("n0", 64, max_tokens=50))
    bet = req("bet", 20, "bet", max_tokens=50)
    s.add_request(bet)
    out = s.schedule()
    assert set(out.num_scheduled_tokens) == {"n0", "bet"}
    step(s, out)
    assert s.reset_prefix_cache(reset_running_requests=True)
    s.add_request(req("n1", 60))
    s.add_request(req("n2", 60))
    out = s.schedule()
    assert "bet" not in out.num_scheduled_tokens
    outs = step(s, out)
    assert bet.status == RequestStatus.FINISHED_ABORTED
    (o,) = client_outs(outs, "bet")
    assert o.finish_reason == FinishReason.ABORT and o.stop_reason == "sptc_bet_dropped"
    assert s.sptc_counters["bet_dropped_requeued:nonbet_waiting"] == 1
    assert "bet_rejected:nonbet_waiting" not in s.sptc_counters
    assert s.sptc_counters["bet_admitted"] == 1


def test_sync_bet_finishing_on_in_flight_token_is_requeued_not_dropped():
    # audit #35: sync scheduling with a step in flight (pipeline parallelism's batch queue)
    # has no placeholders. b's last token is in flight when norm needs a block: b is the
    # victim, but through vLLM's requeue, so the token is delivered and b ends normally.
    s = make_sched(max_num_seqs=4, max_num_batched_tokens=200, num_blocks=5)
    norm, b = req("norm", 31, max_tokens=50), req("b", 30, "bet", max_tokens=2)
    s.add_request(norm)
    oa = s.schedule()
    ra = runner_output(s, oa)
    s.add_request(b)
    ob = s.schedule()
    rb = runner_output(s, ob)
    assert ob.num_scheduled_tokens == {"b": 30}
    s.update_from_output(oa, ra)
    oc = s.schedule()
    rc = runner_output(s, oc)
    assert oc.num_scheduled_tokens == {"norm": 1}
    s.update_from_output(ob, rb)
    od = s.schedule()
    rd = runner_output(s, od)
    assert od.num_scheduled_tokens == {"b": 1}  # b's last token
    s.update_from_output(oc, rc)
    oe = s.schedule()  # norm needs a third block: b is the victim
    assert oe.num_scheduled_tokens == {"norm": 1}
    assert "b" in oe.preempted_req_ids and s.sptc_counters["bet_requeued_finishing"] == 1
    assert "bet_dropped" not in s.sptc_counters
    (o,) = client_outs(s.update_from_output(od, rd), "b")
    assert o.finish_reason == FinishReason.LENGTH and o.new_token_ids == [7]
    assert not sptc_outs(s.update_from_output(oe, runner_output(s, oe)))


def test_free_window_that_can_fill_every_slot_is_warned_about(monkeypatch):
    # audit #39: bets can take every sequence slot when free_window >= max_num_seqs. Kept
    # as set (kaggle/overhead_bench.py fills every slot on purpose), warned about at startup.
    from sptc_vllm import scheduler as mod

    seen = []
    monkeypatch.setattr(mod.logger, "warning", lambda *a: seen.append(a[0] % a[1:]))
    s = make_sched({"free_window": 8}, max_num_seqs=8)
    assert s.sptc_config.free_window == 8
    assert any("free_window 8 >= max_num_seqs 8" in m for m in seen)
    seen.clear()
    make_sched({"free_window": 7}, max_num_seqs=8)
    assert not seen


def test_async_requeued_finishing_bet_not_rejected_before_its_token_arrives():
    # audit #29, guards (a) and (b): a bet requeued to finish on its in-flight token must
    # not be gated before that token is delivered, neither at the end of the step (a) nor
    # when the waiting loop reaches it (b). free_window 1 and a non-bet waiting would
    # reject it at either point.
    s = make_sched({"bet_hold_steps": 0, "free_window": 1}, async_scheduling=True,
                   **dict(SMALL, max_num_seqs=3))
    bet = req("bet", 30, "bet", max_tokens=2)
    s.add_request(bet)
    step(s, s.schedule())
    s.add_request(req("norm", 32, max_tokens=50))
    out2 = s.schedule()
    assert set(out2.num_scheduled_tokens) == {"bet", "norm"}
    ro2 = runner_output(s, out2)
    s.add_request(req("w", 10))
    out3 = s.schedule()  # norm needs a block: the bet is the victim; no waiting loop
    assert out3.num_scheduled_tokens == {"norm": 1}
    assert bet.status == RequestStatus.PREEMPTED and s.sptc_counters["bet_requeued_finishing"] == 1
    out4 = s.schedule()  # the waiting loop admits w, then reaches the requeued bet
    assert out4.num_scheduled_tokens == {"norm": 1, "w": 10}
    assert bet.status == RequestStatus.PREEMPTED
    (o,) = client_outs(s.update_from_output(out2, ro2), "bet")
    assert o.finish_reason == FinishReason.LENGTH and o.stop_reason is None
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)


def test_async_victim_is_the_bet_that_still_needs_compute():
    # audit #29 (guard c): b_fin's last token is in flight, b_long still needs compute.
    # Ranked, the victim is b_long; with bets merely last it would have been b_fin.
    s = make_sched(async_scheduling=True, max_num_seqs=4, max_num_batched_tokens=200,
                   num_blocks=7)
    b_long, b_fin = req("b_long", 30, "bet", max_tokens=50), req("b_fin", 30, "bet", max_tokens=2)
    s.add_request(b_long)
    s.add_request(b_fin)
    step(s, s.schedule())
    s.add_request(req("norm", 32, max_tokens=50))
    out2 = s.schedule()
    assert set(out2.num_scheduled_tokens) == {"b_long", "b_fin", "norm"}
    assert s.kv_cache_manager.block_pool.get_num_free_blocks() == 0
    ro2 = runner_output(s, out2)
    out3 = s.schedule()  # norm needs a block
    assert out3.num_scheduled_tokens == {"norm": 1}
    assert b_long.status == RequestStatus.FINISHED_ABORTED
    assert s.sptc_counters["bet_dropped"] == 1 and "bet_requeued_finishing" not in s.sptc_counters
    outs = s.update_from_output(out2, ro2)
    (o,) = client_outs(outs, "b_fin")
    assert o.finish_reason == FinishReason.LENGTH
    (d,) = client_outs(outs, "b_long")
    assert d.finish_reason == FinishReason.ABORT and d.stop_reason == "sptc_bet_dropped"
