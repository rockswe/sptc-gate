"""How often does real model-written code have each speculation case?

Corpus: CodeAct (xingyaoww/code-act, Apache-2.0, 7,139 trajectories by gpt-3.5-turbo,
claude-instant-1, claude-2 and gpt-4). Tools are declared in each system prompt as
"[n] name(...)": HotpotQA has `wikipedia_search` (read-only); ALFWorld has household
actions (side effects). Every <execute> block is parsed statically (no code is run).

Per tool call it records the features the case labels need:
  literal       every argument is a constant                      -> Pydantic / pi-fabric eligible
  in_loop       inside a for/while body or a comprehension         -> case B
  in_helper     inside a def / lambda                              -> case B
  in_branch     inside an if/elif/else arm (or try/except handler) -> case C
  cond_on_tool  an enclosing if/while test reads a tool result     -> case C on a pending value
  dep_on_tool   an argument reads a tool result (this or an earlier block of the same
                conversation: the REPL keeps state)                -> case A
Derived: which calls each design could start early, and which launches are BETS (a
literal-only speculator launches calls in every arm; only one arm runs).

  .venv/bin/python -I experiments/census.py <codeact.parquet> results/census
  .venv/bin/python -I experiments/census.py <replies.parquet> <out dir> "<corpus description>"
"""

from __future__ import annotations

import ast
import builtins
import json
import re
import sys
import textwrap
import warnings
from collections import Counter
from pathlib import Path

import pandas as pd

TOOL_DECL = re.compile(r"\[\d+\]\s*([A-Za-z_][A-Za-z0-9_]*)\(")  # CodeAct
SMOL_DECL = re.compile(r"^\s*def ([A-Za-z_][A-Za-z0-9_]*)\(", re.M)  # smolagents
EXECUTE = re.compile(r"<execute>(.*?)</execute>", re.S)
SMOL_CODE = re.compile(r"<code>(.*?)</code>|```(?:py|python)?\n(.*?)```", re.S)
REPL_CODE = re.compile(r"```repl\n(.*?)```", re.S)  # RLM
RLM_TOOLS = {"llm_query", "llm_query_batched", "rlm_query", "rlm_query_batched"}
SIDE_EFFECTS = {"put", "goto", "take_from", "open_receptacle", "toggle", "close_receptacle",
                "clean", "heat", "cool", "use",  # ALFWorld actions change the world
                "final_answer"}  # smolagents: ends the run
_BUILTINS = set(dir(builtins))


def source_of(cid: str) -> str:
    parts = cid.split("/")
    return parts[1] if len(parts) == 4 else "/".join(parts[1:3])  # smolagents ids: x/src/model/i


def model_of(cid: str) -> str:
    return cid.split("/")[-2]


def names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def tool_calls_in(node: ast.AST, tools: set[str]) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in tools]


def _const(a: ast.AST) -> bool:
    if isinstance(a, ast.UnaryOp) and isinstance(a.op, (ast.USub, ast.UAdd)):
        return isinstance(a.operand, ast.Constant)  # -1, +2.5
    return isinstance(a, ast.Constant)


def is_literal(call: ast.Call) -> bool:
    args = list(call.args) + [k.value for k in call.keywords]
    return all(_const(a) for a in args)


