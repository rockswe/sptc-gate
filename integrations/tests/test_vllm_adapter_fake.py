"""The vLLM adapter (sptc_vllm/scheduler.py) run on a stand-in of vLLM 0.32's scheduler
(tests/_vllm_fake.py), so its behaviour is tested without vLLM or torch (audit #15). The
same cases that need the real scheduler are in tests_vllm/ (run on Kaggle). Skipped where
vLLM itself is installed: there tests_vllm runs the adapter on the real scheduler.
"""

import random
import zlib
from collections import deque
from importlib.util import find_spec
from types import SimpleNamespace

import pytest

if find_spec("vllm") is not None:
    pytest.skip("vLLM is installed: tests_vllm covers the adapter", allow_module_level=True)

import _vllm_fake as F  # noqa: E402

A = F.load_adapter()
RS = F.RequestStatus
ASYNC = pytest.mark.parametrize("async_scheduling", [False, True], ids=["sync", "async"])


def make(sptc=None, **kw):
    return A.SptcScheduler(vllm_config=F.config({} if sptc is None else sptc, **kw))


def stock(**kw):
    cls = F.AsyncScheduler if kw.get("async_scheduling") else F.Scheduler
    return cls(vllm_config=F.config(None, **kw))


def sampled(s, out, token=7):
    """What the model runner returns for `out`, computed when the step is scheduled."""
    return {
        rid: [] if s.requests[rid].is_prefill_chunk else [token]
        for rid in out.num_scheduled_tokens
    }


def step(s, out=None, **extra):
    out = out if out is not None else s.schedule()
    return out, s.update_from_output(out, {**sampled(s, out), **extra})


def outs_of(outs, rid=None):
    return [o for eco in outs.values() for o in eco.outputs if rid is None or o.request_id == rid]


def rejected(s, r, outs, reason, stop="sptc_bet_rejected"):
    assert r.status == RS.FINISHED_ABORTED and r.request_id not in s.requests
    (o,) = outs_of(outs, r.request_id)
    assert o.finish_reason == F.FinishReason.ABORT and o.stop_reason == stop
    return True


# ===================================================================== untagged is stock
def workload(seed, n=50, steps=150):
    rng = random.Random(seed)
    return sorted(
        (rng.randrange(steps), f"r{i}", rng.randint(1, 300), rng.randint(1, 40))
        for i in range(n)
    )


def drive(s, tag, seed, queue_size, max_steps=3000):
    """Engine loop as in EngineCore.step_with_batch_queue (queue_size 2: async scheduling,
    the next step is scheduled before the previous one's output is processed). Tokens are
    EOS on a fixed hash of (request, loop index), so both arms see the same EOS."""
    arrivals, k, log, queue = workload(seed), 0, [], deque()
    for t in range(max_steps):
        while k < len(arrivals) and arrivals[k][0] <= t:
            _, rid, n, m = arrivals[k]
            s.add_request(F.Request(rid, n, tag, max_tokens=m))
            k += 1
        if k == len(arrivals) and not s.requests and not queue:
            break
        if s.has_requests():
            out = s.schedule()
            tok = {
                rid: [] if s.requests[rid].is_prefill_chunk
                else [F.EOS if zlib.crc32(f"{rid}:{t}".encode()) % 23 == 0 else 7]
                for rid in out.num_scheduled_tokens
            }
            queue.appendleft((out, tok))
            log.append(("S", t, dict(out.num_scheduled_tokens), out.scheduled_new_reqs,
                        out.scheduled_resumed_reqs, out.scheduled_running_reqs,
                        sorted(out.preempted_req_ids), sorted(out.finished_req_ids)))
            if len(queue) < queue_size and (out.total_num_scheduled_tokens > 0
                                            or s.has_requests()):
                continue
        elif not queue:
            continue
        out, tok = queue.pop()
        outs = s.update_from_output(out, tok)
        log.append(("U", t, sorted((o.request_id, tuple(o.new_token_ids), o.finish_reason,
                                    o.stop_reason) for o in outs_of(outs))))
    assert k == len(arrivals) and not s.requests and not queue, "workload did not drain"
    return log


MODES = pytest.mark.parametrize(
    "async_scheduling,queue_size", [(False, 1), (True, 1), (True, 2)],
    ids=["sync", "async-lockstep", "async-overlap"],
)


