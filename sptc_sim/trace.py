"""Compile one model response into a timing-free trace of what each policy does.

The trick that keeps the agent side faithful: we run spec-ptc's OWN code
(StreamSegmenter, plan_peeks, SpecStore, the shadow/real/baseline hook
factories, SpecREPL) on the response, single-threaded, with tools that return
instantly. Every speculation is a Speculation subclass whose wait() logs a
"force" instead of blocking. The result is the exact op sequence spec-ptc
would produce, independent of latency: which statements the shadow runs and
in what order, which calls it dispatches or adopts from peeks, where it
blocks, what peeks retract, and what the real run claims or misses. The
simulator then replays those ops on a virtual clock against a model server.

Fake results are a deterministic function of (tool, args, occurrence), so the
same logical call has the same identity (and the same sampled output length)
under every policy: comparisons are paired.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from spec_ptc.contracts.tools import ToolRegistry, contains_nonspec, spec_key
from spec_ptc.engine.shadow import (
    NonSpeculated,
    _bound_names,
    _comp_local_names,
    _read_names,
    _rebind,
    shadow_builtins,
    snapshot_ns,
)
from spec_ptc.engine.speculation import (
    Budget,
    Speculation,
    SpecStore,
    SpecValue,
    force_in_place,
    make_baseline_hooks,
    make_real_hooks,
    make_shadow_hooks,
)
from spec_ptc.engine.streaming import StreamSegmenter, plan_peeks, repair_tail
from spec_ptc.runtime.harness import REAL_BUILTINS, SpecREPL, _worthwhile

# ---------------------------------------------------------------------------
# op sink: every fake tool / wait appends here; swapped per shadow item
_SINK: list = []


def _emit(op: tuple) -> None:
    _SINK.append(op)


@dataclass(frozen=True)
class CallInfo:
    tool: str
    rid: str  # result identity: tool + args + occurrence (paired across policies)
    prompt_chars: int
    raises: bool = False
    head: str = ""  # start of the prompt (its instruction template)


@dataclass
class ToolDef:
    name: str
    kind: str = "llm"  # llm | tool | noop
    speculatable: bool = True
    batched: bool = False
    raises_on: str | None = None  # substring that makes the tool raise
    returns: str | None = None  # fixed return for noop tools


SUITE_TOOLS = [
    ToolDef("llm_query"),
    ToolDef("llm_query_batched", batched=True),
    ToolDef("log_note", kind="noop", speculatable=False),
    ToolDef("env_probe", kind="noop", speculatable=False, returns="[x=cloud spend]"),
    ToolDef("llm_query_fragile", raises_on="BOOM"),
]


class _Results:
    """R(tool, args, occurrence) -> deterministic fake output string."""

    def __init__(self) -> None:
        self.occ: Counter = Counter()

    def make(self, tool: str, args: tuple) -> tuple[str, CallInfo]:
        h = hashlib.sha1(repr((tool, args)).encode()).hexdigest()[:8]
        n = self.occ[h]
        self.occ[h] += 1
        rid = f"{tool}:{h}#{n}"
        chars = sum(len(a) for a in args if isinstance(a, str))
        head = next((a[:40] for a in args if isinstance(a, str)), "")
        out = f"<{h}#{n}> ok"
        first = next((a for a in args if isinstance(a, str)), "").lower()
        if "yes or no" in first or "yes/no" in first:
            out += " yes" if int(h, 16) % 2 else " no"  # branch outcome: a fair coin per call
        return out, CallInfo(tool, rid, chars, head=head)


class LogSpec(Speculation):
    """A Speculation that is 'done' at once; waiting on it is logged as a force."""

    def wait(self, timeout: float | None = None) -> Any:
        _emit(("force", self.seq))
        if self.error is not None:
            raise self.error
        return self.result


@dataclass
class SpecRec:
    seq: int
    call: CallInfo
    source: str  # peek | shadow | literal


class FakeLauncher:
    """spec-ptc's Launcher logic (budget, adopt, peek top-up) without threads."""

    def __init__(self, store: SpecStore, results: _Results, tools: dict[str, ToolDef],
                 max_dispatches: int = 64) -> None:
        self.store = store
        self.results = results
        self.tools = tools
        self.budget = Budget(max_dispatches_per_turn=max_dispatches)
        self.specs: dict[int, SpecRec] = {}
        self._seq = 0

    def dispatch(self, tool, args, kwargs, source):
        if not self.budget.admit():
            return None
        self._seq += 1
        out, info = self.results.make(tool.name, args)
        td = self.tools.get(tool.name)
        spec = LogSpec(key=spec_key(tool, args, kwargs), seq=self._seq, args=args,
                       kwargs=kwargs, source=source)
        if td is not None and td.raises_on and any(
            isinstance(a, str) and td.raises_on in a for a in args
        ):
            spec.error = ValueError(f"tool failure: {td.raises_on}")
            info = CallInfo(info.tool, info.rid, info.prompt_chars, True, info.head)
        spec.result = out
        self.store.put(spec)
        self.specs[spec.seq] = SpecRec(spec.seq, info, source)
        _emit(("dispatch", spec.seq))
        return spec

    def dispatch_or_adopt(self, tool, args, kwargs, source):
        key = spec_key(tool, args, kwargs)
        spec = self.store.adopt(key)
        if spec is not None:
            _emit(("adopt", spec.seq))
            return spec
        return self.dispatch(tool, args, kwargs, source)

    def ensure_peeked(self, tool, args, needed):
        key = spec_key(tool, args, {})
        new = 0
        while self.store.unadopted_peeks(key) < needed:
            if self.dispatch(tool, args, {}, "peek") is None:
                break
            new += 1
        return new


