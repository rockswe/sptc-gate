"""sptc_sglang against the real SGLang v0.5.22 package (needs `pip install sglang==0.5.22`
and `pip install -e integrations --no-deps`; run on the Kaggle GPU box):

  pytest -q tests_sglang

Checks the plugin wiring that the fake-based tests cannot: the entry point is discoverable,
register() + HookRegistry.apply_hooks() really replace the Scheduler and wrap the
retraction order, and the generated classes compose with SGLang's own. The end-to-end
behaviour is covered by kaggle/sptc_sglang_smoke.py.
"""

from __future__ import annotations

import importlib.metadata
import inspect
import os
from types import SimpleNamespace

import pytest

sglang = pytest.importorskip("sglang")


def _req(rid, cls=None):
    return SimpleNamespace(
        rid=rid, sampling_params=SimpleNamespace(custom_params={"sptc_class": cls} if cls else None)
    )


def test_version():
    assert sglang.__version__ == "0.5.22"


def test_entry_point_registered():
    eps = importlib.metadata.entry_points(group="sglang.srt.plugins")
    assert any(ep.name == "sptc" and ep.value == "sptc_sglang:register" for ep in eps)


def test_off_without_env(monkeypatch):
    from sglang.srt.plugins.hook_registry import HookRegistry

    from sptc_sglang import plugin

    monkeypatch.delenv("SPTC_SGLANG_CONFIG", raising=False)
    before = dict(HookRegistry._hooks)
    plugin.register()
    assert dict(HookRegistry._hooks) == before


def test_register_and_apply(monkeypatch):
    from sglang.srt.managers import schedule_batch, scheduler
    from sglang.srt.plugins.hook_registry import HookRegistry

    from sptc_sglang import plugin

    original = scheduler.Scheduler
    monkeypatch.setenv("SPTC_SGLANG_CONFIG", "{}")
    plugin.register()
    HookRegistry.apply_hooks()
    new = scheduler.Scheduler
    assert new.__name__ == "SptcScheduler" and issubclass(new, original)
    for name in ("get_prefill_adder_class", "_get_new_batch_prefill_raw",
                 "get_next_batch_to_run", "update_running_batch", "_add_request_to_queue"):
        assert name in new.__dict__, name
        assert (inspect.signature(getattr(new, name)).parameters.keys()
                == inspect.signature(getattr(original, name)).parameters.keys()), name

    plugin.register()  # idempotent: SptcScheduler is not wrapped again
    assert scheduler.Scheduler is new

    raw = schedule_batch.ScheduleBatch.__dict__["_get_decode_retraction_order"]
    assert isinstance(raw, staticmethod)
    assert hasattr(raw.__func__, "__wrapped__")  # HookRegistry's AROUND wrapper
    # The original reads get_schedule(), which needs a running server's context: give it
    # the defaults (audit #16: this check used to skip).
    monkeypatch.setattr(schedule_batch, "get_schedule", lambda: SimpleNamespace(
        retraction_policy="length", schedule_low_priority_values_first=False,
    ))
    reqs = [_req("n0"), _req("b0", "bet"), _req("e0", "early"), _req("b1", "bet")]
    for i, r in enumerate(reqs):  # what the original sort reads: keep more output first
        r.output_ids, r.origin_input_ids, r.priority = [0] * (10 - i), [0], None
    order = schedule_batch.ScheduleBatch._get_decode_retraction_order(reqs)
    assert [reqs[i].rid for i in order] == ["n0", "e0", "b0", "b1"]  # popped from the end



def test_adder_composes_with_prefill_adder():
    from sglang.srt.managers.schedule_policy import AddReqResult, PrefillAdder

    from sptc_sglang.core import make_adder_class

    cls = make_adder_class(PrefillAdder, AddReqResult)
    assert issubclass(cls, PrefillAdder)
    for name in ("add_one_req", "add_chunked_req"):
        assert (inspect.signature(getattr(cls, name)).parameters.keys()
                == inspect.signature(getattr(PrefillAdder, name)).parameters.keys()), name


def test_bad_config_raises_at_scheduler_start(monkeypatch):
    from sptc_sglang import plugin

    monkeypatch.setenv("SPTC_SGLANG_CONFIG", '{"free_windw": 4}')
    with pytest.raises(ValueError, match="unknown sptc knob"):
        plugin.load_config()
    monkeypatch.setenv("SPTC_SGLANG_CONFIG", "{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        plugin.load_config()
    monkeypatch.setenv("SPTC_SGLANG_CONFIG", '{"prefill_allowance": "sometimes"}')
    with pytest.raises(ValueError, match="prefill_allowance"):
        plugin.load_config()
    os.environ.pop("SPTC_SGLANG_CONFIG", None)


@pytest.mark.parametrize("mode", ["fixed", "adaptive", "off"])
def test_prefill_allowance_mode_from_env(monkeypatch, mode):
    from sptc_sglang import plugin

    monkeypatch.setenv("SPTC_SGLANG_CONFIG", f'{{"prefill_allowance": "{mode}"}}')
    cfg = plugin.load_config()
    assert cfg.prefill_allowance == mode
    assert cfg.allowance_budget == (0 if mode == "off" else 512)


def test_finish_abort_json():
    from types import SimpleNamespace as NS

    from sptc_sglang import plugin

    req = NS(return_logprob=False, finished_reason=None)
    plugin.make_finish_abort()(req, "sptc_bet_rejected", "free_window")
    fr = req.finished_reason.to_json()
    assert fr["type"] == "abort" and fr["matched"] == "sptc_bet_rejected"
    assert fr["status_code"] is None  # graceful: a normal response, not an HTTP error
    assert fr["message"] == "sptc_bet_rejected: free_window"