@MODES
@pytest.mark.parametrize(
    "tag,sptc",
    [(None, {}), (None, {"spec_prefill_budget": 16}), (None, {"prefill_allowance": "adaptive"}),
     ("early", {"spec_prefill_budget": 0}), ("early", {"prefill_allowance": "off"})],
    ids=["normal", "normal-tiny-budget", "normal-adaptive", "early-unlimited", "early-off"],
)
def test_untagged_identical_to_stock(async_scheduling, queue_size, tag, sptc):
    kw = dict(async_scheduling=async_scheduling, max_num_seqs=8, max_num_batched_tokens=256,
              num_blocks=40)
    ref = drive(stock(**kw), tag, 7, queue_size)
    got = drive(make(sptc, **kw), tag, 7, queue_size)
    assert any(e[0] == "S" and e[6] for e in ref), "workload must exercise preemption"
    assert len(got) == len(ref)
    for i, (a, b) in enumerate(zip(ref, got, strict=True)):
        assert a == b, f"entry {i} differs:\nstock {a}\nsptc  {b}"


# ============================================================ #2 allowance: early first
def test_running_bet_prefill_leaves_the_allowance_to_waiting_early():
    s = make(max_num_batched_tokens=2048)
    bet = F.Request("bet", 8192, "bet")
    s.add_request(bet)
    out, _ = step(s)
    assert out.num_scheduled_tokens == {"bet": 512}
    s.add_request(F.Request("early", 300, "early"))
    out, _ = step(s)
    # before the fix: {"bet": 512}, and the early request waited for 16 steps
    assert out.num_scheduled_tokens == {"bet": 212, "early": 300}
    out, _ = step(s)
    assert out.num_scheduled_tokens == {"bet": 512, "early": 1}


def test_running_bet_keeps_the_allowance_when_no_early_waits():
    s = make(max_num_batched_tokens=2048)
    s.add_request(F.Request("bet", 8192, "bet"))
    step(s)
    s.add_request(F.Request("norm", 300))
    out, _ = step(s)
    assert out.num_scheduled_tokens == {"bet": 512, "norm": 300}


def test_adaptive_keeps_early_share_only_while_early_is_limited():
    # adaptive: an early prefill is limited only while an untagged request decodes; with
    # none decoding there is nothing to keep, and the bet is not limited either
    s = make({"prefill_allowance": "adaptive"}, max_num_batched_tokens=2048)
    s.add_request(F.Request("bet", 8192, "bet"))
    step(s)
    s.add_request(F.Request("early", 3000, "early"))
    out, _ = step(s)
    assert out.num_scheduled_tokens == {"bet": 2048}  # early: token budget, not the cap
    s2 = make({"prefill_allowance": "adaptive"}, max_num_batched_tokens=2048)
    s2.add_request(F.Request("norm", 10, max_tokens=100))
    step(s2)
    s2.add_request(F.Request("bet", 8192, "bet"))
    step(s2)
    s2.add_request(F.Request("early", 300, "early"))
    out, _ = step(s2)
    assert out.num_scheduled_tokens == {"norm": 1, "bet": 212, "early": 300}


def test_bet_not_held_at_zero_for_early_work_that_cannot_be_admitted():
    # follow-up to #2: the early request's full prompt does not fit next to the bet's KV, so
    # vLLM's waiting loop breaks on it. The kept share cut the bet to 0 tokens on every
    # step and nothing ran again. Now the bet loses one step (not one per early request
    # queued behind the first), then runs and frees the KV.
    s = make(max_num_batched_tokens=2048, num_blocks=101)  # 100 usable blocks of 16
    s.add_request(F.Request("bet", 1500, "bet", max_tokens=50))
    step(s)
    step(s)
    early = F.Request("early", 600, "early", max_tokens=5)
    s.add_request(early)
    s.add_request(F.Request("early2", 600, "early", max_tokens=5))
    out, _ = step(s)
    assert out.num_scheduled_tokens == {} and early.status == RS.WAITING
    out, _ = step(s)
    assert out.num_scheduled_tokens == {"bet": 476}
    assert s.sptc_counters["early_kept_not_admitted"] == 1
    for _ in range(100):
        if not s.has_requests():
            break
        step(s)
    assert not s.has_requests() and early.status == RS.FINISHED_LENGTH_CAPPED
    assert s.sptc_counters["early_kept_not_admitted"] == 1