class _EvictBus:
    """Captures SpecStore evictions as ops."""

    def emit(self, kind: str, **data) -> None:
        if kind == "evict":
            _emit(("evict", data["seq"]))


def _registry(tools: list[ToolDef], results: _Results) -> ToolRegistry:
    reg = ToolRegistry()
    for td in tools:
        if td.kind == "noop":
            reg.register(td.name, (lambda *a, _r=td.returns, **k: _r), speculatable=False)
            continue

        def single(*args, _td=td, **kw):
            out, info = results.make(_td.name if not _td.batched else _td.name, args)
            raises = bool(_td.raises_on) and any(
                isinstance(a, str) and _td.raises_on in a for a in args
            )
            info = CallInfo(info.tool, info.rid, info.prompt_chars, raises, info.head)
            _emit(("run", info))
            if raises:
                raise ValueError(f"tool failure: {_td.raises_on}")
            return out

        if td.batched:
            base = td.name.removesuffix("_batched")

            def batched(prompts, *rest, _base=base, **kw):
                outs, infos = [], []
                for p in prompts:
                    o, i = results.make(_base, (p, *rest))
                    outs.append(o)
                    infos.append(i)
                _emit(("batch", tuple(infos)))
                return outs

            reg.register(td.name, batched, speculatable=td.speculatable, pure=True,
                         batched=True)
        else:
            reg.register(td.name, single, speculatable=td.speculatable, pure=True)
    return reg


# ---------------------------------------------------------------------------
@dataclass
class Item:
    kind: str  # stmt | peek
    avail_char: int  # response offset at which the stream delivered it
    ops: list
    reads: frozenset = frozenset()
    writes: frozenset = frozenset()
    src: str = ""


