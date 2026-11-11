"""Pure tests for sptc_vllm.policy (stdlib + pytest only, milliseconds, no vLLM)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent  # integrations/
sys.path.insert(0, str(ROOT))

from sptc_vllm import policy  # noqa: E402
from sptc_vllm.policy import (  # noqa: E402
    PrefillAllowance,
    SptcClass,
    SptcConfig,
    admit_bet,
    bets_last,
    classify,
    config_from_additional,
    finishes_in_flight,
    is_prefill,
    order_by_rank,
    scan_decoders,
)


# --------------------------------------------------------------------------- classify
@pytest.mark.parametrize("extra", [None, {}, {"x": 1}, "bet", ["bet"], 3])
def test_classify_absent_or_non_mapping_is_normal(extra):
    assert classify(extra) is SptcClass.NORMAL


@pytest.mark.parametrize(
    "tag,cls",
    [("bet", SptcClass.BET), ("early", SptcClass.EARLY), ("BET", SptcClass.NORMAL),
     ("maybe", SptcClass.NORMAL), (1, SptcClass.NORMAL), (None, SptcClass.NORMAL),
     (["bet"], SptcClass.NORMAL), ("normal", SptcClass.NORMAL)],
)
def test_classify_tags(tag, cls):
    assert classify({policy.CLASS_KEY: tag, "kv_transfer_params": None}) is cls


def test_class_key_matches_client_contract():
    assert policy.CLASS_KEY == "sptc_class"
    assert policy.STOP_REASON_REJECTED == "sptc_bet_rejected"
    assert policy.STOP_REASON_DROPPED == "sptc_bet_dropped"


# --------------------------------------------------------------------------- is_prefill
@pytest.mark.parametrize(
    "num_tokens,computed,expect",
    [(10, 0, True), (10, 8, True), (10, 9, False), (10, 10, False), (10, 11, False),
     (1, 0, False), (2, 0, True)],
)
def test_is_prefill(num_tokens, computed, expect):
    assert is_prefill(num_tokens, computed) is expect


# --------------------------------------------------------------------------- admit_bet
CFG = SptcConfig()


@pytest.mark.parametrize(
    "running,nonbet,kv,cfg,admit,reason",
    [
        (0, False, 0.0, CFG, True, "ok"),
        (7, False, 0.5, CFG, True, "ok"),  # 7 + 1 == window: still inside
        (8, False, 0.5, CFG, False, "free_window"),
        (0, False, 0.0, SptcConfig(free_window=0), False, "free_window"),
        (100, False, 0.0, SptcConfig(free_window=0), False, "free_window"),
        (0, True, 0.0, CFG, False, "nonbet_waiting"),
        (0, False, 0.89, CFG, True, "ok"),
        (0, False, 0.9, CFG, True, "ok"),  # exactly 1 - kv_reserve: still admitted
        (0, False, 0.91, CFG, False, "kv_reserve"),
        (0, False, 0.99, SptcConfig(kv_reserve=0.0), True, "ok"),
        (0, False, 0.0, SptcConfig(kv_reserve=0.999), True, "ok"),
        # precedence: non-bet waiting, then window, then KV
        (8, True, 0.95, CFG, False, "nonbet_waiting"),
        (8, False, 0.95, CFG, False, "free_window"),
    ],
)
def test_admit_bet(running, nonbet, kv, cfg, admit, reason):
    v = admit_bet(num_running=running, nonbet_waiting=nonbet, kv_usage=kv, cfg=cfg)
    assert (v.admit, v.reason) == (admit, reason)


def test_admit_bet_is_keyword_only():
    with pytest.raises(TypeError):
        admit_bet(0, False, 0.0, CFG)  # type: ignore[misc]


# --------------------------------------------------------------------------- in flight
@pytest.mark.parametrize(
    "placeholders,computed,prompt,max_tokens,expect",
    [
        (0, 31, 30, 2, False),  # sync, or nothing in flight
        (1, 31, 30, 2, True),  # the in-flight decode is token #2 of 2
        (1, 31, 30, 3, False),
        (1, 30, 30, 1, True),  # prefill step in flight samples the only token
        (3, 34, 30, 3, True),  # 2 draft placeholders: counted as if all rejected
        (3, 34, 30, 4, False),
    ],
)
def test_finishes_in_flight(placeholders, computed, prompt, max_tokens, expect):
    got = finishes_in_flight(
        num_output_placeholders=placeholders, num_computed_tokens=computed,
        num_prompt_tokens=prompt, max_tokens=max_tokens,
    )
    assert got is expect


@pytest.mark.parametrize(
    "computed,num_tokens,in_flight,prompt,max_tokens,expect",
    [
        (31, 31, 1, 30, 2, True),  # sync + PP: decode of token #2 of 2 in flight
        (31, 31, 1, 30, 3, False),
        (31, 31, 0, 30, 2, False),  # nothing in flight
        (30, 30, 30, 30, 1, True),  # last prefill chunk in flight samples the only token
        (20, 30, 20, 30, 1, False),  # partial prefill chunk in flight: no token sampled
    ],
)
def test_finishes_in_flight_sync_with_steps_in_flight(
    computed, num_tokens, in_flight, prompt, max_tokens, expect
):
    # audit #35: no placeholders under sync scheduling, but a batch queue keeps steps in
    # flight; the in-flight step's token was thrown away when the bet was dropped
    got = finishes_in_flight(
        num_output_placeholders=0, num_computed_tokens=computed, num_prompt_tokens=prompt,
        max_tokens=max_tokens, num_tokens=num_tokens, num_in_flight_tokens=in_flight,
    )
    assert got is expect


# --------------------------------------------------------------------------- bets_last
def test_bets_last_stable_partition():
    items = ["B1", "N1", "B2", "N2", "N3", "B3"]
    out = bets_last(items, lambda s: s.startswith("B"))
    assert out == ["N1", "N2", "N3", "B1", "B2", "B3"]
    assert items == ["B1", "N1", "B2", "N2", "N3", "B3"]  # input untouched


@pytest.mark.parametrize(
    "items", [[], ["N1", "N2"], ["B1"], ["N1", "B1", "B2"], ["B1", "B2"], ["N1", "N2", "B1"]]
)
def test_bets_last_returns_same_object_when_partitioned(items):
    assert bets_last(items, lambda s: s.startswith("B")) is items


def test_bets_last_calls_predicate_once_per_item():
    calls = []
    bets_last(["B1", "N1"], lambda s: calls.append(s) or s.startswith("B"))
    assert calls == ["B1", "N1"]


def test_order_by_rank_stable_and_identity():
    items = ["n1", "f1", "b1", "n2", "b2", "f2"]
    rank = {"n": 0, "f": 1, "b": 2}
    out = order_by_rank(items, lambda s: rank[s[0]])
    assert out == ["n1", "n2", "f1", "f2", "b1", "b2"]
    assert order_by_rank(out, lambda s: rank[s[0]]) is out
    assert order_by_rank([], lambda s: 0) == []


# --------------------------------------------------------------------------- allowance
def test_allowance_cap_charge_reset():
    a = PrefillAllowance(512)
    assert not a.unlimited and not a.exhausted
    assert a.cap(2000) == 512 and a.cap(100) == 100
    a.charge(100)
    assert a.cap(2000) == 412 and not a.exhausted
    a.charge(412)
    assert a.exhausted and a.cap(2000) == 0 and a.cap(0) == 0
    a.charge(5)  # over-charge (e.g. after a failed allocation) stays exhausted
    assert a.exhausted and a.left == -5 and a.cap(10) == 0
    a.reset()
    assert a.left == 512 and not a.exhausted


def test_allowance_cap_keeps_a_share():
    a = PrefillAllowance(512)
    assert a.cap(2000, keep=300) == 212 and a.cap(100, keep=300) == 100
    assert a.cap(2000, keep=512) == 0 and a.cap(2000, keep=10**6) == 0
    a.charge(212)
    assert a.cap(2000, keep=300) == 0 and a.cap(2000) == 300
    assert PrefillAllowance(0).cap(2000, keep=300) == 2000  # unlimited keeps nothing back


def test_allowance_short_of_lookahead():
    a = PrefillAllowance(6)
    assert not a.short_of(4)
    a.charge(4)  # 2 left
    assert a.short_of(4) and not a.short_of(2) and not a.short_of(1) and not a.short_of(0)
    a.charge(2)
    assert a.short_of(0) and a.short_of(1) and a.exhausted
    assert not PrefillAllowance(0).short_of(10**6)


@pytest.mark.parametrize("budget", [0, -1])
def test_allowance_unlimited(budget):
    a = PrefillAllowance(budget)
    assert a.unlimited and not a.exhausted
    assert a.cap(10**6) == 10**6
    a.charge(10**6)
    assert not a.exhausted and a.cap(7) == 7


BET, EARLY, NORMAL = SptcClass.BET, SptcClass.EARLY, SptcClass.NORMAL


def _never():
    pytest.fail("must not scan")


def test_allowance_fixed_always_applies_without_scanning():
    a = PrefillAllowance(512)
    assert a.applies(EARLY, _never) and a.applies(BET, _never)
    assert a.applied(EARLY) and a.applied(BET)


def test_allowance_unlimited_never_applies_without_scanning():
    for a in (PrefillAllowance(0), PrefillAllowance(0, adaptive=True)):
        assert not a.applies(EARLY, _never) and not a.applies(BET, _never)
        assert not a.applied(BET)


@pytest.mark.parametrize(
    "decoders, early, bet",
    [
        ((True, True), True, True),  # an untagged stream decodes: both yield
        ((False, True), False, True),  # only early decoders: bets yield, early work does not
        ((False, False), False, False),  # only bets (or nothing) decode: nothing to protect
    ],
)
def test_allowance_adaptive_by_class(decoders, early, bet):
    a = PrefillAllowance(512, adaptive=True)
    assert not a.applied(EARLY) and not a.applied(BET)  # undecided: nothing limited yet
    assert a.applies(EARLY, lambda: decoders) is early
    assert a.applies(BET, _never) is bet  # one scan per step
    assert a.applied(EARLY) is early and a.applied(BET) is bet


def test_allowance_adaptive_scans_once_per_step():
    scans = []

    def scan(answer):
        def f():
            scans.append(answer)
            return answer
        return f

    a = PrefillAllowance(512, adaptive=True)
    assert not a.applies(EARLY, scan((False, False)))
    assert not a.applies(EARLY, scan((True, True)))  # decided for this step
    assert scans == [(False, False)]
    a.reset()
    assert a.applies(EARLY, scan((True, True)))
    a.charge(512)
    assert a.short_of(1)
    a.reset()  # next step: undecided again, full allowance
    assert a.left == 512 and not a.applied(EARLY)
    assert not a.applies(BET, scan((False, False)))
    assert scans == [(False, False), (True, True), (False, False)]


@pytest.mark.parametrize(
    "pairs, expect",
    [
        ([], (False, False)),
        ([(NORMAL, False), (EARLY, False), (BET, True)], (False, False)),  # only a bet decodes
        ([(EARLY, True), (BET, True)], (False, True)),
        ([(BET, True), (EARLY, True), (NORMAL, True)], (True, True)),
        ([(NORMAL, False), (EARLY, True)], (False, True)),  # a prefilling normal: not a stream
    ],
)
def test_scan_decoders(pairs, expect):
    assert scan_decoders(pairs) == expect


def test_scan_decoders_stops_at_first_untagged_decoder():
    def pairs():
        yield EARLY, True
        yield NORMAL, True
        pytest.fail("scanned past the first untagged decoder")

    assert scan_decoders(pairs()) == (True, True)


# --------------------------------------------------------------------------- config
@pytest.mark.parametrize(
    "additional", [None, {}, {"sptc": None}, {"sptc": {}}, {"other": 1}, object(), "x"]
)
def test_config_defaults(additional):
    cfg = config_from_additional(additional)
    assert cfg == SptcConfig()
    assert (cfg.free_window, cfg.kv_reserve, cfg.spec_prefill_budget) == (8, 0.10, 512)
    assert cfg.bet_hold_steps == 16
    assert cfg.prefill_allowance == "fixed" and cfg.allowance_budget == 512


@pytest.mark.parametrize(
    "mode, budget, effective",
    [("fixed", 512, 512), ("adaptive", 512, 512), ("off", 512, 0), ("adaptive", 0, 0)],
)
def test_config_prefill_allowance(mode, budget, effective):
    cfg = config_from_additional(
        {"sptc": {"prefill_allowance": mode, "spec_prefill_budget": budget}}
    )
    assert cfg.prefill_allowance == mode and cfg.spec_prefill_budget == budget
    assert cfg.allowance_budget == effective


def test_config_overrides():
    cfg = config_from_additional(
        {"sptc": {"free_window": 4, "kv_reserve": 0, "spec_prefill_budget": 0}, "x": 1}
    )
    assert (cfg.free_window, cfg.kv_reserve, cfg.spec_prefill_budget) == (4, 0, 0)
    assert config_from_additional({"sptc": {"kv_reserve": 0.25}}).kv_reserve == 0.25
    assert config_from_additional({"sptc": {"bet_hold_steps": 0}}).bet_hold_steps == 0


@pytest.mark.parametrize(
    "raw",
    [
        {"free_windw": 8},
        {"free_window": True},
        {"free_window": -1},
        {"free_window": 8.0},
        {"kv_reserve": 1.0},
        {"kv_reserve": -0.1},
        {"kv_reserve": "0.1"},
        {"kv_reserve": True},
        {"spec_prefill_budget": 1.5},
        {"spec_prefill_budget": "512"},
        {"bet_hold_steps": -1},
        {"bet_hold_steps": 2.0},
        {"bet_hold_steps": True},
        {"prefill_allowance": "Fixed"},
        {"prefill_allowance": "dynamic"},
        {"prefill_allowance": None},
        {"prefill_allowance": 1},
        [],
        "free_window=8",
    ],
)
def test_config_errors(raw):
    with pytest.raises(ValueError):
        config_from_additional({"sptc": raw})


def test_config_is_frozen():
    with pytest.raises(AttributeError):
        SptcConfig().free_window = 3  # type: ignore[misc]


# --------------------------------------------------------------------------- hygiene
def test_policy_does_not_import_vllm():
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT)!r})\n"
        "import sptc_vllm, sptc_vllm.policy\n"
        "assert not any(m == 'vllm' or m.startswith('vllm.') for m in sys.modules), "
        "sorted(m for m in sys.modules if m.startswith('vllm'))\n"
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True)
