"""kaggle/overhead_bench.py without vLLM: the pure-policy benchmark runs for real, the vLLM
benchmark's plumbing runs on a stand-in for integrations/tests_vllm/_helpers.py (the real
thing is integrations/tests_vllm/test_overhead_bench.py, run on Kaggle)."""

from __future__ import annotations

import sys
import types

import overhead_bench as ob


def test_pure_policy_bench_runs():
    r = ob.pure_case(16, True, 20)
    assert r["policy"]["p50_us"] > 0 and r["n_waiting"] == 8


class _FakeSched:
    def __init__(self, max_num_seqs, **kw):
        self.max_num_seqs, self.running, self.waiting, self.calls = max_num_seqs, [], [], 0

    def add_request(self, r):
        self.waiting.append(r)

    def schedule(self):
        self.calls += 1
        while self.waiting and len(self.running) < self.max_num_seqs:
            self.running.append(self.waiting.pop(0))
        return object()

    def update_from_output(self, out, ro):
        return {}


def test_vllm_case_plumbing(monkeypatch):
    made = []

    def build(**kw):
        made.append(("stock", kw))
        return _FakeSched(**kw)

    def make_sched(sptc, **kw):
        made.append((sptc, kw))
        return _FakeSched(**kw)

    fake = types.ModuleType("_helpers")
    fake.build, fake.make_sched = build, make_sched
    fake.req = lambda rid, n, cls, max_tokens: (rid, cls)
    fake.runner_output = lambda s, out: None
    monkeypatch.setitem(sys.modules, "_helpers", fake)
    for variant in ob.VARIANTS:
        r = ob.vllm_case(300, variant, True, 7)
        assert r["n_running"] == 300 and r["n_waiting"] == 150 and r["steps"] == 7
        assert r["scheduling"] == "async" and r["schedule"]["p50_us"] >= 0
    assert made[0][0] == "stock" and made[2][0]["free_window"] == 10**6
    assert "| async | 300 | 150 | sptc-tagged |" in ob.table({"rows": [r]}, "vllm")