@dataclass
class TurnTrace:
    text: str
    chunk: int
    n_deltas: int
    items: list[Item]
    specs: dict[int, SpecRec]
    shadow_join: bool  # harness waits for the shadow before real exec
    spec_exec: list  # real-run ops in spec mode (claims are ("force", seq))
    spec_end_evict: list[int]
    base_exec: list
    literal_specs: list[tuple[SpecRec, int]]  # (spec, avail_char)
    literal_exec: list
    literal_end_evict: list[int]
    aborted: str | None = None
    notes: dict = field(default_factory=dict)

    def delta_of_char(self, c: int) -> int:
        """Index of the stream delta that delivers response char offset c (1-based end)."""
        return max(0, min(self.n_deltas - 1, (max(c, 1) - 1) // self.chunk))


class _SyncShadow:
    """ShadowRunner._exec_one/_peek, synchronous (spec-ptc 0.1.1 semantics)."""

    def __init__(self, real_locals, hooks, store, launcher, registry):
        self.hooks = hooks
        self.store = store
        self.launcher = launcher
        self.registry = registry
        self.ns: dict = {}
        self.ns.update(snapshot_ns(real_locals))
        self.ns.update(hooks)
        self.ns["__builtins__"] = shadow_builtins(REAL_BUILTINS)
        self.ns.setdefault("__name__", "__main__")
        for k, v in list(self.ns.items()):
            if callable(v) and hasattr(v, "__globals__") and k not in hooks:
                self.ns[k] = _rebind(v, self.ns)
        self.aborted: str | None = None
        self._last_peek_tally: dict = {}

    def exec_one(self, source: str) -> None:
        if self.aborted:
            return
        try:
            tree = ast.parse(source)
        except SyntaxError:
            self.aborted = "syntax"
            return
        for name in _bound_names(tree):
            if name in self.hooks:
                self.store.evict_tool(name, reason="rebound")
                self.aborted = f"rebind:{name}"
                return
        reads = _read_names(tree)
        tainted = sorted(n for n in reads if contains_nonspec(self.ns.get(n)))
        if tainted:
            for name in _bound_names(tree) - _comp_local_names(tree):
                self.ns[name] = NonSpeculated("tainted:" + "+".join(tainted))
            return
        # sorted: reads is a set of str, so its order (which value is forced first) followed
        # PYTHONHASHSEED and moved some agent-policy cells by up to ~1.4% between processes
        for name in sorted(reads):
            v = self.ns.get(name)
            try:
                if isinstance(v, SpecValue):
                    self.ns[name] = v._force()
                else:
                    force_in_place(v)
            except BaseException:
                self.aborted = "force-failed"
                return
        try:
            exec(compile(tree, "<shadow>", "exec"), self.ns, self.ns)
        except BaseException as e:  # noqa: BLE001 - mirrors spec-ptc
            self.aborted = f"{type(e).__name__}: {e}"[:80]

    def peek(self, tail: str) -> None:
        if self.aborted:
            return
        names = self.registry.speculative_names()
        try:
            plans = plan_peeks(tail, names, self.ns)
        except Exception:
            return
        tally = Counter((p.tool, p.args) for p in plans)
        new_tally: dict = {}
        for (tool_name, args), needed in tally.items():
            tool = self.registry.get(tool_name)
            if tool is None or tool.batched or not tool.speculatable:
                continue
            self.launcher.ensure_peeked(tool, args, needed)
            new_tally[spec_key(tool, args, {})] = needed
        for key, old_n in self._last_peek_tally.items():
            keep = new_tally.get(key, 0)
            if keep < old_n:
                self.store.evict_unadopted_peeks(key, keep, "peek-retracted")
        self._last_peek_tally = new_tally


_BUILTIN_NAMES = set(dir(builtins))


def _rw_sets(source: str, tool_names: set[str]) -> tuple[frozenset, frozenset]:
    """Name-level read/write sets for the dataflow (never-stall) scheduler.
    Writes include receivers of method calls and subscript/attribute stores,
    since `outs.append(x)` and `answer['k'] = v` mutate the named object."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return frozenset(), frozenset({"*"})
    reads = _read_names(tree) - tool_names - _BUILTIN_NAMES
    writes = set(_bound_names(tree)) - _comp_local_names(tree)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            base = n.func.value
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name):
                writes.add(base.id)
        if isinstance(n, (ast.Subscript, ast.Attribute)) and isinstance(n.ctx, ast.Store):
            base = n.value
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name):
                writes.add(base.id)
    if any(isinstance(n, (ast.Import, ast.ImportFrom, ast.Global)) for n in ast.walk(tree)):
        writes.add("*")  # be conservative: order against everything
    # a call to a model-defined function may read or mutate anything it closes over
    # (aliasing through plain assignment is still not tracked)
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id not in _BUILTIN_NAMES and n.func.id not in tool_names):
            writes.add("*")
    return frozenset(reads), frozenset(writes - tool_names)


def _block_spans(text: str) -> list[tuple[int, str]]:
    """(absolute offset of code start, code) for each ```repl block."""
    out, pos = [], 0
    while True:
        i = text.find("```repl", pos)
        if i < 0:
            return out
        start = text.find("\n", i) + 1
        end = text.find("\n```", start - 1)
        end = len(text) if end < 0 else end
        out.append((start, text[start:end]))
        pos = end + 4


def _literal_calls(text: str, reg: ToolRegistry, spec_names: set[str]):
    """Calls a literal-only speculator (Pydantic `speculate`, pi-fabric) would
    launch: every argument a constant. Returns (tool, args, kwargs, avail_char)."""
    found = []
    for start, code in _block_spans(text):
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        line_off = [0]
        for line in code.splitlines(keepends=True):
            line_off.append(line_off[-1] + len(line))
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
                continue
            if n.func.id not in spec_names:
                continue
            if not all(isinstance(a, ast.Constant) for a in n.args):
                continue
            if not all(isinstance(k.value, ast.Constant) and k.arg for k in n.keywords):
                continue
            end = start + line_off[n.end_lineno - 1] + n.end_col_offset
            found.append((n.func.id, tuple(a.value for a in n.args),
                          {k.arg: k.value.value for k in n.keywords}, end))
    found.sort(key=lambda x: x[3])
    return found


def compile_turn(text: str, context: Any = None, tools: list[ToolDef] | None = None,
                 chunk: int = 24, real_locals: dict | None = None) -> TurnTrace:
    """Trace one turn. `real_locals` carries REPL state from earlier turns."""
    global _SINK
    tools = tools or SUITE_TOOLS
    tdefs = {t.name: t for t in tools}
    tool_names = set(tdefs)
    deltas = [text[i:i + chunk] for i in range(0, len(text), chunk)] or [""]

    def fresh_repl() -> SpecREPL:
        repl = SpecREPL(context=context)
        if real_locals:
            repl.locals.update(snapshot_ns(real_locals))
        return repl

    # ---------------- spec mode: stream -> shadow items ----------------
    results = _Results()
    reg = _registry(tools, results)
    store = SpecStore(_EvictBus())
    launcher = FakeLauncher(store, results, tdefs)
    repl = fresh_repl()
    shadow_hooks = make_shadow_hooks(reg, launcher)
    seg = StreamSegmenter()
    items: list[Item] = []
    segments = []
    shadow: _SyncShadow | None = None
    last_tail = ""

    def run_item(kind: str, avail: int, payload: str) -> None:
        global _SINK
        nonlocal shadow
        if shadow is None:
            shadow = _SyncShadow(repl.locals, shadow_hooks, store, launcher, reg)
        _SINK = ops = []
        if kind == "stmt":
            shadow.exec_one(payload)
            r, w = _rw_sets(payload, tool_names)
        else:
            shadow.peek(payload)
            rep = repair_tail(payload)
            r, w = (_rw_sets(rep, tool_names)[0], frozenset()) if rep else (frozenset(), frozenset())
        items.append(Item(kind, avail, ops, r, w, payload[:120]))

    for k, d in enumerate(deltas):
        avail = min((k + 1) * chunk, len(text))
        for s in seg.feed(d):
            segments.append(s)
            run_item("stmt", avail, s.source)
        if "\n" in d and shadow is not None:
            tail = seg.pending_tail()
            if tail.strip() and tail != last_tail and _worthwhile(tail, last_tail, shadow):
                last_tail = tail
                run_item("peek", avail, tail)
    for s in seg.finish():
        segments.append(s)
        run_item("stmt", len(text), s.source)
    aborted = shadow.aborted if shadow else None

    blocks: dict[int, list] = {}
    for s in segments:
        blocks.setdefault(s.block_id, []).append(s)
    codes = ["\n".join(s.source for s in blocks[b]) for b in sorted(blocks)]

    # real run (spec mode): claims against the shadow's store
    _SINK = spec_exec = []
    real_hooks = make_real_hooks(reg, store, launcher)
    for code in codes:
        repl.execute_code(code, real_hooks)
    _SINK = end_evict = []
    store.evict_unclaimed("turn_end")
    spec_end_evict = [op[1] for op in end_evict]

    # ---------------- baseline ----------------
    _SINK = base_exec = []
    b_results = _Results()
    b_reg = _registry(tools, b_results)
    b_repl = fresh_repl()
    for code in codes:
        b_repl.execute_code(code, make_baseline_hooks(b_reg))

    # ---------------- literal-only speculation ----------------
    l_results = _Results()
    l_reg = _registry(tools, l_results)
    l_store = SpecStore(_EvictBus())
    l_launcher = FakeLauncher(l_store, l_results, tdefs, max_dispatches=32)
    literal_specs = []
    _SINK = []
    for name, args, kwargs, end in _literal_calls(text, l_reg, l_reg.speculative_names()):
        tool = l_reg.get(name)
        if tool.batched:
            continue
        spec = l_launcher.dispatch(tool, args, kwargs, "literal")
        if spec is not None:
            literal_specs.append((l_launcher.specs[spec.seq], end))
    _SINK = literal_exec = []
    l_repl = fresh_repl()
    for code in codes:
        l_repl.execute_code(code, make_real_hooks(l_reg, l_store, l_launcher))
    _SINK = l_end = []
    l_store.evict_unclaimed("turn_end")
    _SINK = []

    return TurnTrace(
        text=text, chunk=chunk, n_deltas=len(deltas), items=items, specs=launcher.specs,
        shadow_join=any(s.has_call for s in segments), spec_exec=spec_exec,
        spec_end_evict=spec_end_evict, base_exec=base_exec, literal_specs=literal_specs,
        literal_exec=literal_exec, literal_end_evict=[op[1] for op in l_end],
        aborted=aborted, notes={"real_locals": b_repl.locals},
    )
