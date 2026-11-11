"""Static guard against SGLang API drift: parses the downloaded SGLang v0.5.22 sources with
`ast` (no SGLang import, no install) and checks every name, signature and control-flow
assumption sptc_sglang relies on. Skipped if the sources are missing. Point
SPTC_SGLANG_SRC at another checkout (its python/ dir) to re-check a different version."""

import ast
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent  # integrations/
# default: a sglang_src_v0.5.22/ checkout next to the sptc-sim repo
SRC = Path(
    os.environ.get("SPTC_SGLANG_SRC", ROOT.parent.parent / "sglang_src_v0.5.22" / "python")
)
SRT = SRC / "sglang" / "srt"
SCHED = SRT / "managers" / "scheduler.py"

pytestmark = pytest.mark.skipif(not SCHED.exists(), reason=f"SGLang sources not at {SRC}")


def _tree(rel: str) -> ast.Module:
    return ast.parse((SRT / rel).read_text())


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def _methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _func(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


def _args(fn: ast.FunctionDef) -> list[str]:
    return [a.arg for a in fn.args.posonlyargs + fn.args.args]


def _src(fn: ast.AST) -> str:
    return ast.unparse(fn)


def _has(src: str, snippet: str) -> bool:
    """Substring test that ignores whitespace (ast.unparse indents by nesting depth)."""
    return "".join(snippet.split()) in "".join(src.split())


def _self_attrs(cls: ast.ClassDef) -> set[str]:
    """Attributes assigned as self.x anywhere in the class (incl. tuple targets)."""
    out: set[str] = set()
    for node in ast.walk(cls):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for t in targets:
            for x in ast.walk(t):
                if (
                    isinstance(x, ast.Attribute)
                    and isinstance(x.value, ast.Name)
                    and x.value.id == "self"
                ):
                    out.add(x.attr)
    return out


@pytest.fixture(scope="module")
def sched():
    return _class(_tree("managers/scheduler.py"), "Scheduler")


@pytest.fixture(scope="module")
def adder():
    return _class(_tree("managers/schedule_policy.py"), "PrefillAdder")


# --------------------------------------------------------------------------- plugin loading
def test_plugin_group_and_hook_types():
    t = _tree("plugins/__init__.py")
    assert 'GENERAL_PLUGINS_GROUP = "sglang.srt.plugins"' in ast.unparse(t).replace("'", '"')
    hooks = _class(_tree("plugins/hook_registry.py"), "HookType")
    names = {t.id for n in hooks.body if isinstance(n, ast.Assign) for t in n.targets}
    assert {"REPLACE", "AROUND"} <= names
    reg = _methods(_class(_tree("plugins/hook_registry.py"), "HookRegistry"))
    assert "register" in reg and "apply_hooks" in reg


def test_scheduler_process_loads_plugins_before_building_the_scheduler():
    fn = _func(_tree("managers/scheduler.py"), "run_scheduler_process")
    src = _src(fn)
    assert "load_plugins()" in src and "Scheduler(" in src
    assert src.index("load_plugins()") < src.index("Scheduler(")


def test_make_abort_req(sched):
    fn = _func(_tree("managers/scheduler.py"), "_make_abort_req")
    assert _args(fn) == ["req", "finished_reason"]


# --------------------------------------------------------------------------- scheduler
def test_scheduler_method_signatures(sched):
    m = _methods(sched)
    assert _args(m["get_prefill_adder_class"]) == ["self"]
    assert _args(m["_get_new_batch_prefill_raw"]) == [
        "self", "prefill_delayer_single_pass", "running_batch",
    ]
    assert _args(m["get_next_batch_to_run"]) == ["self", "running_batch", "last_batch"]
    assert _args(m["_add_request_to_queue"]) == ["self", "req", "is_retracted"]
    assert _args(m["_release_aborted_request"]) == ["self", "req"]
    assert _args(m["update_running_batch"]) == ["self", "batch"]
    assert _args(m["process_pending_chunked_abort"]) == ["self"]
    assert _args(m["_reqs_finishing_inflight"]) == ["self", "batch"]


def test_scheduler_attributes(sched):
    attrs = _self_attrs(sched)
    need = {
        "waiting_queue", "chunked_req", "chunked_prefill_size", "is_mixed_chunk", "page_size",
        "enable_priority_scheduling", "schedule_policy", "disaggregation_mode",
        "require_mlp_sync", "tree_cache", "is_hybrid_swa", "pool_stats_observer",
        "max_total_num_tokens", "beam_coordinator", "ipc_channels", "enable_hisparse",
        "dllm_config", "_prefill_decode_interval_remaining", "truncation_align_size",
        "_pending_chunked_abort_req",
    }
    assert need <= attrs, need - attrs


def test_prefill_loop_shape(sched):
    """The loop the adder hooks into: built via get_prefill_adder_class(), continuation
    first, waiting requests in queue order, stops on anything but CONTINUE, and the waiting
    queue is rebuilt from self.waiting_queue (so the reorder before it is what runs)."""
    src = _src(_methods(sched)["_get_new_batch_prefill_raw"])
    assert "adder = self.get_prefill_adder_class()(" in src
    assert "self.chunked_req = adder.add_chunked_req(self.chunked_req)" in src
    assert "for req in self.waiting_queue:" in src
    assert "res = adder.add_one_req(req, has_chunked_req=" in src
    assert "truncation_align_size=" in src
    assert "if res != AddReqResult.CONTINUE:" in src
    assert "self.waiting_queue = [x for x in self.waiting_queue if x not in can_run_set]" in src
    assert "new_batch.prepare_for_extend()" in src  # KV allocated before we return
    i_calc = src.index("self.policy.calc_priority(")
    assert i_calc < src.index("for req in self.waiting_queue:")


def test_mixed_step_marks_decoding_reqs(sched):
    """core.py tells a mixed step from a prefill-only one by new_batch.decoding_reqs."""
    src = _src(_methods(sched)["_get_new_batch_prefill_raw"])
    assert "new_batch.decoding_reqs = running_batch.reqs" in src
    assert "new_batch.decoding_reqs = None" in src
    assert "not (new_batch.return_logprob or running_batch.return_logprob)" in src


def test_fcfs_without_priority_does_not_reorder():
    fn = _methods(_class(_tree("managers/schedule_policy.py"), "SchedulePolicy"))["calc_priority"]
    src = _src(fn)
    assert _has(src, "if self.policy == CacheAgnosticPolicy.FCFS: if self.enable_priority_scheduling:")


def test_prefill_defer_counter(sched):
    m = _methods(sched)
    assert "_prefill_decode_interval_remaining" in _src(m["_should_defer_prefill"])
    src = _src(m["get_next_batch_to_run"])
    assert "elif self._should_defer_prefill():" in src
    assert src.index("_should_defer_prefill") < src.index("self.get_new_batch_prefill(")
    assert "return NextBatchPlan(batch_to_run=ret, running_batch=running_batch)" in src


def test_retracted_requests_requeued_through_add_request_to_queue(sched):
    src = _src(_methods(sched)["update_running_batch"])
    assert "batch.retract_decode()" in src
    assert "self._add_request_to_queue(req, is_retracted=True)" in src


def test_chunked_bet_drop_path(sched):
    """core.py drops a chunked bet before a decode step that would retract: the same test
    update_running_batch uses, then SGLang's chunked-request abort with the bet's reason."""
    m = _methods(sched)
    src = _src(m["update_running_batch"])
    i_fin = src.index("finishing_reqs = self._reqs_finishing_inflight(batch)")
    i_mem = src.index("kv_full_retract_flag = not batch.check_decode_mem()")
    assert i_fin < i_mem < src.index("batch.retract_decode()")
    assert _has(src, "if kv_full_retract_flag and finishing_reqs: batch.batch_is_full = False return None")
    abort = _src(m["process_pending_chunked_abort"])
    for snippet in (
        "req = self._pending_chunked_abort_req",
        "reason = req.discard_output_reason or FINISH_ABORT('Aborted')",
        "prepare_abort(req, reason.message, reason.status_code)",
        "release_kv_cache(req, self.tree_cache, checkpoint=False)",
        "self.chunked_req = None",
        "finished_reason = req.discard_output_reason and reason.to_json()",
    ):
        assert snippet in abort, snippet
    nxt = _src(m["get_next_batch_to_run"])
    assert "decode_batch = self.update_running_batch(running_batch)" in nxt
    batch = _methods(_class(_tree("managers/schedule_batch.py"), "ScheduleBatch"))
    assert _args(batch["check_decode_mem"]) == ["self", "selected_indices"]


def test_chunked_early_retract_path(sched):
    """core.py retracts a chunked early request as pause_generation(mode="retract") does
    with the chunked request (plugin.make_retract: retract_all, then chunked_req = None and
    a requeue); a retracted request's in-flight chunk result is skipped (overlap)."""
    fn = _func(_tree("managers/schedule_batch.py"), "retract_all")
    assert [a.arg for a in fn.args.kwonlyargs] == [
        "reqs", "req_to_token_pool", "token_to_kv_pool_allocator", "tree_cache",
        "hisparse_coordinator", "offload_kv",
    ]
    assert {"req_to_token_pool", "token_to_kv_pool_allocator", "hisparse_coordinator"} <= (
        _self_attrs(sched)
    )
    pause = _src(_methods(sched)["pause_generation"])
    assert "retract_reqs.append(self.chunked_req)" in pause and "self.chunked_req = None" in pause
    fn = next(
        n for n in ast.walk(_tree("managers/scheduler_components/batch_result_processor.py"))
        if isinstance(n, ast.FunctionDef) and n.name == "process_batch_result_prefill"
    )
    assert _has(_src(fn), "if req.finished() and req.inflight_middle_chunks <= 0 or req.is_retracted: continue")


def test_pause_retract_requeues_without_the_flag(sched):
    """core.py recognises a bet requeued by pause_generation(mode="retract") by
    req.is_retracted, which Req.reset_for_retract sets and prepare_for_extend clears."""
    src = _src(_methods(sched)["pause_generation"])
    assert "retract_all(" in src and "self._add_request_to_queue(req)" in src
    batch = _tree("managers/schedule_batch.py")
    reset = _src(_methods(_class(batch, "Req"))["reset_for_retract"])
    assert "self.is_retracted = True" in reset
    extend = _src(_methods(_class(batch, "ScheduleBatch"))["prepare_for_extend"])
    assert "req.is_retracted = False" in extend


def test_waiting_queue_abort_steps(sched):
    """_sptc_abort mirrors abort_request's 'abort method 1' for queued requests."""
    src = _src(_methods(sched)["abort_request"])
    for call in (
        "self._release_aborted_request(req)",
        "self.beam_coordinator.retire_group(req)",
        "self.ipc_channels.send_to_tokenizer.send_output(_make_abort_req(req, "
        "finished_reason=recv_req.finished_reason), req)",
    ):
        assert call in src, call


def test_pool_stats():
    t = _tree("managers/scheduler_components/pool_stats_observer.py")
    stats = _class(t, "PoolStats")
    fields = {n.target.id for n in stats.body if isinstance(n, ast.AnnAssign)}
    assert {"full_capacity", "full_token_usage"} <= fields
    assert "get_max_pool_usage" in _methods(stats)
    assert "get_pool_stats" in _methods(_class(t, "SchedulerPoolStatsObserver"))


# --------------------------------------------------------------------------- adder
def test_adder_api(adder):
    m = _methods(adder)
    assert _args(m["add_one_req"]) == ["self", "req", "has_chunked_req", "truncation_align_size"]
    assert _args(m["add_chunked_req"]) == ["self", "req"]
    assert _args(m["budget_state"]) == ["self"]
    assert {"rem_chunk_tokens", "chunked_req_limit", "can_run_list", "running_batch",
            "new_chunked_req"} <= _self_attrs(adder)
    t = _tree("managers/schedule_policy.py")
    res = _class(t, "AddReqResult")
    assert {"CONTINUE", "NO_TOKEN", "OTHER"} <= {
        x.id for n in res.body if isinstance(n, ast.Assign) for x in n.targets
    }


def test_adder_uses_rem_chunk_tokens_and_chunked_req_limit(adder):
    m = _methods(adder)
    assert "self.chunked_req_limit" in _src(m["add_chunked_req"])
    assert "chunk_limit=self.rem_chunk_tokens" in _src(m["_check_prefill_budget"])
    assert "self.rem_chunk_tokens -= compute_charge" in _src(m["_update_prefill_budget"])
    assert "self.rem_chunk_tokens <= 0" in _src(m["budget_state"])
    commit = _src(m["_commit_prefill_admission"])
    assert "self.new_chunked_req = req" in commit and "req.extend_end =" in commit
    assert "return self.budget_state()" in _src(m["add_one_req"])


def test_alignment_applies_only_to_chunks(adder):
    """core.py admits a tagged request that fits the cap whole and rounds the budget up to
    the alignment, because SGLang aligns a request only when it has to chunk it."""
    src = _src(_methods(adder)["_select_prefill_admission"])
    i_chunk = src.index("elif chunk_tokens_limit is not None and chunk_fit_tokens > chunk_tokens_limit:")
    i_align = src.index("extend_len = extend_len // truncation_align_size * truncation_align_size")
    assert i_chunk < i_align
    assert src.count("truncation_align_size * truncation_align_size") == 2  # both chunk paths


def test_one_chunked_request_invariant(sched):
    src = _src(_methods(sched)["_get_new_batch_prefill_raw"])
    assert "assert self.chunked_req is None" in src  # why core.py closes the step


# --------------------------------------------------------------------------- retraction
def test_retraction_order_hook_target():
    batch = _class(_tree("managers/schedule_batch.py"), "ScheduleBatch")
    m = _methods(batch)
    fn = m["_get_decode_retraction_order"]
    assert any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in fn.decorator_list)
    assert _args(fn) == ["reqs"]
    src = _src(m["retract_decode"])
    assert "sorted_indices = self._get_decode_retraction_order(self.reqs)" in src
    assert "idx = sorted_indices.pop()" in src  # retracted from the end