def test_no_allowance_kept_for_early_work_while_paused():
    # PAUSED_NEW admits nothing from `waiting`, and the pause drains only when running
    # requests finish: a running bet must keep its whole allowance
    s = make(max_num_batched_tokens=2048)
    s.add_request(F.Request("bet", 8192, "bet", max_tokens=16))
    step(s)
    s.add_request(F.Request("early", 3000, "early", max_tokens=4))
    s.set_pause_state(F.PauseState.PAUSED_NEW)
    for _ in range(3):
        out, _ = step(s)
        assert out.num_scheduled_tokens == {"bet": 512}
    assert not s.sptc_counters["early_kept_not_admitted"]


def test_no_allowance_kept_for_early_work_while_every_slot_is_taken():
    s = make({"free_window": 2}, max_num_batched_tokens=2048, max_num_seqs=2)
    s.add_request(F.Request("norm", 10, max_tokens=100))
    step(s)
    s.add_request(F.Request("bet", 8192, "bet"))
    step(s)
    s.add_request(F.Request("early", 300, "early"))
    out, _ = step(s)
    assert out.num_scheduled_tokens == {"norm": 1, "bet": 512}


# ======================================================= #10 hold behind another bet
def test_small_bet_behind_long_bet_prefill_is_not_held_too_long():
    s = make(max_num_batched_tokens=2048)
    s.add_request(F.Request("b1", 9216, "bet"))
    step(s)
    b2 = F.Request("b2", 64, "bet")
    s.add_request(b2)
    for _ in range(25):
        out, outs = step(s)
        assert not outs_of(outs, "b2") or b2.status == RS.RUNNING
        if "b2" in out.num_scheduled_tokens:
            break
    assert b2.status == RS.RUNNING, dict(s.sptc_counters)
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)


def test_bet_behind_early_prefill_still_counts_hold_steps():
    s = make({"bet_hold_steps": 2}, max_num_batched_tokens=2048)
    s.add_request(F.Request("e", 9216, "early"))
    step(s)
    b = F.Request("b", 64, "bet")
    s.add_request(b)
    step(s)
    step(s)
    assert s._sptc_held == {"b": 2}
    _, outs = step(s)
    assert rejected(s, b, outs, "held_too_long")


# ============================================================== #1, #33 async KV loads
def _seven_running(s, prompt):
    for i in range(7):
        s.add_request(F.Request(f"n{i}", prompt, max_tokens=50))
    step(s)


def test_bet_in_async_kv_load_is_not_regated_by_its_own_allocation():
    conn = F.FakeConnector({"rb": 160})
    s = make(num_blocks=101, connector=conn)
    _seven_running(s, 176)  # 7 x 12 blocks = 84 of 100 once the next decode is placed
    assert s.kv_cache_manager.usage <= 0.9
    rb = F.Request("rb", 160, "bet")
    s.add_request(rb)
    out, outs = step(s)
    assert rb.status == RS.WAITING_FOR_REMOTE_KVS and s.kv_cache_manager.usage > 0.9
    assert not outs_of(outs, "rb") and s.sptc_counters["bet_kv_load"] == 1
    out, outs = step(s, finished_recving=["rb"])
    out, outs = step(s)
    assert rb.status == RS.RUNNING and "rb" in out.num_scheduled_tokens
    assert s.sptc_counters["bet_admitted"] == 1
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)


def test_async_kv_load_bets_count_toward_the_free_window():
    conn = F.FakeConnector({f"b{i}": 32 for i in range(5)})
    s = make(connector=conn)
    _seven_running(s, 16)
    bets = [F.Request(f"b{i}", 32, "bet") for i in range(5)]
    for b in bets:
        s.add_request(b)
    out, outs = step(s)
    assert [b.status for b in bets] == [RS.WAITING_FOR_REMOTE_KVS] + [RS.FINISHED_ABORTED] * 4
    assert s.sptc_counters["bet_rejected:free_window"] == 4


def test_paused_new_keeps_a_bet_whose_kv_load_finished():
    conn = F.FakeConnector({"rb": 32})
    s = make(connector=conn, max_num_batched_tokens=64)
    rb = F.Request("rb", 32, "bet")
    s.add_request(rb)
    step(s)
    assert rb.status == RS.WAITING_FOR_REMOTE_KVS
    s.add_request(F.Request("norm", 64))
    s.set_pause_state(F.PauseState.PAUSED_NEW)
    out, outs = step(s, finished_recving=["rb"])
    assert not outs_of(outs, "rb") and not rb.is_finished()
    out, outs = step(s)  # PAUSED_NEW still drains kv_holding_waiting
    assert rb.status == RS.RUNNING
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)