class Scan(ast.NodeVisitor):
    """Walks one block in program order with an enclosing-context stack and a taint set
    (names holding values derived from tool results) that persists across blocks."""

    def __init__(self, tools: set[str], tainted: set[str]) -> None:
        self.tools = tools
        self.tainted = tainted  # also holds names of model-defined helpers that call tools
        self.ctx: list[tuple[str, ast.AST]] = []
        self.calls: list[dict] = []
        self.side_effect_seen = False  # a world-changing call earlier in this block

    def _reads_tool(self, node: ast.AST) -> bool:
        # a call to a model-defined helper that calls a tool reads a tool result: the
        # helper's name is in `tainted` (see visit_FunctionDef), and names_in() sees it
        return bool(names_in(node) & self.tainted) or bool(tool_calls_in(node, self.tools))

    def _taint_targets(self, targets, value, strong: bool = True) -> None:
        """Assignment from a tool-derived value taints the targets; reassignment from
        anything else clears them (strong update), except augmented assignment."""
        hot = value is not None and self._reads_tool(value)
        # clearing is only sound on straight-line code: inside a branch or loop the
        # other path may still hold a tool value (may-analysis)
        strong = strong and not self.ctx
        for t in targets:
            for name in self._target_bases(t):
                if hot:
                    self.tainted.add(name)
                elif strong:
                    self.tainted.discard(name)

    @staticmethod
    def _target_bases(t) -> list[str]:
        """Names a target binds: `x`, `a, b`, and the base of `d[k]` / `o.f` (but not the
        names used inside the subscript index)."""
        if isinstance(t, ast.Name):
            return [t.id]
        if isinstance(t, (ast.Tuple, ast.List)):
            return [n for e in t.elts for n in Scan._target_bases(e)]
        if isinstance(t, ast.Starred):
            return Scan._target_bases(t.value)
        while isinstance(t, (ast.Subscript, ast.Attribute)):
            t = t.value
        return [t.id] if isinstance(t, ast.Name) else []

    # -- statements that bind names ------------------------------------------------
    def visit_Assign(self, node):
        self.generic_visit(node)
        self._taint_targets(node.targets, node.value)

    def visit_AugAssign(self, node):
        self.generic_visit(node)
        self._taint_targets([node.target], node.value, strong=False)

    def visit_AnnAssign(self, node):
        self.generic_visit(node)
        self._taint_targets([node.target], node.value)

    def visit_Expr(self, node):
        # `results.append(search(x))` taints `results`
        self.generic_visit(node)
        v = node.value
        if (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
                and isinstance(v.func.value, ast.Name) and self._reads_tool(v)):
            self.tainted.add(v.func.value.id)

    # -- context ---------------------------------------------------------------------
    def _with(self, kind, node, fields):
        self.ctx.append((kind, node))
        for f in fields:
            val = getattr(node, f, None)
            if isinstance(val, list):
                for x in val:
                    self.visit(x)
            elif val is not None:
                self.visit(val)
        self.ctx.pop()

    def visit_For(self, node):
        self.visit(node.iter)
        self._taint_targets([node.target], node.iter)
        self._with("loop", node, ["body"])
        self._with("branch", node, ["orelse"])

    visit_AsyncFor = visit_For

    def visit_While(self, node):
        self.visit(node.test)
        self._with("loop", node, ["body"])
        self._with("branch", node, ["orelse"])

    def visit_If(self, node):
        self.visit(node.test)
        self._with("branch", node, ["body", "orelse"])

    def visit_Try(self, node):
        for x in node.body:
            self.visit(x)
        for h in node.handlers:
            self._with("branch", node, [])  # marker only
            self.ctx.append(("branch", node))
            for x in h.body:
                self.visit(x)
            self.ctx.pop()
        self._with("branch", node, ["orelse"])
        for x in node.finalbody:
            self.visit(x)

    def visit_FunctionDef(self, node):
        self._with("helper", node, ["body"])
        if tool_calls_in(node, self.tools) or names_in(node) & self.tainted:
            self.tainted.add(node.name)  # its return value may carry a tool result

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        self._with("helper", node, ["body"])

    def _comp(self, node):
        for g in node.generators:
            self.visit(g.iter)
            self._taint_targets([g.target], g.iter)
        self.ctx.append(("loop", node))
        for f in ("elt", "key", "value"):
            if getattr(node, f, None) is not None:
                self.visit(getattr(node, f))
        for g in node.generators:
            for c in g.ifs:
                self.visit(c)
        self.ctx.pop()

    visit_ListComp = visit_SetComp = visit_GeneratorExp = visit_DictComp = _comp

    def visit_IfExp(self, node):
        self.visit(node.test)
        self.ctx.append(("branch", node))
        self.visit(node.body)
        self.visit(node.orelse)
        self.ctx.pop()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in self.tools:
            kinds = {k for k, _ in self.ctx}
            cond_nodes = [n for k, n in self.ctx if k in ("branch", "loop")
                          and isinstance(n, (ast.If, ast.While, ast.IfExp))]
            args = list(node.args) + [k.value for k in node.keywords]
            # a read after a write (earlier in the block, or anywhere in an enclosing loop
            # that writes) cannot be started early without seeing a stale world
            loop_writes = any(k == "loop" and any(c.func.id in SIDE_EFFECTS for c in
                                                  tool_calls_in(n, self.tools))
                              for k, n in self.ctx)
            self.calls.append({
                "after_side_effect": self.side_effect_seen or loop_writes,
                "tool": node.func.id,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "end_col": node.end_col_offset,
                "literal": is_literal(node),
                "in_loop": "loop" in kinds,
                "in_helper": "helper" in kinds,
                "in_branch": "branch" in kinds,
                "cond_on_tool": any(self._reads_tool(n.test) for n in cond_nodes),
                "dep_on_tool": any(self._reads_tool(a) for a in args),
                "side_effect": node.func.id in SIDE_EFFECTS,
            })
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id in SIDE_EFFECTS \
                and node.func.id in self.tools:
            self.side_effect_seen = True


