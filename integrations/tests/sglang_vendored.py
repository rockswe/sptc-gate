"""SGLang v0.5.22's scheduling path, run locally from the vendored sources: no SGLang
install, no torch, no GPU, no model.

The methods the plugin wraps or relies on are the real ones. Their source is read from
sglang_src_v0.5.22/ and compiled with `ast`, method by method:
- Scheduler: get_next_batch_to_run, get_new_batch_prefill, _get_new_batch_prefill_raw,
  update_running_batch, pause_generation, process_pending_chunked_abort,
  _add_request_to_queue and the helpers they call;
- PrefillAdder (the whole class) and PrefillBudget;
- ScheduleBatch.retract_decode, _get_decode_retraction_order, check_decode_mem,
  new_tokens_required_next_decode; FINISH_ABORT.

Only the objects around them are stand-ins: requests, a batch object, a paged KV pool, a
radix cache that never matches a prefix, and a driver that plays the model's forward pass
(one output token per decode, KV allocated as SGLang's prepare_for_extend/decode would).
SGLang globals that need the server's runtime context (get_schedule, get_parallel, ...)
are replaced by fixed values for a single-GPU, FCFS, non-disaggregated server.

tests/test_sglang_vendored.py runs the plugin on top of this and checks, step by step,
that untagged traffic is scheduled exactly as by the stock path.
"""

from __future__ import annotations

import __future__
import ast
import enum
import functools
import logging
import os
import sys
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from enum import Enum, auto
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent  # integrations/
SRC = Path(
    os.environ.get("SPTC_SGLANG_SRC", ROOT.parent.parent / "sglang_src_v0.5.22" / "python")
)
SRT = SRC / "sglang" / "srt"
AVAILABLE = (SRT / "managers" / "scheduler.py").exists()

logger = logging.getLogger("sglang_vendored")
_FLAGS = __future__.annotations.compiler_flag


# --------------------------------------------------------------------------- source loading
@functools.lru_cache(maxsize=None)
def _tree(rel: str) -> ast.Module:
    return ast.parse((SRT / rel).read_text())


