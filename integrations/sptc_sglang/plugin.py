"""SGLang v0.5.22 glue: an SGLang general plugin (entry point group "sglang.srt.plugins").

SGLang calls register() early in every process, including the scheduler process, before the
Scheduler is built. It registers two hooks with SGLang's HookRegistry:
- class REPLACE of sglang.srt.managers.scheduler.Scheduler by a subclass (core.py);
- AROUND on ScheduleBatch._get_decode_retraction_order, so bets are retracted first.

The plugin is off unless SPTC_SGLANG_CONFIG is set (a JSON object, "{}" for the defaults):
installing the package must not change other SGLang servers in the same environment. The
config is parsed when the scheduler starts, so a bad knob stops the server instead of being
swallowed by SGLang's plugin loader, which only logs exceptions raised in register().
"""

from __future__ import annotations

import json
import logging
import os

from sptc_vllm.policy import SptcConfig

from .core import CONFIG_ENV, abort_reason, make_scheduler_class, retraction_order

logger = logging.getLogger("sptc_sglang")

SGLANG_VERSION = "0.5.22"
SCHEDULER = "sglang.srt.managers.scheduler.Scheduler"
RETRACTION_ORDER = "sglang.srt.managers.schedule_batch.ScheduleBatch._get_decode_retraction_order"


def load_config() -> SptcConfig:
    raw = os.environ.get(CONFIG_ENV, "{}")
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as e:
        raise ValueError(f"{CONFIG_ENV} is not valid JSON: {e}") from None
    return SptcConfig.from_mapping(data)


def checks(s) -> tuple[list[str], list[str]]:
    """(unsupported modes, reasons to switch the prefill allowance off) for a Scheduler."""
    from sglang.srt.runtime_context import get_parallel

    fatal, no_allowance = [], []
    if s.enable_priority_scheduling:
        fatal.append("--enable-priority-scheduling")
    if s.schedule_policy != "fcfs":
        fatal.append(f"--schedule-policy {s.schedule_policy} (only fcfs)")
    if getattr(s.disaggregation_mode, "value", s.disaggregation_mode) != "null":
        fatal.append("PD disaggregation")
    if get_parallel().pp_size > 1:
        fatal.append("pipeline parallelism")
    if s.require_mlp_sync:
        fatal.append("DP attention")
    if getattr(s, "dllm_config", None) is not None:
        fatal.append("diffusion LLMs")
    if getattr(s, "enable_hisparse", False):
        fatal.append("HiSparse")
    if getattr(s, "enable_lora", False):
        # SGLang adds a skipped request's adapter to the step's running set anyway
        fatal.append("LoRA")
    if s.tree_cache.supports_mamba():
        # A skipped request would keep the mamba slot init_next_round_input gave it.
        fatal.append("hybrid SSM (mamba) models")
    if s.chunked_prefill_size is None:
        no_allowance.append("chunked prefill is off")
    if s.is_hybrid_swa:
        no_allowance.append("hybrid SWA model")
    return fatal, no_allowance


def make_finish_reason():
    """SptcFinishAbort(stop, detail): SGLang's FINISH_ABORT whose JSON carries matched=stop
    and no status_code, so the OpenAI layer reports finish_reason "abort", matched_stop=stop,
    instead of an HTTP error."""
    from sglang.srt.managers.schedule_batch import FINISH_ABORT

    class SptcFinishAbort(FINISH_ABORT):
        def __init__(self, stop: str, detail: str):
            fr = abort_reason(stop, detail)
            super().__init__(fr["message"])
            self.matched = fr["matched"]

        def to_json(self):
            return {**super().to_json(), "matched": self.matched}

    return SptcFinishAbort


def make_finish_abort(finish_reason=None):
    """finish_abort(req, stop, detail) for core.py: SGLang's prepare_abort (clears input
    logprobs), then finished_reason = finish_reason(stop, detail)."""
    from sglang.srt.disaggregation.utils import prepare_abort

    reason = finish_reason or make_finish_reason()

    def finish_abort(req, stop: str, detail: str) -> None:
        prepare_abort(req, abort_reason(stop, detail)["message"])
        req.finished_reason = reason(stop, detail)

    return finish_abort


def make_retract():
    """retract(scheduler, req) for core.py: SGLang's retract_all for one request, as
    pause_generation(mode="retract") does for the chunked request: frees its KV and resets
    it (Req.reset_for_retract) so a later prefill starts over."""
    from sglang.srt.managers.schedule_batch import retract_all

    def retract(s, req) -> None:
        retract_all(
            reqs=[req],
            req_to_token_pool=s.req_to_token_pool,
            token_to_kv_pool_allocator=s.token_to_kv_pool_allocator,
            tree_cache=s.tree_cache,
            hisparse_coordinator=s.hisparse_coordinator,
            offload_kv=False,
        )

    return retract


def register() -> None:
    if CONFIG_ENV not in os.environ:
        logger.debug("sptc_sglang installed but off (%s not set)", CONFIG_ENV)
        return

    import sglang
    from sglang.srt.managers import scheduler as sched_mod
    from sglang.srt.managers.schedule_policy import AddReqResult
    from sglang.srt.plugins.hook_registry import HookRegistry, HookType

    version = getattr(sglang, "__version__", "?")
    if version != SGLANG_VERSION:
        logger.warning("sptc_sglang targets SGLang %s, found %s", SGLANG_VERSION, version)
    if getattr(sched_mod.Scheduler, "__name__", "") == "SptcScheduler":
        return  # already registered in this process

    reason = make_finish_reason()
    cls = make_scheduler_class(
        sched_mod.Scheduler,
        AddReqResult=AddReqResult,
        finish_abort=make_finish_abort(reason),
        finish_reason=reason,
        retract=make_retract(),
        cfg_loader=load_config,
        checks=checks,
    )
    cls.__module__ = __name__
    HookRegistry.register(SCHEDULER, cls, HookType.REPLACE)
    HookRegistry.register(RETRACTION_ORDER, retraction_order, HookType.AROUND)
