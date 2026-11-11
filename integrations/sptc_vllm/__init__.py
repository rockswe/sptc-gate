"""sptc scheduler plugin for vLLM v0.32.0 (speculation-aware 'agent' policy).

Importing this package does not import vLLM; the adapter lives in sptc_vllm.scheduler and
is loaded by vLLM via --scheduler-cls sptc_vllm.scheduler.SptcScheduler.
"""

from sptc_vllm.policy import (
    CLASS_KEY,
    STOP_REASON_DROPPED,
    STOP_REASON_REJECTED,
    SptcClass,
    SptcConfig,
)

__all__ = ["CLASS_KEY", "STOP_REASON_DROPPED", "STOP_REASON_REJECTED", "SptcClass", "SptcConfig"]