# ================================================================== #3 grammar errors
def test_bet_with_failed_grammar_is_an_error_not_a_rejection():
    s = make(max_num_batched_tokens=64)
    s.add_request(F.Request("norm", 64))
    b = F.Request("b", 10, "bet")
    b.status = RS.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR
    b.structured_output_request = SimpleNamespace(grammar=ValueError("bad schema"))
    s.add_request(b)
    s.add_request(F.Request("norm2", 10))  # non-bet waiting: the gate would fail
    seen = []
    for _ in range(4):
        _, outs = step(s)
        seen += outs_of(outs, "b")
        if b.is_finished():
            break
    (o,) = seen
    assert o.finish_reason == F.FinishReason.ERROR and o.stop_reason is None
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)


# ================================================================== #4 MTP lookahead
def test_budget_below_mtp_lookahead_is_raised_to_it():
    s = make({"spec_prefill_budget": 2}, num_prefill_lookahead=4)
    assert s._sptc_allow.budget == 4
    s.add_request(F.Request("e", 12, "early"))
    out, _ = step(s)
    assert out.num_scheduled_tokens == {"e": 4}


# ============================================================ #5, #34 DP throttle
def test_throttle_flag_without_deferral_counts_the_hold():
    s = make({"bet_hold_steps": 0}, max_num_batched_tokens=64)
    s.add_request(F.Request("norm", 64))
    b = F.Request("b", 10, "bet")
    s.add_request(b)
    # throttle requested, but nothing decodes: vLLM defers nothing, so the step counts
    out, outs = step(s, s.schedule(throttle_prefills=True))
    assert out.num_scheduled_tokens == {"norm": 64}
    assert rejected(s, b, outs, "held_too_long")


def test_bet_arriving_with_its_real_call_survives_a_deferred_step():
    s = make({"bet_hold_steps": 0})
    s.add_request(F.Request("n0", 10, max_tokens=50))
    step(s)
    real, b = F.Request("real", 10), F.Request("b", 10, "bet")
    s.add_request(real)
    s.add_request(b)
    out, outs = step(s, s.schedule(throttle_prefills=True))
    assert out.num_scheduled_tokens == {"n0": 1}  # vLLM deferred real's prefill
    assert not outs_of(outs, "b") and b.status == RS.WAITING and not s._sptc_held
    out, _ = step(s)
    assert {"real", "b"} <= set(out.num_scheduled_tokens)


# ======================================================== #19 requeued after admission
def test_bet_requeued_by_reset_and_not_readmitted_is_reported_dropped():
    s = make(max_num_batched_tokens=100)
    s.add_request(F.Request("n0", 64, max_tokens=50))
    b = F.Request("b", 20, "bet", max_tokens=50)
    s.add_request(b)
    out, _ = step(s)
    assert set(out.num_scheduled_tokens) == {"n0", "b"} and s.sptc_counters["bet_admitted"] == 1
    assert s.reset_prefix_cache(reset_running_requests=True)
    s.add_request(F.Request("n1", 60))
    s.add_request(F.Request("n2", 60))
    out, outs = step(s)
    assert rejected(s, b, outs, "nonbet_waiting", stop="sptc_bet_dropped")
    assert s.sptc_counters["bet_dropped_requeued:nonbet_waiting"] == 1
    assert "bet_rejected:nonbet_waiting" not in s.sptc_counters
    assert s.sptc_counters["bet_admitted"] == 1


def test_bet_requeued_by_reset_on_idle_server_is_readmitted_once():
    s = make()
    b = F.Request("b", 20, "bet", max_tokens=20)
    s.add_request(b)
    step(s)
    assert s.reset_prefix_cache(reset_running_requests=True)
    out, _ = step(s)
    assert b.status == RS.RUNNING
    assert s.sptc_counters["bet_admitted"] == 1 and s.sptc_counters["bet_readmitted"] == 1


# ================================================================ #25 idle iterations
def test_step_that_schedules_nothing_does_not_count_the_hold():
    s = make({"bet_hold_steps": 0})
    b = F.Request("b", 10, "bet")
    s.add_request(b)
    s.ec_pending.add("b")  # e.g. encoder prefetch still in flight: vLLM skips it
    for _ in range(3):
        out, outs = step(s)
        assert out.total_num_scheduled_tokens == 0 and not outs_of(outs)
    assert b.status == RS.WAITING and not s._sptc_held
    s.ec_pending.clear()
    out, _ = step(s)
    assert "b" in out.num_scheduled_tokens


