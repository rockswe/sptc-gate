"""A small stand-in for vLLM v0.32.0's scheduler, so the sptc adapter's behaviour can be
tested on a machine without vLLM or torch (audit #15). Not a copy of vLLM: it keeps only
what the adapter touches, in the same order as the real `Scheduler.schedule()`.

Mirrored from vllm_src_v0.32.0/vllm/v1/core/sched/scheduler.py:
- running loop: async max_tokens skip, DP defer of prefill chunks, chunk size,
  `_reserve_prefill_lookahead` hook, allocation with FCFS preemption of `running[-1]`
  (`running.pop()` then `_preempt_request`), `continue` on 0 tokens;
- waiting loop (skipped in a step that preempted): `kv_holding_waiting` drained first and
  alone under PAUSED_NEW, `max_num_active_reqs` break, the blocked-request hook, the
  stale-output skip, an encoder-prefetch skip, a KV-connector lookup (async load:
  WAITING_FOR_REMOTE_KVS, then skipped), DP defer `break`, the lookahead hook (0: `break`),
  full-ISL allocation (`break` on failure), skipped requests prepended back, the DP
  capacity signal;
- `_update_after_schedule` (and the async variant's placeholders), `update_from_output`
  (in-flight and stale accounting, stop checks, grammar errors as FINISHED_ERROR, finished
  KV loads), `_preempt_request`, `finish_requests`, `_free_request`,
  `_handle_blocked_waiting_request`, `reset_prefix_cache`.
Left out: prefix caching, spec decode, encoders, LoRA, mamba, priority policy, PP cadence.

The real scheduler is tested on vLLM itself in `tests_vllm/` (Kaggle); these fakes only let
the adapter's own logic run locally. `load_adapter()` imports `sptc_vllm/scheduler.py`
against the fakes without leaving them in `sys.modules`.
"""

from __future__ import annotations

import enum
import importlib.util
import logging
import sys
import time
import types
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent  # integrations/
EOS = 2


# --------------------------------------------------------------------------- enums
class PauseState(enum.IntEnum):
    UNPAUSED = 0
    PAUSED_NEW = 1
    PAUSED_ALL = 2


class SchedulingPolicy(enum.Enum):
    FCFS = "fcfs"
    PRIORITY = "priority"


class FinishReason(enum.IntEnum):
    STOP = 0
    LENGTH = 1
    ABORT = 2
    ERROR = 3
    REPETITION = 4


class RequestStatus(enum.IntEnum):  # same members and order as vllm/v1/request.py
    WAITING = enum.auto()
    WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR = enum.auto()
    WAITING_FOR_REMOTE_KVS = enum.auto()
    WAITING_FOR_STREAMING_REQ = enum.auto()
    RUNNING = enum.auto()
    PREEMPTED = enum.auto()
    FINISHED_STOPPED = enum.auto()
    FINISHED_LENGTH_CAPPED = enum.auto()
    FINISHED_ABORTED = enum.auto()
    FINISHED_IGNORED = enum.auto()
    FINISHED_ERROR = enum.auto()
    FINISHED_REPETITION = enum.auto()

    @staticmethod
    def is_finished(status: RequestStatus) -> bool:
        return status > RequestStatus.PREEMPTED


_FINISH = {
    RequestStatus.FINISHED_STOPPED: FinishReason.STOP,
    RequestStatus.FINISHED_LENGTH_CAPPED: FinishReason.LENGTH,
    RequestStatus.FINISHED_ABORTED: FinishReason.ABORT,
    RequestStatus.FINISHED_IGNORED: FinishReason.LENGTH,
    RequestStatus.FINISHED_ERROR: FinishReason.ERROR,
    RequestStatus.FINISHED_REPETITION: FinishReason.REPETITION,
}


# --------------------------------------------------------------------------- engine I/O
@dataclass
class EngineCoreOutput:
    request_id: str
    new_token_ids: list[int]
    finish_reason: FinishReason | None = None
    stop_reason: int | str | None = None
    events: object = None
    trace_headers: object = None