warnings.filterwarnings("ignore", category=SyntaxWarning)  # model code with bad escapes


def blocks_of(text: str, fmt: str) -> list[tuple[int, str]]:
    """(offset of the code in the message, code)."""
    if fmt == "codeact":
        return [(m.start(1), m.group(1)) for m in EXECUTE.finditer(text)]
    if fmt == "rlm":
        return [(m.start(1), m.group(1)) for m in REPL_CODE.finditer(text)]
    out = []
    for m in SMOL_CODE.finditer(text):
        g = 1 if m.group(1) is not None else 2
        out.append((m.start(g), m.group(g)))
    return out


def line_offsets(code: str) -> list[int]:
    offs = [0]
    for line in code.splitlines(keepends=True):
        offs.append(offs[-1] + len(line))
    return offs


def scan_conversation(conv, tools: set[str], fmt: str = "codeact") -> tuple[list[dict], int, int]:
    tainted: set[str] = set()
    calls, blocks, bad = [], 0, 0
    for turn, m in enumerate(conv):
        if m["role"] != "assistant":
            continue
        text = str(m["content"])
        for b, (start, code) in enumerate(blocks_of(text, fmt)):
            blocks += 1
            body = textwrap.dedent(code.strip("\n"))
            lead = len(code) - len(code.lstrip("\n"))
            try:
                tree = ast.parse(body)
            except SyntaxError:
                bad += 1
                continue
            s = Scan(tools, tainted)
            for stmt in tree.body:
                s.visit(stmt)
            offs = line_offsets(body)
            for c in s.calls:
                end_in_body = offs[c.pop("end_line") - 1] + c.pop("end_col")
                # characters the model still streams after this call's closing paren
                # (dedent shifts columns by a few chars per line: an approximation)
                c["chars_after"] = max(0, len(text) - (start + lead + end_in_body))
                c.update(turn=turn, block=b, block_calls=len(s.calls))
            calls.extend(s.calls)
    return calls, blocks, bad


