"""Scheduler CPU time per step: stock vLLM vs the sptc plugin, no GPU (the model runner is
faked as in the other tests). It measures the plugin's per-step hook overhead, one of the
candidate causes of the 1-agent slowdown on the T4 (results/t4_run1_analysis/root_cause.md).

The workload is the T4 load test's 1-agent shape: one untagged stream (the root) decoding
next to 16 early-tagged sub-calls (map16), async scheduling as on the server. Each arm is
timed for schedule() + update_from_output() over many steps, alternating arms to spread
machine noise. Print the numbers with:

    pytest sptc-sim/integrations/tests_vllm/test_sptc_overhead.py -q -s -p no:cacheprovider

Set SPTC_OVERHEAD_OUT=path.json to also write them to a file.
"""

import json
import os
import statistics
import time

import pytest

pytest.importorskip("vllm")

from _helpers import build, make_sched, req, runner_output  # noqa: E402

STEPS, WARMUP, ROUNDS = 400, 40, 5
# 1 root + 16 sub-calls = 17 requests. build()'s default max_num_seqs=16 would leave one
# waiting (vLLM admits while len(running) < max_num_active_reqs = max_num_seqs).
SEQS = 32


def _arm(make, tag):
    s = make()
    s.add_request(req("root", 20, max_tokens=1500))
    for i in range(16):
        s.add_request(req(f"sub{i}", 40, tag, max_tokens=1500))
    return s


def _time(s, steps):
    t0 = time.perf_counter_ns()
    for _ in range(steps):
        out = s.schedule()
        s.update_from_output(out, runner_output(s, out))
    return (time.perf_counter_ns() - t0) / steps / 1000  # microseconds per step


@pytest.mark.parametrize("mode", ["fixed", "adaptive"])
def test_scheduler_overhead_per_step(mode):
    arms = {
        "stock": lambda: build(async_scheduling=True, max_num_seqs=SEQS),
        "sptc_untagged": lambda: make_sched({"prefill_allowance": mode},
                                            async_scheduling=True, max_num_seqs=SEQS),
        "sptc_early": lambda: make_sched({"prefill_allowance": mode},
                                         async_scheduling=True, max_num_seqs=SEQS),
    }
    tags = {"stock": None, "sptc_untagged": None, "sptc_early": "early"}
    us = {k: [] for k in arms}
    for _ in range(ROUNDS):
        for name, make in arms.items():
            s = _arm(make, tags[name])
            _time(s, WARMUP)
            us[name].append(_time(s, STEPS))
            assert len(s.running) == 17  # all still decoding: same work in every arm
    med = {k: statistics.median(v) for k, v in us.items()}
    res = {"mode": mode, "median_us_per_step": med,
           "overhead_us": {k: med[k] - med["stock"] for k in med if k != "stock"},
           "runs_us": us}
    print(json.dumps(res))
    out = os.environ.get("SPTC_OVERHEAD_OUT")
    if out:
        with open(out, "a") as f:
            f.write(json.dumps(res) + "\n")
    # Loose sanity bound only (CPU noise): a T4 decode step is about 16 ms.
    assert med["sptc_early"] - med["stock"] < 1000