@dataclass
class EngineCoreOutputs:
    outputs: list[EngineCoreOutput] = field(default_factory=list)


@dataclass
class SchedulerOutput:
    num_scheduled_tokens: dict[str, int]
    total_num_scheduled_tokens: int
    scheduled_new_reqs: list[str]
    scheduled_resumed_reqs: list[str]
    scheduled_running_reqs: list[str]
    preempted_req_ids: set[str]
    finished_req_ids: set[str]


# --------------------------------------------------------------------------- requests
class Request:
    def __init__(self, rid: str, n: int, cls: str | None = None, max_tokens: int = 16):
        extra = {"sptc_class": cls} if cls is not None else None
        self.request_id = rid
        self.sampling_params = SimpleNamespace(extra_args=extra, eos_token_id=EOS)
        self.resumable = False
        self.status = RequestStatus.WAITING
        self.num_prompt_tokens = n
        self.output_token_ids: list[int] = []
        self.max_tokens = max_tokens
        self.num_computed_tokens = 0
        self.num_output_placeholders = 0
        self.num_stale_output_tokens = 0
        self.drop_stale_output = False
        self.num_in_flight_tokens = 0
        self.is_prefill_chunk = False
        self.num_preemptions = 0
        self.structured_output_request = None
        self.client_index = 0
        self.trace_headers = None
        self.blocks = 0

    @property
    def num_tokens(self) -> int:
        return self.num_prompt_tokens + len(self.output_token_ids)

    def is_finished(self) -> bool:
        return RequestStatus.is_finished(self.status)

    def take_events(self):
        return None

    def get_finished_reason(self) -> FinishReason | None:
        return _FINISH.get(self.status)

    def __repr__(self) -> str:
        return f"Request({self.request_id}, {self.status.name})"


class FCFSRequestQueue(deque):
    def add_request(self, r):
        self.append(r)

    def pop_request(self):
        return self.popleft()

    def peek_request(self):
        return self[0]

    def prepend_request(self, r):
        self.appendleft(r)

    def prepend_requests(self, rs):
        self.extendleft(reversed(list(rs)))

    def remove_requests(self, rs):
        drop = {id(r) for r in rs}
        keep = [r for r in self if id(r) not in drop]
        self.clear()
        self.extend(keep)