def classify(c: dict) -> str:
    """Mutually exclusive case label, most constraining first."""
    if c["side_effect"]:
        return "D side effect"
    if c["cond_on_tool"]:
        return "C under a condition on a tool result"
    if c["dep_on_tool"]:
        return "A argument depends on a tool result"
    if c["in_branch"]:
        return "C under a condition (not on a tool result)"
    if c["in_loop"] or c["in_helper"]:
        return "B in a loop/helper/comprehension"
    return "literal or local-only argument, straight-line" if c["literal"] else \
        "straight-line, argument from local values"


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(src)
    fmt = ("codeact" if "conversations" in df.columns else
           "rlm" if "rlm_iter" in df.columns else "smolagents")
    if fmt == "rlm":  # one row per RLM iteration: regroup into one conversation per example
        convs = []
        for ex, g in df.sort_values(["example_idx", "rlm_iter"]).groupby("example_idx"):
            msgs = [{"role": "system", "content": "\n".join(f"def {t}(" for t in sorted(RLM_TOOLS))}]
            msgs += [{"role": "assistant", "content": r} for r in g.response]
            convs.append((f"x/rlm-{g.model.iloc[0]}/{g.model.iloc[0]}/{ex}", msgs))
        df = pd.DataFrame(convs, columns=["id", "conversations"])
    if fmt == "smolagents":  # one trajectory per row; id = model/source/row
        df = df.assign(id=[f"x/{s}/run/{m.split('/')[-1]}/{i}" for i, (s, m)
                           in enumerate(zip(df.source, df.model_id, strict=True))],
                       conversations=df.messages)
        df["id"] = [f"x/{s}/{m.split('/')[-1]}/{i}" for i, (s, m)
                    in enumerate(zip(df.source, df.model_id, strict=True))]
    rows, per_conv = [], []
    totals = Counter()
    for cid, conv in zip(df.id, df.conversations, strict=True):
        decl = TOOL_DECL if fmt == "codeact" else SMOL_DECL  # rlm: synthetic "def" header
        tools = set(decl.findall(str(conv[0]["content"])))
        if not tools:
            continue
        calls, blocks, bad = scan_conversation(conv, tools, fmt)
        totals["conversations"] += 1
        totals["blocks"] += blocks
        totals["unparsable_blocks"] += bad
        for i, c in enumerate(calls):
            c.update(id=cid, idx=i, source=source_of(cid), model=model_of(cid), case=classify(c))
            rows.append(c)
        per_conv.append({"id": cid, "source": source_of(cid), "model": model_of(cid),
                         "calls": len(calls), "blocks": blocks})
    calls = pd.DataFrame(rows)
    calls.to_csv(out / "calls.csv", index=False)
    pd.DataFrame(per_conv).to_csv(out / "conversations.csv", index=False)

    corpus = {"codeact": "CodeAct (2023 models)",
              "smolagents": "smolagents CodeAgent traces, one shard (2025 models)",
              "rlm": "RLM call traces (gpt-5-nano on CodeQA; one small public run)"}[fmt]
    if len(sys.argv) > 3:  # another corpus in one of these formats: its own description
        corpus = sys.argv[3]
    lines = [f"# Call-shape census: {corpus} (static analysis of model-written code)", "",
             f"{totals['conversations']} trajectories with declared tools, {totals['blocks']} "
             f"<execute> blocks ({totals['unparsable_blocks']} unparsable), {len(calls)} tool "
             "calls.", ""]
    for source, g in calls.groupby("source"):
        n = len(g)
        lines += [f"## {source}: {n} tool calls, tools {sorted(set(g.tool))}", "",
                  "| case | share of calls |", "|---|---|"]
        for case, k in g["case"].value_counts().items():
            lines.append(f"| {case} | {100 * k / n:.1f}% ({k}) |")
        spec = g[~g.side_effect & ~g.after_side_effect]  # safely speculable reads
        lit = spec[spec.literal & ~spec.in_helper]
        lines += ["", "| feature (any combination) | share |", "|---|---|"]
        for f in ("literal", "in_loop", "in_helper", "in_branch", "cond_on_tool", "dep_on_tool",
                  "side_effect"):
            lines.append(f"| {f} | {100 * g[f].mean():.1f}% |")
        multi = g.groupby(["id", "turn", "block"]).size()
        after = spec.chars_after / 4.0  # ~tokens still to stream (to end of message)
        if len(after):
            lines += ["", f"Tokens the model still streams after a speculable call's closing "
                      f"paren, to the end of its message (stop sequences aside, the "
                      f"overlap window): "
                      f"median "
                      f"{after.median():.0f}, p75 {after.quantile(0.75):.0f}, p90 "
                      f"{after.quantile(0.9):.0f}; share with <10 tokens "
                      f"{100 * (after < 10).mean():.0f}%."]
        lines += ["",
                  f"Calls per block: mean {multi.mean():.2f}; blocks with >=2 tool calls "
                  f"{100 * (multi >= 2).mean():.1f}%.", "",
                  "| design | can start early | of those, bets (in a branch arm: may not run) |",
                  "|---|---|---|",
                  f"| literal-only (Pydantic, pi-fabric) | {100 * len(lit) / n:.1f}% | "
                  f"{100 * lit.in_branch.mean() if len(lit) else 0:.1f}% |",
                  f"| literal-only, if every tool were read-only | "
                  f"{100 * (g.literal & ~g.in_helper).mean():.1f}% | "
                  f"{100 * g[g.literal & ~g.in_helper].in_branch.mean():.1f}% |",
                  f"| shadow (spec-ptc; reads not after a write, waits on conditions) | "
                  f"{100 * len(spec) / n:.1f}% | ~0% (peeks retract only on mutation/early "
                  "exit) |",
                  f"| reads excluded because they follow a write in the block/loop | "
                  f"{100 * (~g.side_effect & g.after_side_effect).mean():.1f}% | |", ""]
        by_model = g.groupby("model").agg(calls=("tool", "size"), literal=("literal", "mean"),
                                          dep=("dep_on_tool", "mean"),
                                          branch=("in_branch", "mean"), loop=("in_loop", "mean"))
        lines += ["| model | calls | literal | dep_on_tool | in_branch | in_loop |",
                  "|---|---|---|---|---|---|"]
        for mname, r in by_model.iterrows():
            lines.append(f"| {mname} | {int(r.calls)} | {100 * r.literal:.0f}% | "
                         f"{100 * r.dep:.0f}% | {100 * r.branch:.0f}% | {100 * r.loop:.0f}% |")
        lines.append("")
    (out / "census.md").write_text("\n".join(lines))
    json.dump(totals, open(out / "totals.json", "w"))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
