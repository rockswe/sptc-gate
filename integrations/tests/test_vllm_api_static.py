"""Static guard against vLLM API drift: parses sptc_vllm/scheduler.py and the downloaded
vLLM v0.32.0 sources with `ast` (no vLLM import, no install). Skipped if the sources are
missing. Point SPTC_VLLM_SRC at another checkout to re-check a different vLLM version."""

import ast
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent  # integrations/
ADAPTER = ROOT / "sptc_vllm" / "scheduler.py"
# default: a vllm_src_v0.32.0/ checkout next to the sptc-sim repo
SRC = Path(os.environ.get("SPTC_VLLM_SRC", ROOT.parent.parent / "vllm_src_v0.32.0"))
SCHED = SRC / "vllm/v1/core/sched/scheduler.py"

pytestmark = pytest.mark.skipif(not SCHED.exists(), reason=f"vLLM sources not at {SRC}")


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def _methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}


def _top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split(".")[0] for a in node.names}
    return names


def _module_file(mod: str) -> Path | None:
    base = SRC / Path(*mod.split("."))
    for cand in (base.with_suffix(".py"), base / "__init__.py"):
        if cand.exists():
            return cand
    return None


def _sig(fn: ast.FunctionDef) -> tuple[list[str], list[str]]:
    args = [a.arg for a in fn.args.posonlyargs + fn.args.args]
    defaults = [ast.unparse(d) for d in fn.args.defaults]
    return args, defaults


ADAPTER_TREE = _tree(ADAPTER)


def test_vllm_imports_resolve():
    """(i) every `from vllm... import X` names a top-level definition of that module."""
    checked = 0
    for node in ADAPTER_TREE.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("vllm"):
            f = _module_file(node.module)
            if f is None:
                assert node.module == "vllm.logger", f"{node.module} not downloaded"
                continue  # vllm/logger.py is not part of the downloaded subset
            names = _top_level_names(_tree(f))
            for a in node.names:
                assert a.name in names, f"{a.name} not defined in {node.module}"
                checked += 1
    assert checked >= 8


def _is_property(fn: ast.FunctionDef) -> bool:
    return any(
        ast.unparse(d) == "property" or ast.unparse(d).endswith(".setter")
        for d in fn.decorator_list
    )


def test_overridden_methods_match_base_signatures():
    """(ii) overrides exist on Scheduler with identical positional names and defaults."""
    base = _methods(_class(_tree(SCHED), "Scheduler"))
    ours = _methods(_class(ADAPTER_TREE, "SptcScheduler"))
    overridden = [
        n
        for n, fn in ours.items()
        if not n.startswith("_sptc") and n not in ("__init__", "__new__") and not _is_property(fn)
    ]
    assert set(overridden) == {
        "add_request",
        "schedule",
        "_handle_blocked_waiting_request",
        "_reserve_prefill_lookahead",
        "_preempt_request",
        "update_from_output",
    }
    for name in overridden:
        assert name in base, f"Scheduler.{name} no longer exists"
        assert _sig(ours[name]) == _sig(base[name]), (name, _sig(ours[name]), _sig(base[name]))


def test_shadowed_attribute_is_a_plain_base_attribute():
    """prefill_capacity_bound is shadowed by a property (to see when schedule() sets it). It
    must be a plain instance attribute of Scheduler, assigned in __init__ and in schedule()
    with the expression _sptc_end_step repeats."""
    cls = _class(_tree(SCHED), "Scheduler")
    props = {n for n, fn in _methods(_class(ADAPTER_TREE, "SptcScheduler")).items()
             if _is_property(fn)}
    assert props == {"prefill_capacity_bound"}
    assert "prefill_capacity_bound" not in _methods(cls)
    init_src = ast.unparse(_methods(cls)["__init__"])
    sched_src = ast.unparse(_methods(cls)["schedule"])
    assert "self.prefill_capacity_bound = False" in init_src
    assert (
        "self.prefill_capacity_bound = num_waiting > len(self.deferred_waiting)" in sched_src
    )
    assert "_, num_waiting = self.get_request_counts()" in sched_src


def test_base_hooks_are_called_where_the_design_assumes():
    """The hooks must be called inside schedule() (and _preempt_request also from
    reset_prefix_cache only), otherwise the policy silently stops applying."""
    sched = _methods(_class(_tree(SCHED), "Scheduler"))

    def calls(fn: ast.FunctionDef) -> list[str]:
        return [
            n.func.attr
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "self"
        ]

    in_schedule = calls(sched["schedule"])
    assert in_schedule.count("_reserve_prefill_lookahead") == 2  # running + waiting loop
    assert in_schedule.count("_handle_blocked_waiting_request") == 1
    assert in_schedule.count("_preempt_request") == 1
    callers = {n for n, fn in sched.items() if "_preempt_request" in calls(fn)}
    assert callers == {"schedule", "reset_prefix_cache"}, callers
    # the FCFS victim is running[-1], popped with self.running.pop()
    src = ast.unparse(sched["schedule"])
    assert "preempted_req = self.running[-1]" in src
    assert "preempted_req = self.running.pop()" in src
    assert "finished_req_ids=self.finished_req_ids" in src
    # the stale-output shortcut in the hook relies on vLLM skipping such requests right after
    hook = src.index("ready_to_schedule = self._handle_blocked_waiting_request(request)")
    stale = src.index("if request.num_stale_output_tokens and (not request.drop_stale_output)")
    assert hook < stale
    # policy.finishes_in_flight mirrors the running loop's async max_tokens skip
    assert (
        "request.num_output_placeholders > 0 and request.num_computed_tokens + 2 - "
        "request.num_output_placeholders >= request.num_prompt_tokens + request.max_tokens"
    ) in src
    # the KV reserve of a held bet is re-read through kv_cache_manager.usage
    assert "self.kv_cache_manager.new_step_starts()" in src
    # _sptc_begin_step repeats vLLM's DP defer test (audit #5): same inputs, read before
    # schedule() changes them
    assert (
        "defer_prefills = (throttle_prefills and (not self.prefill_capacity_bound)) and "
        "any((not r.is_prefill_chunk for r in self.running))"
    ) in src
    # an async KV load is started after the hook passed the bet (audit #1): the status is
    # set in the waiting loop only, after the hook call
    load = src.index("request.status = RequestStatus.WAITING_FOR_REMOTE_KVS")
    assert hook < load and src.count("RequestStatus.WAITING_FOR_REMOTE_KVS") == 1
    # a grammar that failed to compile is finished as FINISHED_ERROR by vLLM (audit #3)
    upd = ast.unparse(sched["update_from_output"])
    assert "error_req_ids = set(self.grammar_compile_error_reqs)" in upd
    assert "self.finish_requests(error_req_ids, RequestStatus.FINISHED_ERROR)" in upd