# --------------------------------------------------------------------------- KV
class KVCacheManager:
    """Block counting only (no prefix cache). usage = used / usable blocks."""

    def __init__(self, num_blocks: int, block_size: int):
        self.total = num_blocks - 1  # block 0 is the null block, as in vLLM
        self.free_blocks = self.total
        self.block_size = block_size

    @property
    def usage(self) -> float:
        return 1.0 - self.free_blocks / self.total

    def blocks_for(self, tokens: int) -> int:
        return -(-tokens // self.block_size)

    def allocate(self, r: Request, upto: int) -> bool:
        need = self.blocks_for(upto) - r.blocks
        if need > self.free_blocks:
            return False
        if need > 0:
            self.free_blocks -= need
            r.blocks += need
        return True

    def free(self, r: Request) -> None:
        self.free_blocks += r.blocks
        r.blocks = 0


class FakeConnector:
    """get_num_new_matched_tokens(request, local) -> (tokens, load_async) from a dict."""

    def __init__(self, remote: dict[str, int] | None = None):
        self.remote = remote or {}

    def get_num_new_matched_tokens(self, r, local):
        n = self.remote.get(r.request_id, 0)
        return n, n > 0


# --------------------------------------------------------------------------- scheduler
class Scheduler:
    def __init__(
        self, *, vllm_config, kv_cache_config=None, block_size=16, log_stats=False,
        structured_output_manager=None, **_,
    ):
        self.vllm_config = vllm_config
        self.scheduler_config = vllm_config.scheduler_config
        sc = self.scheduler_config
        self.policy = SchedulingPolicy(sc.policy)
        self.max_num_running_reqs = sc.max_num_seqs
        self.max_num_active_reqs = sc.max_num_seqs
        self.max_num_scheduled_tokens = sc.max_num_batched_tokens
        self.kv_cache_manager = KVCacheManager(vllm_config.num_blocks, block_size)
        self.block_size = block_size
        self.connector = vllm_config.connector
        self.need_mamba_block_aligned_split = False
        self.num_prefill_lookahead = vllm_config.num_prefill_lookahead
        self.requests: dict[str, Request] = {}
        self.waiting = FCFSRequestQueue()
        self.kv_holding_waiting = FCFSRequestQueue()
        self.deferred_waiting: set[Request] = set()
        self.running: list[Request] = []
        self.finished_req_ids: set[str] = set()
        self.reset_preempted_req_ids: set[str] = set()
        self.finished_recving_kv_req_ids: set[str] = set()
        self.grammar_compile_error_reqs: set[str] = set()
        self._pause_state = PauseState.UNPAUSED
        self.num_waiting_for_streaming_input = 0  # no streaming sessions here
        self.prefill_capacity_bound = False
        self.ec_pending: set[str] = set()  # test knob: encoder prefetch still in flight

    # -- queues ------------------------------------------------------------------------
    @staticmethod
    def _holds_kv_blocks(r: Request) -> bool:
        return r.num_computed_tokens > 0 or r.status == RequestStatus.WAITING_FOR_REMOTE_KVS

    def add_request(self, r: Request) -> None:
        if r.status in (
            RequestStatus.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR,
            RequestStatus.WAITING_FOR_REMOTE_KVS,
            RequestStatus.WAITING_FOR_STREAMING_REQ,
        ):
            self.deferred_waiting.add(r)
        (self.kv_holding_waiting if self._holds_kv_blocks(r) else self.waiting).add_request(r)
        self.requests[r.request_id] = r

    def get_request_counts(self) -> tuple[int, int]:
        return len(self.running), len(self.waiting) + len(self.kv_holding_waiting)

    def has_requests(self) -> bool:
        return bool(self.running or self.waiting or self.kv_holding_waiting)

    def set_pause_state(self, s: PauseState) -> None:
        self._pause_state = s

    # -- hooks -------------------------------------------------------------------------
    def _reserve_prefill_lookahead(self, request, num_computed_tokens, num_new_tokens):
        remaining = request.num_tokens - num_computed_tokens - num_new_tokens
        if 0 < remaining < self.num_prefill_lookahead:
            num_new_tokens -= self.num_prefill_lookahead - remaining
        return max(num_new_tokens, 0)

    def _handle_blocked_waiting_request(self, request: Request) -> bool:
        if request.status == RequestStatus.WAITING_FOR_REMOTE_KVS:
            rid = request.request_id
            if rid not in self.finished_recving_kv_req_ids:
                return False
            if request.num_computed_tokens == request.num_tokens:
                request.num_computed_tokens = request.num_tokens - 1
            self.finished_recving_kv_req_ids.remove(rid)
            request.status = (
                RequestStatus.PREEMPTED if request.num_preemptions else RequestStatus.WAITING
            )
        elif request.status == RequestStatus.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR:
            so = request.structured_output_request
            if not so or so.grammar is None:
                return False
            if isinstance(so.grammar, Exception):
                self.grammar_compile_error_reqs.add(request.request_id)
                return False
            request.status = RequestStatus.WAITING
        elif request.status == RequestStatus.WAITING_FOR_STREAMING_REQ:
            return False
        return True

    def _ec_transfer_pending(self, request: Request, num_computed_tokens: int) -> bool:
        return request.request_id in self.ec_pending

    def _preempt_request(self, request, timestamp, drop_stale_output=False) -> None:
        assert request.status == RequestStatus.RUNNING
        self.kv_cache_manager.free(request)
        request.status = RequestStatus.PREEMPTED
        request.num_computed_tokens = 0
        request.drop_stale_output = drop_stale_output or (
            request.drop_stale_output and request.num_stale_output_tokens > 0
        )
        request.num_stale_output_tokens = request.num_in_flight_tokens
        request.num_output_placeholders = 0
        request.num_preemptions += 1
        self.waiting.prepend_request(request)
        self.reset_preempted_req_ids.add(request.request_id)

    # -- one step ----------------------------------------------------------------------
    def schedule(self, throttle_prefills: bool = False) -> SchedulerOutput:
        kv = self.kv_cache_manager
        token_budget = self.max_num_scheduled_tokens
        if self._pause_state == PauseState.PAUSED_ALL:
            token_budget = 0
        sched: dict[str, int] = {}
        new, resumed, running_ids, preempted = [], [], [], []
        ts = time.monotonic()
        defer_prefills = (throttle_prefills and not self.prefill_capacity_bound) and any(
            not r.is_prefill_chunk for r in self.running
        )

        req_index = 0
        while req_index < len(self.running) and token_budget > 0:
            request = self.running[req_index]
            if (
                request.num_output_placeholders > 0
                and request.num_computed_tokens + 2 - request.num_output_placeholders
                >= request.num_prompt_tokens + request.max_tokens
            ):
                req_index += 1
                continue
            if defer_prefills and request.is_prefill_chunk:
                req_index += 1
                continue
            n = request.num_tokens + request.num_output_placeholders - request.num_computed_tokens
            n = min(n, token_budget)
            n = self._reserve_prefill_lookahead(request, request.num_computed_tokens, n)
            if n == 0:
                req_index += 1
                continue
            while True:
                ok = kv.allocate(request, request.num_computed_tokens + n)
                if ok:
                    break
                victim = self.running.pop()
                self._preempt_request(victim, ts, drop_stale_output=False)
                preempted.append(victim)
                if victim is request:
                    break
            if not ok:
                break
            running_ids.append(request.request_id)
            sched[request.request_id] = n
            token_budget -= n
            req_index += 1

        if not preempted and self._pause_state != PauseState.PAUSED_ALL:
            skipped_waiting: deque = deque()
            skipped_kv: deque = deque()

            def skip_request(q):
                r = q.pop_request()
                self.deferred_waiting.add(r)
                (skipped_kv if self._holds_kv_blocks(r) else skipped_waiting).appendleft(r)

            while token_budget > 0:
                q = self.kv_holding_waiting
                if not q and self._pause_state == PauseState.UNPAUSED:
                    q = self.waiting
                if not q:
                    break
                num_running = len(self.running) + self.num_waiting_for_streaming_input
                if num_running >= self.max_num_active_reqs:
                    break
                request = q.peek_request()
                if not self._handle_blocked_waiting_request(request):
                    skip_request(q)
                    continue
                if request.num_stale_output_tokens and not request.drop_stale_output:
                    skip_request(q)
                    continue
                computed = request.num_computed_tokens
                ext, load_async = 0, False
                if computed == 0:
                    if self._ec_transfer_pending(request, computed):
                        skip_request(q)
                        continue
                    if self.connector is not None:
                        ext, load_async = self.connector.get_num_new_matched_tokens(request, 0)
                        if ext is None:
                            skip_request(q)
                            continue
                        computed = ext
                if load_async:
                    n = 0
                elif defer_prefills and computed < request.num_tokens - 1:
                    break
                else:
                    n = min(request.num_tokens - computed, token_budget)
                    n = self._reserve_prefill_lookahead(request, computed, n)
                    if n == 0:
                        break
                # full-ISL admission (scheduler_reserve_full_isl, vLLM's default)
                if not kv.allocate(request, max(request.num_tokens, computed + n)):
                    break
                if load_async:
                    request.status = RequestStatus.WAITING_FOR_REMOTE_KVS
                    request.num_computed_tokens = computed
                    skip_request(q)
                    continue
                q.pop_request()
                self.deferred_waiting.discard(request)
                self.running.append(request)
                if request.status == RequestStatus.WAITING:
                    new.append(request.request_id)
                elif request.status == RequestStatus.PREEMPTED:
                    resumed.append(request.request_id)
                else:
                    raise RuntimeError(f"Invalid request status: {request.status}")
                sched[request.request_id] = n
                token_budget -= n
                request.status = RequestStatus.RUNNING
                request.num_computed_tokens = computed
            if skipped_kv:
                self.kv_holding_waiting.prepend_requests(skipped_kv)
            if skipped_waiting:
                self.waiting.prepend_requests(skipped_waiting)
            if not defer_prefills:
                _, num_waiting = self.get_request_counts()
                self.prefill_capacity_bound = num_waiting > len(self.deferred_waiting)

        out = SchedulerOutput(
            num_scheduled_tokens=sched,
            total_num_scheduled_tokens=sum(sched.values()),
            scheduled_new_reqs=new,
            scheduled_resumed_reqs=resumed,
            scheduled_running_reqs=running_ids,
            preempted_req_ids=self.reset_preempted_req_ids,
            finished_req_ids=self.finished_req_ids,
        )
        self._update_after_schedule(out)
        return out

    def _update_after_schedule(self, out: SchedulerOutput) -> None:
        for rid, n in out.num_scheduled_tokens.items():
            r = self.requests[rid]
            r.num_computed_tokens += n
            r.num_in_flight_tokens += n
            r.is_prefill_chunk = r.num_computed_tokens < r.num_tokens + r.num_output_placeholders
        self.finished_req_ids = set()
        self.reset_preempted_req_ids = set()

    # -- results -----------------------------------------------------------------------
    def _update_request_with_output(self, request, token_ids, is_stale=False):
        stopped = False
        for k, t in enumerate(token_ids, 1):
            request.output_token_ids.append(t)
            if t == EOS:
                request.status = RequestStatus.FINISHED_STOPPED
                stopped = True
            elif len(request.output_token_ids) >= request.max_tokens:
                request.status = RequestStatus.FINISHED_LENGTH_CAPPED
                stopped = True
            if stopped:
                del token_ids[k:]
                break
        return token_ids, stopped

    def update_from_output(self, out: SchedulerOutput, sampled: dict) -> dict:
        """sampled: request id -> sampled token ids (empty for a partial prefill chunk);
        key "finished_recving" (optional): ids whose async KV load completed."""
        outputs: dict[int, list[EngineCoreOutput]] = {}
        stopped_running, stopped_preempted = [], []
        for rid, n in out.num_scheduled_tokens.items():
            request = self.requests.get(rid)
            stale = False
            if request is not None:
                request.num_in_flight_tokens -= n
                if request.num_stale_output_tokens > 0:
                    stale = True
                    request.num_stale_output_tokens -= n
            if request is None or request.is_finished():
                continue
            if stale and request.drop_stale_output:
                continue
            status_before = request.status
            tokens, stopped = list(sampled.get(rid, [])), False
            if tokens:
                tokens, stopped = self._update_request_with_output(request, tokens, stale)
            if tokens or stopped:
                reason = request.get_finished_reason() if stopped else None
                if stopped:
                    self._free_request(request)
                    (stopped_running if status_before == RequestStatus.RUNNING
                     else stopped_preempted).append(request)
                outputs.setdefault(request.client_index, []).append(
                    EngineCoreOutput(rid, tokens, reason)
                )
        if stopped_running:
            self.running = [r for r in self.running if r not in stopped_running]
        if stopped_preempted:
            self.waiting.remove_requests(stopped_preempted)
            self.kv_holding_waiting.remove_requests(stopped_preempted)
            self.deferred_waiting.difference_update(stopped_preempted)
        errors = set(self.grammar_compile_error_reqs)
        self.grammar_compile_error_reqs.clear()
        for r in self.finish_requests(errors, RequestStatus.FINISHED_ERROR):
            outputs.setdefault(r.client_index, []).append(
                EngineCoreOutput(r.request_id, [], r.get_finished_reason())
            )
        for rid in sampled.get("finished_recving", ()):
            if self.requests[rid].status == RequestStatus.WAITING_FOR_REMOTE_KVS:
                self.finished_recving_kv_req_ids.add(rid)
        return {c: EngineCoreOutputs(outputs=o) for c, o in outputs.items()}

    # -- finishing ---------------------------------------------------------------------
    def finish_requests(self, request_ids, finished_status) -> list[Request]:
        assert RequestStatus.is_finished(finished_status)
        ids = (request_ids,) if isinstance(request_ids, str) else list(request_ids)
        valid = []
        for rid in ids:
            r = self.requests.get(rid)
            if r is None or r.is_finished():
                continue
            valid.append(r)
            if r.status == RequestStatus.RUNNING:
                self.running = [x for x in self.running if x is not r]
            else:
                self.waiting.remove_requests([r])
                self.kv_holding_waiting.remove_requests([r])
                self.deferred_waiting.discard(r)
        for r in valid:
            self.finished_recving_kv_req_ids.discard(r.request_id)
            r.status = finished_status
            self._free_request(r)
        return valid

    def _free_request(self, request: Request) -> None:
        assert request.is_finished()
        self.finished_req_ids.add(request.request_id)
        self.kv_cache_manager.free(request)
        del self.requests[request.request_id]

    def reset_prefix_cache(self, reset_running_requests=False, reset_connector=False) -> bool:
        if reset_running_requests:
            ts = time.monotonic()
            while self.running:
                self._preempt_request(self.running.pop(), ts, drop_stale_output=True)
        return True


class AsyncScheduler(Scheduler):
    def _update_after_schedule(self, out: SchedulerOutput) -> None:
        super()._update_after_schedule(out)
        for rid in out.num_scheduled_tokens:
            r = self.requests[rid]
            if not r.is_prefill_chunk:
                r.num_output_placeholders += 1

    def _update_request_with_output(self, request, token_ids, is_stale=False):
        token_ids, stopped = super()._update_request_with_output(request, token_ids)
        if not is_stale:
            request.num_output_placeholders -= len(token_ids)
            assert request.num_output_placeholders >= 0
        return token_ids, stopped


# --------------------------------------------------------------------------- loading
_MODULES = {
    "vllm": {},
    "vllm.logger": {"init_logger": logging.getLogger},
    "vllm.v1": {},
    "vllm.v1.core": {},
    "vllm.v1.core.sched": {},
    "vllm.v1.core.sched.interface": {"PauseState": PauseState},
    "vllm.v1.core.sched.output": {"SchedulerOutput": SchedulerOutput},
    "vllm.v1.core.sched.request_queue": {
        "SchedulingPolicy": SchedulingPolicy, "FCFSRequestQueue": FCFSRequestQueue,
    },
    "vllm.v1.core.sched.scheduler": {"Scheduler": Scheduler},
    "vllm.v1.core.sched.async_scheduler": {"AsyncScheduler": AsyncScheduler},
    "vllm.v1.engine": {
        "EngineCoreOutput": EngineCoreOutput, "EngineCoreOutputs": EngineCoreOutputs,
        "FinishReason": FinishReason,
    },
    "vllm.v1.request": {"Request": Request, "RequestStatus": RequestStatus},
}


def load_adapter() -> types.ModuleType:
    """sptc_vllm/scheduler.py imported against the fakes, under a private module name.
    The fake `vllm` modules are removed from sys.modules again afterwards."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    saved = {name: sys.modules.get(name) for name in _MODULES}
    try:
        for name, attrs in _MODULES.items():
            m = types.ModuleType(name)
            m.__dict__.update(attrs)
            sys.modules[name] = m
        spec = importlib.util.spec_from_file_location(
            "_sptc_vllm_scheduler_on_fakes", ROOT / "sptc_vllm" / "scheduler.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


def config(
    sptc: dict | None = None, *, async_scheduling=False, max_num_seqs=16,
    max_num_batched_tokens=8192, num_blocks=10000, connector=None, num_prefill_lookahead=1,
    policy="fcfs",
):
    return SimpleNamespace(
        scheduler_config=SimpleNamespace(
            async_scheduling=async_scheduling, enable_chunked_prefill=True,
            max_num_seqs=max_num_seqs, max_num_batched_tokens=max_num_batched_tokens,
            policy=policy,
        ),
        additional_config={} if sptc is None else {"sptc": dict(sptc)},
        model_config=SimpleNamespace(supports_multimodal_inputs=False),
        num_blocks=num_blocks,
        connector=connector,
        num_prefill_lookahead=num_prefill_lookahead,
    )