# --------------------------------------------------------------------------- client side
def test_custom_params_reach_sampling_params():
    t = _tree("entrypoints/openai/protocol.py")
    chat = _class(t, "ChatCompletionRequest")
    fields = {n.target.id for n in chat.body if isinstance(n, ast.AnnAssign)}
    assert "custom_params" in fields
    assert "'custom_params': self.custom_params" in _src(chat)
    comp = _class(t, "CompletionRequest")
    assert "custom_params" in {n.target.id for n in comp.body if isinstance(n, ast.AnnAssign)}
    sp = _class(_tree("sampling/sampling_params.py"), "SamplingParams")
    fields = {n.target.id for n in sp.body if isinstance(n, ast.AnnAssign)}
    init = _methods(sp).get("__init__")
    assert "custom_params" in (fields | set(_args(init) if init else []))


def test_graceful_abort_reaches_the_client():
    """finished_reason passes through the tokenizer unchanged; without a status_code it is
    not turned into an HTTP error; the chat API maps "matched" to matched_stop."""
    tm = _class(_tree("managers/tokenizer_manager.py"), "TokenizerManager")
    m = _methods(tm)
    src = _src(m["_handle_abort_req"])
    assert _has(src, "if recv_obj.finished_reason: finish_reason = recv_obj.finished_reason")
    src = _src(_methods(tm)["_handle_abort_finish_reason"])
    assert "status_code = finish_reason.get('status_code')" in src
    assert "return None" in src
    chat = _tree("entrypoints/openai/serving_chat.py")
    src = ast.unparse(chat)
    assert "matched_stop = finish_reason_data.get('matched')" in src
    assert "finish_reason['matched'] if finish_reason and 'matched' in finish_reason" in src
    fr = _tree("managers/io_struct.py")
    assert "FinishReasonDict = Dict[str, Optional[Union[str, int, List[int]]]]" in ast.unparse(fr)


def test_finish_through_the_output_path(sched):
    """_sptc_abort follows _reject_sampling_mask_request: prepare_abort, then stream_output;
    the streamer skips a finished request it already output (overlap's second visit)."""
    m = _methods(sched)
    src = _src(m["_reject_sampling_mask_request"])
    assert "prepare_abort(req, error_msg" in src
    assert "self.output_streamer.stream_output([req], req.return_logprob)" in src
    assert "output_streamer" in _self_attrs(sched) and "enable_lora" in _self_attrs(sched)
    fn = _func(_tree("disaggregation/utils.py"), "prepare_abort")
    assert _args(fn) == ["req", "error_message", "status_code"]
    assert "req.finished_reason = FINISH_ABORT(error_message, status_code)" in _src(fn)
    streamer = _src(_tree("managers/scheduler_components/output_streamer.py"))
    assert _has(streamer, "if req.finished() and req.finished_output: continue")
    assert "req.finished_reason.to_json()" in streamer
    abort = _class(_tree("managers/schedule_batch.py"), "FINISH_ABORT")
    assert _args(_methods(abort)["__init__"]) == ["self", "message", "status_code", "err_type"]