def test_base_attributes_exist():
    """(iii) every self.<name> read from the base is assigned in Scheduler.__init__ or is a
    method/property of Scheduler."""
    cls = _class(_tree(SCHED), "Scheduler")
    init = _methods(cls)["__init__"]
    assigned = {
        t.attr
        for n in ast.walk(init)
        for t in (n.targets if isinstance(n, ast.Assign) else [getattr(n, "target", None)])
        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"
    }
    members = assigned | set(_methods(cls))
    used = {
        "waiting", "kv_holding_waiting", "deferred_waiting", "running", "requests", "policy",
        "scheduler_config", "vllm_config", "kv_cache_manager", "need_mamba_block_aligned_split",
        "finish_requests", "_free_request", "_pause_state", "num_prefill_lookahead",
        "finished_recving_kv_req_ids", "get_request_counts", "prefill_capacity_bound",
        "connector", "grammar_compile_error_reqs", "max_num_active_reqs",
        "num_waiting_for_streaming_input",
    }
    assert used <= members, used - members
    adapter_reads = {
        n.attr
        for n in ast.walk(_class(ADAPTER_TREE, "SptcScheduler"))
        if isinstance(n, ast.Attribute)
        and isinstance(n.value, ast.Name)
        and n.value.id == "self"
        and not n.attr.startswith(("_sptc", "sptc_"))
    }
    assert adapter_reads <= members | used, adapter_reads - members


def test_request_and_engine_fields_exist():
    """(iv) RequestStatus members, Request attributes, EngineCoreOutput fields."""
    req_tree = _tree(SRC / "vllm/v1/request.py")
    status = {
        t.id
        for n in _class(req_tree, "RequestStatus").body
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name)
    }
    used_status = {
        n.attr
        for n in ast.walk(ADAPTER_TREE)
        if isinstance(n, ast.Attribute)
        and isinstance(n.value, ast.Name)
        and n.value.id == "RequestStatus"
    }
    assert used_status and used_status <= status, used_status - status

    req_init = _methods(_class(req_tree, "Request"))
    req_attrs = {
        t.attr
        for n in ast.walk(req_init["__init__"])
        if isinstance(n, (ast.Assign, ast.AnnAssign))
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
        if isinstance(t, ast.Attribute)
    } | set(req_init)
    for a in ("sampling_params", "resumable", "client_index", "trace_headers", "status",
              "request_id", "num_computed_tokens", "num_tokens", "take_events", "is_finished",
              "num_output_placeholders", "num_prompt_tokens", "max_tokens",
              "num_stale_output_tokens", "drop_stale_output", "structured_output_request",
              "num_in_flight_tokens", "is_prefill_chunk"):
        assert a in req_attrs, a

    eng = _tree(SRC / "vllm/v1/engine/__init__.py")
    eco = {
        n.target.id for n in _class(eng, "EngineCoreOutput").body if isinstance(n, ast.AnnAssign)
    }
    assert {"request_id", "new_token_ids", "finish_reason", "stop_reason", "events",
            "trace_headers"} <= eco
    ecos = {
        n.target.id for n in _class(eng, "EngineCoreOutputs").body if isinstance(n, ast.AnnAssign)
    }
    assert "outputs" in ecos
    finish = {
        t.id
        for n in _class(eng, "FinishReason").body
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name)
    }
    assert "ABORT" in finish


def test_async_scheduler_does_not_override_schedule():
    """SptcAsyncScheduler relies on AsyncScheduler only touching these two hooks."""
    a = _methods(_class(_tree(SRC / "vllm/v1/core/sched/async_scheduler.py"), "AsyncScheduler"))
    assert set(a) == {"__init__", "_update_after_schedule", "_update_request_with_output"}


def test_fcfs_queue_is_a_deque():
    """_sptc_begin_step reorders `waiting` with deque.clear()/extend()."""
    rq = _tree(SRC / "vllm/v1/core/sched/request_queue.py")
    bases = [ast.unparse(b) for b in _class(rq, "FCFSRequestQueue").bases]
    assert bases[0] == "deque[Request]"


def test_openai_protocol_maps_vllm_xargs_to_extra_args():
    for p in ("chat_completion", "completion"):
        src = (SRC / f"vllm/entrypoints/openai/{p}/protocol.py").read_text()
        assert "vllm_xargs:" in src and "self.vllm_xargs" in src and "extra_args=" in src