# ===================================================== #35 sync with a step in flight
def test_sync_bet_finishing_on_in_flight_token_is_requeued_not_dropped():
    # pipeline parallelism under sync scheduling: the next step is scheduled before the
    # previous output is processed. b's last token (max_tokens 2) is in flight when norm
    # needs a block; b is the victim but finishes normally on the in-flight token.
    s = make(max_num_seqs=4, max_num_batched_tokens=200, num_blocks=5)
    norm, b = F.Request("norm", 31, max_tokens=50), F.Request("b", 30, "bet", max_tokens=2)
    s.add_request(norm)
    oa = s.schedule()
    ra = sampled(s, oa)  # norm prefill in flight
    s.add_request(b)
    ob = s.schedule()
    rb = sampled(s, ob)  # b prefill in flight
    assert ob.num_scheduled_tokens == {"b": 30}
    s.update_from_output(oa, ra)
    oc = s.schedule()
    rc = sampled(s, oc)
    assert oc.num_scheduled_tokens == {"norm": 1}
    s.update_from_output(ob, rb)
    od = s.schedule()
    rd = sampled(s, od)
    assert od.num_scheduled_tokens == {"b": 1}  # b's last token
    s.update_from_output(oc, rc)
    oe = s.schedule()  # norm needs a third block: b is the victim
    assert oe.num_scheduled_tokens == {"norm": 1}
    assert "b" in oe.preempted_req_ids and s.sptc_counters["bet_requeued_finishing"] == 1
    assert "bet_dropped" not in s.sptc_counters
    outs = s.update_from_output(od, rd)
    (o,) = outs_of(outs, "b")
    assert o.finish_reason == F.FinishReason.LENGTH and o.new_token_ids == [7]


# ===================================================================== #39 slots
def test_free_window_that_can_fill_every_slot_is_warned_about(monkeypatch):
    seen = []
    monkeypatch.setattr(A.logger, "warning", lambda *a: seen.append(a[0] % a[1:]))
    s = make({"free_window": 8}, max_num_seqs=8)
    assert s.sptc_config.free_window == 8  # kept: only warned about
    assert any("free_window 8 >= max_num_seqs 8" in m for m in seen)
    seen.clear()
    make({"free_window": 7}, max_num_seqs=8)
    assert not seen


# ===================================================== #29 async in-flight guards
def test_async_requeued_finishing_bet_not_gated_before_its_token_arrives():
    # guards (a) end-of-step and (b) hook: free_window 1 and a non-bet waiting would
    # reject the requeued bet at either point, losing its finished result
    s = make({"bet_hold_steps": 0, "free_window": 1}, async_scheduling=True, max_num_seqs=3,
             max_num_batched_tokens=200, num_blocks=5)
    b = F.Request("b", 30, "bet", max_tokens=2)
    s.add_request(b)
    step(s)
    s.add_request(F.Request("norm", 32, max_tokens=50))
    o2 = s.schedule()
    r2 = sampled(s, o2)
    s.add_request(F.Request("w", 10))
    o3 = s.schedule()
    assert o3.num_scheduled_tokens == {"norm": 1} and b.status == RS.PREEMPTED
    o4 = s.schedule()
    assert o4.num_scheduled_tokens == {"norm": 1, "w": 10} and b.status == RS.PREEMPTED
    (o,) = outs_of(s.update_from_output(o2, r2), "b")
    assert o.finish_reason == F.FinishReason.LENGTH
    assert not any(k.startswith("bet_rejected") for k in s.sptc_counters)


def test_async_victim_is_the_bet_that_still_needs_compute():
    # guard (c), the running rank: b_fin's last token is in flight, b_long is the victim
    s = make(async_scheduling=True, max_num_seqs=4, max_num_batched_tokens=200, num_blocks=7)
    b_long = F.Request("b_long", 30, "bet", max_tokens=50)
    b_fin = F.Request("b_fin", 30, "bet", max_tokens=2)
    s.add_request(b_long)
    s.add_request(b_fin)
    step(s)
    s.add_request(F.Request("norm", 32, max_tokens=50))
    o2 = s.schedule()
    r2 = sampled(s, o2)
    o3 = s.schedule()
    assert o3.num_scheduled_tokens == {"norm": 1} and b_long.status == RS.FINISHED_ABORTED
    outs = s.update_from_output(o2, r2)
    assert outs_of(outs, "b_fin")[0].finish_reason == F.FinishReason.LENGTH
    assert outs_of(outs, "b_long")[0].stop_reason == "sptc_bet_dropped"