def _find(tree: ast.Module, cls: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            return node
    raise AssertionError(f"class {cls} not found")


def _compile_class(
    rel: str, cls: str, ns: dict, only: tuple[str, ...] | None = None, *, bases: bool = False
) -> type:
    """Class `cls` of SRT/rel compiled into namespace ns. bases: keep its base classes (they
    must be in ns), else none. only: keep just these methods. Line numbers are kept, so
    tracebacks point into the vendored file."""
    node = _find(_tree(rel), cls)
    body = node.body
    if only is not None:
        body = [n for n in body if isinstance(n, ast.FunctionDef) and n.name in only]
        missing = set(only) - {n.name for n in body}
        assert not missing, f"{cls}: {missing} not in {rel}"
    kw = {"type_params": []} if sys.version_info >= (3, 12) else {}
    new = ast.ClassDef(
        name=cls, bases=node.bases if bases else [], keywords=[], body=body, decorator_list=[],
        **kw,
    )
    mod = ast.fix_missing_locations(ast.Module(body=[new], type_ignores=[]))
    exec(compile(mod, str(SRT / rel), "exec", flags=_FLAGS, dont_inherit=True), ns)
    return ns[cls]


# --------------------------------------------------------------------------- stand-ins
class _Nothing:
    """Any attribute, any call: does nothing (time_stats, trace contexts)."""

    def __getattr__(self, name):
        return self

    def __call__(self, *a, **k):
        return None


class DisaggregationMode(Enum):
    NULL = "null"
    PREFILL = "prefill"
    DECODE = "decode"


SCHEDULE = NS(
    schedule_policy="fcfs", retraction_policy="length", prefill_max_requests=None,
    schedule_low_priority_values_first=False, disable_priority_preemption=False,
    chunked_prefill_size=None,
)
PARALLEL = NS(pp_size=1, pp_max_micro_batch_size=1 << 30, attn_dp_size=1, tp_rank=0)
EXEC = NS(features=NS(enable_encoder_swa_bounded_replay=False))
DISAGG = NS(disaggregation_mode="null", disaggregation_decode_retraction_backup=None)


class Pool:
    """Paged token-to-KV pool plus the request-slot pool. Tokens are allocated in whole
    pages; a request's pages are freed when it finishes, is retracted or is aborted."""

    def __init__(self, size: int, page_size: int, slots: int):
        self.page_size = page_size
        self.pages = size // page_size
        self.used = 0
        self.slots = slots
        self.slot_holders: set[str] = set()
        self.shard_spec = None
        self.slot_reserve = 0  # request_slot_reserve(); > 0 can park a chunked request

    @property
    def size(self) -> int:
        return self.pages * self.page_size

    def available_size(self) -> int:
        return (self.pages - self.used) * self.page_size

    def create_prefill_budget(self, tree_cache, num_mixed_decode_tokens=0):
        return NS_BUDGET["PrefillBudget"](
            self, tree_cache, num_mixed_decode_tokens=num_mixed_decode_tokens
        )

    def request_slot_reserve(self, *, has_req_pool_slot, prefill_tokens):
        return 0 if has_req_pool_slot else self.slot_reserve

    def check_decode_capacity(self, *, num_tokens, tree_cache, requests=None, spec_algorithm=None):
        return self.available_size() >= num_tokens

    def alloc_to(self, req, tokens: int) -> None:
        """Grow req's KV to cover `tokens` tokens."""
        need = -(-tokens // self.page_size) - req.kv.pages
        if need > 0:
            if self.used + need > self.pages:
                raise MemoryError(f"KV pool overrun by {req.rid}")  # SGLang's budgets failed
            self.used += need
            req.kv.pages += need
        req.kv.kv_allocated_len = req.kv.pages * self.page_size
        if req.rid not in self.slot_holders:
            assert len(self.slot_holders) < self.slots, "request slots overrun"
            self.slot_holders.add(req.rid)
            req.kv.req_pool_idx = len(self.slot_holders)

    def free(self, req) -> None:
        self.used -= req.kv.pages
        req.kv.pages = 0
        req.kv.kv_allocated_len = req.kv.kv_committed_len = 0
        self.slot_holders.discard(req.rid)
        req.kv.req_pool_idx = None


class Tree:
    """A radix cache that never matches and holds nothing evictable."""

    disable = True
    buffer_pipeline = None
    storage_prefetch_retries = None

    def __init__(self, pool: Pool):
        self.token_to_kv_pool_allocator = pool
        self.req_to_token_pool = NS()

    def evictable_size(self):
        return 0

    full_evictable_size = evictable_size

    def supports_mamba(self):
        return False

    def supports_prefix_sharing(self):
        return False

    def lock(self, node):
        return None

    def unlock(self, lock):
        return None

    def finish(self, handle, outcome):
        return None

    def discard_storage_prefetch_accounting(self, handle):
        return None

    def finish_storage_prefetch_admission(self, handle, **kw):
        return None


class Req:
    """The Req fields the scheduling path reads. prompt: prompt tokens; max_new: output
    tokens until FINISH_LENGTH; cls: the sptc tag ("bet", "early") or None."""

    def __init__(self, rid, prompt=100, max_new=16, cls=None, *, logprob=False):
        self.rid = rid
        self.origin_input_ids = [7] * prompt
        self.output_ids: list[int] = []
        self.full_untruncated_fill_ids = list(self.origin_input_ids)
        self.sampling_params = NS(
            max_new_tokens=max_new, ignore_eos=False,
            custom_params={"sptc_class": cls} if cls else None,
        )
        self.prefix_len = 0
        self.extend_end = 0
        self.kv = NS(
            pages=0, kv_allocated_len=0, kv_committed_len=0, req_pool_idx=None,
            holds_mamba=False, mamba_pool_idx=None, mamba_cow_src_index=None,
            mamba_needs_clear=False, cache_protected_len=0, cache_inserted_len=0,
        )
        self.last_node = None
        self.host_hit_length = self.swa_host_hit_length = self.host_loaded_length = 0
        self.storage_hit_length = self.storage_hit_start = 0
        self.host_hit_is_storage = False
        self.retracted_stain = self.is_retracted = False
        self.retraction_count = 0
        self.finished_reason = None
        self.to_finish = None
        self.discard_output_reason = None
        self.return_logprob = logprob
        self.logprob_start_len = -1
        self.token_indices_to_pool = None
        self.beam_group = None
        self.inflight_middle_chunks = 0
        self.priority = None
        self.session = None
        self.lora_id = None
        self.cache_request_handle = None
        self.skip_radix_cache_insert = False
        self.time_stats = _Nothing()

    @property
    def extend_len(self) -> int:
        return self.extend_end - self.prefix_len

    def finished(self) -> bool:
        return self.finished_reason is not None

    def next_output_finishes_by_length(self) -> bool:
        return len(self.output_ids) + 1 >= self.sampling_params.max_new_tokens

    def needs_host_load_back(self) -> bool:
        return False

    def materialized_host_hit_len(self) -> int:
        return 0

    def fulfilled_storage_hit_len(self, prefix_len) -> int:
        return 0

    def release_mm_inputs_on_abort(self) -> None:
        return None

    def init_next_round_input(self, tree_cache=None, cow_mamba=None) -> None:
        # refresh_fill_ids; no prefix match: prefix_len keeps the computed (stashed) part
        self.full_untruncated_fill_ids = self.origin_input_ids + self.output_ids

    def reset_for_retract(self) -> None:  # schedule_batch.py Req.reset_for_retract
        self.retraction_count += 1
        self.prefix_len = 0
        self.last_node = None
        self.extend_end = None
        self.is_retracted = True
        self.retracted_stain = True
        self.inflight_middle_chunks = 0

    def __repr__(self) -> str:
        return self.rid


class ForwardMode(enum.IntEnum):
    EXTEND = auto()
    DECODE = auto()
    MIXED = auto()

    def is_extend(self, include_draft_extend_v2: bool = False) -> bool:
        return self in (ForwardMode.EXTEND, ForwardMode.MIXED)


NS_BUDGET: dict = {}


# --------------------------------------------------------------------------- world
class World:
    """One scheduler process: a Scheduler class (stock, or a subclass from `wrap`) over the
    real methods, its batch class and the real PrefillAdder, plus a driver."""

    SCHED_METHODS = (
        "get_next_batch_to_run", "get_new_batch_prefill", "_get_new_batch_prefill_raw",
        "update_running_batch", "_should_defer_prefill", "_arm_prefill_decode_interval",
        "get_num_allocatable_reqs", "process_pending_chunked_abort", "_add_request_to_queue",
        "_set_or_validate_priority", "_abort_on_queued_limit", "_release_aborted_request",
        "pause_generation", "stash_chunked_request", "_reqs_finishing_inflight",
        "get_prefill_adder_class",
    )
    BATCH_METHODS = (
        "retract_decode", "_get_decode_retraction_order", "check_decode_mem",
        "new_tokens_required_next_decode", "release_req",
    )

    def __init__(self, retraction_hook=None):
        assert AVAILABLE, f"SGLang sources not at {SRC}"
        base: dict[str, Any] = {
            "__name__": __name__, "logger": logger, "HTTPStatus": HTTPStatus,
            "Optional": Optional, "List": List, "Dict": Dict, "Set": Set, "Tuple": Tuple,
            "Union": Union, "Any": Any, "Enum": Enum, "auto": auto, "dataclass": dataclass,
            "contextmanager": contextmanager, "nullcontext": nullcontext, "sys": sys,
            "time": time, "get_schedule": lambda: SCHEDULE, "get_parallel": lambda: PARALLEL,
            "get_exec": lambda: EXEC, "get_disagg": lambda: DISAGG, "envs": _Nothing(),
            "DisaggregationMode": DisaggregationMode,
        }
        # schedule_batch.py: FINISH_ABORT and the retraction loop
        self.ns_batch = dict(base)
        _compile_class("managers/schedule_batch.py", "BaseFinishReason", self.ns_batch)
        _compile_class("managers/schedule_batch.py", "FINISH_ABORT", self.ns_batch, bases=True)
        self.FINISH_ABORT = self.ns_batch["FINISH_ABORT"]
        world = self

        def release_req(*, req, remaing_req_count, req_to_token_pool,
                        token_to_kv_pool_allocator, tree_cache, hisparse_coordinator,
                        offload_kv=True):
            token_to_kv_pool_allocator.free(req)
            req.reset_for_retract()
            return True

        self.ns_batch.update(
            beam_retraction_order=lambda idx, reqs: idx, num_beam_member_rows=lambda r: 0,
            free_member_rows=lambda *a: None, release_req=release_req,
            # the ratio stays at its configured value, so pressure (and retraction) recurs
            NewTokenRatioTracker=NS(
                estimate_new_token_ratio_after_retract=lambda reqs: self.new_token_ratio
            ),
        )
        Real = _compile_class(
            "managers/schedule_batch.py", "ScheduleBatch", self.ns_batch, self.BATCH_METHODS
        )

        class Batch(Real):
            def __init__(self, reqs=None, batch_is_full=False):
                self.reqs = list(reqs or [])
                self.batch_is_full = batch_is_full
                self.forward_mode = ForwardMode.DECODE
                self.chunked_req = None
                self.is_prefill_only = False
                self.input_embeds = None
                self.decoding_reqs = None
                self.contains_last_prefill_chunk = True
                self.hisparse_coordinator = None
                self.prefill_stats = None
                self.token_to_kv_pool_allocator = world.pool
                self.req_to_token_pool = None
                self.tree_cache = world.tree
                self.spec_algorithm = NS(is_none=lambda: True, is_some=lambda: False)

            @classmethod
            def init_new(cls, reqs, req_to_token_pool, token_to_kv_pool_allocator, tree_cache,
                         model_config, enable_overlap, spec_algorithm, chunked_req=None):
                b = cls(reqs)
                b.forward_mode = ForwardMode.EXTEND
                b.chunked_req = chunked_req
                return b

            @property
            def return_logprob(self):
                return any(r.return_logprob for r in self.reqs)

            def is_empty(self):
                return len(self.reqs) == 0

            def batch_size(self):
                return len(self.reqs)

            def filter_batch(self, reqs_to_exclude=None, keep_indices=None):
                if keep_indices is None:
                    if isinstance(reqs_to_exclude, Req):
                        reqs_to_exclude = [reqs_to_exclude]
                    elif reqs_to_exclude is None:
                        reqs_to_exclude = []
                    keep_indices = [
                        i for i in range(len(self.reqs))
                        if not self.reqs[i].finished() and self.reqs[i] not in reqs_to_exclude
                    ]
                self.reqs = [self.reqs[i] for i in keep_indices]

            def merge_batch(self, other):
                self.reqs.extend(other.reqs)

            def prepare_for_extend(self):
                for r in self.reqs:
                    world.pool.alloc_to(r, r.extend_end)
                    r.is_retracted = False

            def prepare_for_decode(self):
                self.forward_mode = ForwardMode.DECODE
                for r in self.reqs:
                    world.pool.alloc_to(r, r.kv.kv_committed_len + 1)

            def mix_with_running(self, running_batch):
                self.forward_mode = ForwardMode.MIXED
                self.reqs.extend(running_batch.reqs)

        if retraction_hook is not None:  # HookRegistry AROUND on a staticmethod
            orig = Real.__dict__["_get_decode_retraction_order"].__func__

            @functools.wraps(orig)
            def wrapped(*args, **kwargs):
                return retraction_hook(orig, *args, **kwargs)

            wrapped.__wrapped__ = orig
            Real._get_decode_retraction_order = staticmethod(wrapped)
        self.Batch = Batch

        # schedule_policy.py: the whole PrefillAdder; prefill_budget.py: PrefillBudget
        self.ns_policy = dict(base)
        self.ns_policy.update(
            CLIP_MAX_NEW_TOKENS=4096, _IS_HIP=False, PREFILL_TILE_BUDGET=0,
            PREFILL_TILE_BUDGET_MODE="compact", _use_exact_chunk_fill=lambda: False,
            page_interleave_shard_size=lambda alloc: 1,
            _ceil_div=lambda v, d: -(-v // d),
            split_cached_prefix_by_tier=lambda **kw: (kw["prefix_len"], 0, 0),
            **{n: type(n, (), {}) for n in (
                "SWATokenToKVPoolAllocator", "DeepSeekV4HiSparseTokenToKVPoolAllocator",
                "UnifiedMambaTokenToKVPoolAllocator", "UnifiedMambaSWATokenToKVPoolAllocator",
                "UnifiedRadixCache",
            )},
        )
        _compile_class("managers/schedule_policy.py", "AddReqResult", self.ns_policy, bases=True)
        _compile_class("managers/schedule_policy.py", "_PrefillAdmission", self.ns_policy)
        self.ns_policy["_PrefillAdmission"] = dataclass(frozen=True, slots=True)(
            self.ns_policy["_PrefillAdmission"]
        )
        self.PrefillAdder = _compile_class(
            "managers/schedule_policy.py", "PrefillAdder", self.ns_policy
        )
        self.AddReqResult = self.ns_policy["AddReqResult"]
        _compile_class("mem_cache/prefill_budget.py", "PrefillBudget", NS_BUDGET)

        # scheduler.py
        self.outputs: list[tuple[str, Any]] = []  # (rid, finished_reason json) to the client
        self.retracted = 0  # requests retracted by update_running_batch (KV pressure)

        def prepare_abort(req, error_message, status_code=None):  # disaggregation/utils.py
            req.finished_reason = self.FINISH_ABORT(error_message, status_code)

        def release_kv_cache(req, tree_cache, checkpoint=False):
            self.pool.free(req)

        def checkpoint_kv_cache(req, tree_cache):  # mem_cache/common.py
            assert not req.finished(), f"checkpointing finished request {req.rid}"
            req.prefix_len = req.extend_end

        def retract_all(*, reqs, req_to_token_pool, token_to_kv_pool_allocator, tree_cache,
                        hisparse_coordinator, offload_kv=True):
            for r in reqs:
                release_req(req=r, remaing_req_count=0, req_to_token_pool=None,
                            token_to_kv_pool_allocator=self.pool, tree_cache=None,
                            hisparse_coordinator=None)

        class NextBatchPlan:
            def __init__(self, batch_to_run, running_batch):
                self.batch_to_run = batch_to_run
                self.running_batch = running_batch

        self.ns_sched = dict(base)
        self.ns_sched.update(
            AddReqResult=self.AddReqResult, ScheduleBatch=Batch, NextBatchPlan=NextBatchPlan,
            FINISH_ABORT=self.FINISH_ABORT, prepare_abort=prepare_abort,
            release_kv_cache=release_kv_cache, checkpoint_kv_cache=checkpoint_kv_cache,
            retract_all=retract_all, TEST_RETRACT=False, TEST_RETRACT_NO_PREFILL_BS=0,
            TEST_RETRACT_INTERVAL=1, set_time_batch=lambda *a: None,
            set_schedule_time_batch=lambda b: None, PrefillStats=NS(from_adder=lambda *a, **k: None),
            CacheRequestOutcome=NS(ABORT="abort"), PrefillAdder=self.PrefillAdder,
            _make_abort_req=lambda req, finished_reason=None: NS(
                rid=req.rid, finished_reason=finished_reason
            ),
            AbortReq=lambda **kw: NS(**kw),
            scheduler_stage_method=lambda stage: (lambda fn: fn),  # profiling decorator
            SCHEDULER_STAGE_GET_NEXT_BATCH=None,
        )
        self.Scheduler = _compile_class(
            "managers/scheduler.py", "Scheduler", self.ns_sched, self.SCHED_METHODS
        )
        self.pool: Pool = None  # set by build()
        self.tree: Tree = None

    # ---- a scheduler instance
    def build(self, cls=None, *, kv=20_000, page=1, chunk=256, max_prefill=16384, slots=64,
              align=None, mixed=False, new_token_ratio=0.05, **attrs):
        """A scheduler of class cls (default: the stock one) with its own KV pool."""
        cls = cls or self.Scheduler
        world = self
        self.new_token_ratio = new_token_ratio
        self.pool = pool = Pool(kv, page, slots)
        self.tree = tree = Tree(pool)

        def init(s):
            s.page_size = page
            s.chunked_prefill_size = chunk
            s.max_prefill_tokens = max_prefill
            s.max_running_requests = slots
            s.is_mixed_chunk = mixed
            s.truncation_align_size = align
            s.waiting_queue = []
            s.running_batch = world.Batch(reqs=[], batch_is_full=False)
            s.last_batch = None
            s.chunked_req = None
            s._pending_chunked_abort_req = None
            s.token_to_kv_pool_allocator = pool
            s.tree_cache = tree
            s.req_to_token_pool = NS(available_size=lambda: pool.slots - len(pool.slot_holders))
            s.max_total_num_tokens = pool.size
            s.new_token_ratio_tracker = NS(current=new_token_ratio, decay_step=lambda: None)
            s.policy = NS(calc_priority=lambda *a, **k: None,
                          shortest_prefill_chunk_limit=lambda *a: None)
            s.late = []  # grammar-ready requests appended at the start of the next pass
            s.grammar_manager = NS(
                has_waiting_grammars=lambda: bool(s.late),
                get_ready_grammar_requests=lambda: [s.late.pop(0) for _ in list(s.late)],
            )
            for name in (
                "dllm_config", "min_free_slots_delayer", "dynamic_chunk_sizer", "prefill_delayer",
                "decode_offload_manager", "hisparse_coordinator", "model_config", "result_queue",
                "max_queued_requests", "cur_batch_for_debug",
            ):
                setattr(s, name, None)
            for name in (
                "enable_hisparse", "enable_fpm", "enable_priority_preemption", "is_hybrid_swa",
                "enable_lora", "enable_hicache_storage", "enable_lmcache",
                "enable_hierarchical_cache", "enable_unified_cache_external_linker",
                "enable_overlap", "require_mlp_sync", "enable_skip_finishing_decode",
                "enable_priority_scheduling", "abort_on_priority_when_disabled",
                "_engine_paused", "enable_overlap_mlx",
            ):
                setattr(s, name, False)
            s.disaggregation_mode = DisaggregationMode.NULL
            s.schedule_policy = "fcfs"
            s.priority_scheduling_preemption_threshold = 0
            s.max_prefill_bs = 0
            s.processed_tokens_counter = 0
            s.forward_ct = 0
            s.prefill_decode_interval = 0
            s._prefill_decode_interval_remaining = 0
            s.tp_worker = NS(model_runner=NS(attn_backend=NS(), prefill_aware_swa=False))
            s.spec_algorithm = NS(is_none=lambda: True, is_some=lambda: False)
            s.load_inquirer = NS(_get_num_pending_tokens=lambda **kw: 0)
            s.dp_attn_adapter = NS(
                maybe_prepare_mlp_sync_batch=lambda b, need_sync=False: b,
                maybe_convert_decode_to_extend=lambda b: b,
            )
            s.ngram_embedding_manager = NS(prepare_for_forward=lambda b, chunked_req=None: b)
            s.metrics_reporter = NS(
                num_retracted_reqs=0, enable_metrics=False, last_gen_throughput=0.0,
                current_scheduler_metrics_enabled=False,
            )
            s.kv_events_publisher = NS(publish_kv_events=lambda: None)
            s.beam_coordinator = NS(retire_group=lambda req: None,
                                    pending_member_rows=lambda b: 0)
            s.ipc_channels = NS(send_to_tokenizer=NS(
                send_output=lambda out, req: world.outputs.append((out.rid, out.finished_reason))
            ))
            s.output_streamer = NS(stream_output=lambda reqs, lp: world.outputs.extend(
                (r.rid, r.finished_reason.to_json()) for r in reqs if r.finished()
            ))
            s.pool_stats_observer = NS(get_pool_stats=lambda: NS(
                full_capacity=pool.size,
                get_max_pool_usage=lambda: (pool.size - pool.available_size()) / pool.size,
            ))
            s._process_hicache_events = lambda: None
            s._prefetch_kvcache = lambda req: None
            for k, v in attrs.items():
                setattr(s, k, v)

        s = cls.__new__(cls)
        init(s)
        if cls is not self.Scheduler:
            s.__init__()  # the plugin's __init__: super().__init__() is object's, then setup
        return s

    # ---- the event loop (event_loop_normal) and the model
    def step(self, s):
        """One scheduler iteration. Returns None (nothing ran) or (forward mode, per request:
        (rid, prefix_len, extend_end) for a prefill, rid for a decode)."""
        plan = s.get_next_batch_to_run(running_batch=s.running_batch, last_batch=s.last_batch)
        s.running_batch = plan.running_batch
        batch = plan.batch_to_run
        out = None
        if batch:
            decoding = set(map(id, batch.decoding_reqs or ()))
            out = (batch.forward_mode.name, [
                r.rid if batch.forward_mode == ForwardMode.DECODE or id(r) in decoding
                else (r.rid, r.prefix_len, r.extend_end)
                for r in batch.reqs
            ])
            self.forward(s, batch)
        s.last_batch = batch
        s.forward_ct += 1
        self.retracted += s.metrics_reporter.num_retracted_reqs  # set by update_running_batch
        s.metrics_reporter.num_retracted_reqs = 0
        return out

    def forward(self, s, batch):
        decoding = set(map(id, batch.decoding_reqs or ()))
        for r in batch.reqs:
            if batch.forward_mode == ForwardMode.DECODE or id(r) in decoding:
                r.kv.kv_committed_len += 1
                self._token(r)
                continue
            r.kv.kv_committed_len = r.extend_end
            if r.inflight_middle_chunks > 0:  # a middle chunk: no token yet
                r.inflight_middle_chunks -= 1
                continue
            if r.finished():
                continue
            if r.to_finish is not None:  # SGLang finishes it after one cheap prefill
                r.finished_reason, r.to_finish = r.to_finish, None
                self._done(r)
                continue
            self._token(r)

    def _token(self, r):
        if r.finished():
            return
        r.output_ids.append(1)
        if r.to_finish is not None:
            r.finished_reason, r.to_finish = r.to_finish, None
        elif len(r.output_ids) >= r.sampling_params.max_new_tokens:
            r.finished_reason = NS(to_json=lambda: {"type": "length"})
        if r.finished():
            self._done(r)

    def _done(self, r):
        self.pool.free(r)
        self.outputs.append((r.rid, r.finished_reason.to_json()))


@contextmanager
def fake_sglang_modules(world: World):
    """Just enough of the sglang package for plugin.make_finish_abort(), make_retract() and checks()
    to import, so the plugin's own code runs here. Removed again on exit."""

    def prepare_abort(req, error_message, status_code=None):
        req.finished_reason = world.FINISH_ABORT(error_message, status_code)

    mods = {
        "sglang": NS(__path__=[]), "sglang.srt": NS(__path__=[]),
        "sglang.srt.disaggregation": NS(__path__=[]),
        "sglang.srt.disaggregation.utils": NS(prepare_abort=prepare_abort),
        "sglang.srt.managers": NS(__path__=[]),
        "sglang.srt.managers.schedule_batch": NS(
            FINISH_ABORT=world.FINISH_ABORT, retract_all=world.ns_sched["retract_all"]
        ),
        "sglang.srt.runtime_context": NS(get_parallel=lambda: PARALLEL),
    }
    with mock.patch.dict(sys.modules, mods):
        yield
