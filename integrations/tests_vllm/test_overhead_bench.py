"""kaggle/overhead_bench.py on real vLLM 0.32, tiny sizes: the scheduler reaches the
intended steady state (n running decodes, n/2 waiting, running bets never rejected) for
every variant, sync and async. The timing numbers themselves come from running the script.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("vllm")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kaggle"))
import overhead_bench as ob  # noqa: E402


@pytest.mark.parametrize("async_scheduling", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("variant", ob.VARIANTS)
def test_overhead_case_steady_state(variant, async_scheduling):
    r = ob.vllm_case(16, variant, async_scheduling, steps=5)
    assert r["n_running"] == 16 and r["n_waiting"] == 8
    assert r["schedule"]["p50_us"] > 0 and r["update_from_output"]["p50_us"] > 0
    if variant == "sptc-tagged":
        assert r["running_bets"] == 4


def test_overhead_case_loads_in_batches():
    # n = 300 needs several loading steps: nothing may be rejected on the way
    r = ob.vllm_case(300, "sptc-tagged", False, steps=3)
    assert r["n_running"] == 300 and r["running_bets"] == 75
