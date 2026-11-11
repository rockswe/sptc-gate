"""Helpers for the vLLM-dependent sptc tests. Needs `pip install vllm==0.32.0` (the scheduler
is driven directly, no model is executed). Test modules call pytest.importorskip("vllm")
before importing this module, so a machine without vLLM skips them cleanly.

The factory mirrors tests/v1/core/utils.py::create_scheduler of vLLM v0.32.0 (same configs,
watermark=0 for deterministic admission, FullAttentionSpec, log_stats=True) so no vLLM test
checkout is needed. The model config of facebook/opt-125m is fetched from the HF hub (config
only); override with SPTC_TEST_MODEL.
"""

from __future__ import annotations

import os
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # integrations/

import torch  # noqa: E402
from vllm.config import CacheConfig, ModelConfig, SchedulerConfig, VllmConfig  # noqa: E402
from vllm.sampling_params import SamplingParams  # noqa: E402
from vllm.utils.hashing import sha256  # noqa: E402
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash  # noqa: E402
from vllm.v1.core.sched.async_scheduler import AsyncScheduler  # noqa: E402
from vllm.v1.core.sched.scheduler import Scheduler  # noqa: E402
from vllm.v1.core.single_type_kv_cache_manager import register_all_kvcache_specs  # noqa: E402
from vllm.v1.kv_cache_interface import (  # noqa: E402
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
)
from vllm.v1.outputs import ModelRunnerOutput  # noqa: E402
from vllm.v1.request import Request  # noqa: E402
from vllm.v1.structured_output import StructuredOutputManager  # noqa: E402

from sptc_vllm.scheduler import SptcScheduler  # noqa: E402

MODEL = os.environ.get("SPTC_TEST_MODEL", "facebook/opt-125m")
EOS_TOKEN_ID = 50256
BLOCK = 16
TOKEN = 7  # every sampled token (never EOS)

_none_hash_ready = False


def build(
    scheduler_cls=None,
    *,
    sptc: dict | None = None,
    async_scheduling: bool = False,
    max_num_seqs: int = 16,
    max_num_batched_tokens: int = 8192,
    num_blocks: int = 10000,
    block_size: int = BLOCK,
    enable_chunked_prefill: bool = True,
    enable_prefix_caching: bool = False,
    long_prefill_token_threshold: int = 0,
    scheduling_policy: str = "fcfs",
    use_v2_model_runner: bool = False,
):
    """A scheduler under test. scheduler_cls None: vanilla (Async)Scheduler, the reference."""
    model_config = ModelConfig(
        model=MODEL, trust_remote_code=True, dtype="float16", seed=42, max_model_len=None
    )
    scheduler_config = SchedulerConfig(
        max_num_seqs=max_num_seqs,
        max_num_batched_tokens=max_num_batched_tokens,
        max_model_len=max_num_batched_tokens,
        long_prefill_token_threshold=long_prefill_token_threshold,
        enable_chunked_prefill=enable_chunked_prefill,
        async_scheduling=async_scheduling,
        is_encoder_decoder=model_config.is_encoder_decoder,
        watermark=0.0,
        policy=scheduling_policy,
    )
    cache_config = CacheConfig(
        block_size=block_size,
        gpu_memory_utilization=0.9,
        cache_dtype="auto",
        enable_prefix_caching=enable_prefix_caching,
    )
    vllm_config = VllmConfig(
        scheduler_config=scheduler_config, model_config=model_config, cache_config=cache_config
    )
    if sptc is not None:
        # additional_config defaults to a fresh dict: mutate it, never reassign
        vllm_config.additional_config["sptc"] = dict(sptc)
    spec = FullAttentionSpec(
        block_size=block_size, num_kv_heads=1, head_size=1, dtype=torch.float32
    )
    kv_cache_config = KVCacheConfig(
        num_blocks=num_blocks,
        kv_cache_tensors=[],
        kv_cache_groups=[KVCacheGroupSpec(["layer"], spec)],
    )
    cache_config.num_gpu_blocks = num_blocks
    register_all_kvcache_specs(vllm_config)
    if scheduler_cls is None:
        scheduler_cls = AsyncScheduler if async_scheduling else Scheduler
    s = scheduler_cls(
        vllm_config=vllm_config,
        kv_cache_config=kv_cache_config,
        block_size=block_size,
        log_stats=True,
        structured_output_manager=StructuredOutputManager(vllm_config),
    )
    s.use_v2_model_runner = use_v2_model_runner  # as vLLM's helper does
    return s


def make_sched(sptc: dict | None = None, **kw):
    """The sptc scheduler (SptcScheduler auto-selects the async variant)."""
    return build(SptcScheduler, sptc=sptc if sptc is not None else {}, **kw)


def req(rid: str, n: int, cls: str | None = None, max_tokens: int = 16, seed: int = 0,
        block_size: int = BLOCK, prompt: list[int] | None = None) -> Request:
    """n prompt tokens, distinct per (rid, seed); or exactly `prompt` (n is then ignored),
    e.g. to share a prefix between requests."""
    global _none_hash_ready
    if not _none_hash_ready:
        init_none_hash(sha256)
        _none_hash_ready = True
    sp = SamplingParams(
        max_tokens=max_tokens,
        extra_args={"sptc_class": cls} if cls is not None else None,
    )
    sp.update_from_generation_config({}, EOS_TOKEN_ID)
    base = 1 + zlib.crc32(f"{rid}|{seed}".encode()) % 20000  # distinct prompts
    return Request(
        request_id=rid,
        prompt_token_ids=list(prompt) if prompt is not None
        else [(base + k) % 30000 + 1 for k in range(n)],
        sampling_params=sp,
        pooling_params=None,
        block_hasher=get_request_block_hasher(block_size, sha256),
    )


def runner_output(s, out, token: int = TOKEN) -> ModelRunnerOutput:
    """What the model runner returns for `out`: one token for every scheduled request that
    finished its prefill, none for partial prefill chunks. Requests the scheduler already
    dropped (no longer in s.requests) still get a token, as an in-flight step would."""
    ids = list(out.num_scheduled_tokens)
    sampled = [
        [] if (i in s.requests and s.requests[i].is_prefill_chunk) else [token] for i in ids
    ]
    return ModelRunnerOutput(
        req_ids=ids,
        req_id_to_index={r: k for k, r in enumerate(ids)},
        sampled_token_ids=sampled,
        logprobs=None,
        prompt_logprobs_dict={},
        pooler_output=[],
    )


def step(s, out):
    return s.update_from_output(out, runner_output(s, out))


def client_outs(outs, rid=None):
    return [o for eco in outs.values() for o in eco.outputs if rid is None or o.request_id == rid]


def new_ids(out) -> list[str]:
    return [r.req_id for r in out.scheduled_new_reqs]
