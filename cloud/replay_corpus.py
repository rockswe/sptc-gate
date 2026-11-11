"""The replay corpus: recorded RLM sessions, as something that can be run again.

    python replay_corpus.py build --runs ../../_modal_runs --tasks <tasks.json> --out <dir>

Only the `nospec` arm records a session completely: rlms keeps every sub-call's prompt,
answer and time in the trajectory (`rlm_calls`). The speculative arms run their calls
outside that bookkeeping, so a claimed call leaves no record of its answer. The corpus is
therefore built from finished `nospec` tasks.

A session in the corpus holds what a replay needs and nothing it can recompute:

- the task (context, question, hint);
- per turn: the root's reply, how it was cut into deltas, its token count, and the sha256
  of the message history the root was sent;
- per sub-call prompt: the outcomes in program order. An outcome is the recorded answer
  with its output-token count, or the error text the program got instead.

**Outcomes that are errors.** rlms 0.1.3 runs every `llm_query_batched` in a new event
loop but keeps one async HTTP client, so each batch after a session's first loses the
prompts that are handed a connection of the previous, closed loop: they come back as
'Error: llm() call failed - Event loop is closed' (16 or 4 of every batch of 20 in these
runs). Such prompts leave no record. The model's later code was written after seeing those
strings, so a replay has to return them too. A failed prompt is found by alignment: the
recorded answers of a batch are the tail of the batch's prompt list.

**Checked while building.** Each session is run again here, without an engine: the
recorded replies' code is executed in a stock rlms REPL whose sub-calls return the
outcomes. The build fails for a session unless every block prints what it printed in the
recorded run and every turn's message history has the recorded sha256. So the corpus is
known to reproduce the recorded session before any GPU run.

**Sessions the timeout stopped.** rlms checks a task's timeout between turns, so a session
it stops has only whole turns in its trajectory. Such a session is kept (`final.kind` is
`timeout`) and replayed up to that boundary: its final record holds the sha256 of the
message history the next turn would have been sent, which checks the last turn's output
as an answer does for a finished session.

**Sessions a recording's deadline stopped** (rlm_record.py refuses a task's sub-calls
after 1,200 s). The turn in which that happened got error strings in place of answers and
is not the session's own. The turns that ended before the deadline are: such a session is
kept up to there (`final.kind` is `deadline`), and the message history the dropped turn
was sent is compared with the rebuilt one. PREREG_RECORD.md leaves these sessions out of
its registered replay; they can be replayed next to it.

A session that failed for any other reason is not replayable.

The corpus contains OOLONG text. Keep it out of the repository; `manifest.json` (counts,
hashes, timings) is safe to publish.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP_ERROR = "Error: llm() call failed - Event loop is closed"
MAX_ITERATIONS = 12  # spec-ptc benchmark/oolong_campaign/runner.py, _run_task
TOKENIZER_REPO = "Qwen/Qwen3-30B-A3B-Instruct-2507"
SCHEMA = 1
HASH_SEED = "0"  # PYTHONHASHSEED of the build and of every replay process
# what a replayed session answers where the recorded one was stopped by its timeout
TIMEOUT_TEXT = "[replay: the recorded session was stopped here by its timeout]"
DEADLINE_TEXT = ("[replay: the recorded session is replayed up to here; the recording's "
                 "sub-call deadline struck in its next turn]")
CUT_TEXT = {"timeout": TIMEOUT_TEXT, "deadline": DEADLINE_TEXT}


def sha(obj) -> str:
    """sha256 of a JSON-able object in a canonical form, or of a string as is."""
    if not isinstance(obj, str):
        obj = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(obj.encode("utf-8", "surrogatepass")).hexdigest()


def root_prompt_of(task: dict) -> str:
    """The root prompt the campaign's runner builds (runner._run_task)."""
    return f"{task['hint']}\n\nQuestion: {task['question']}"


# --------------------------------------------------------------------------- tokens
class Tokens:
    """Output-token counts for recorded answers.

    A single call's count is in its record. A batch's elements all carry the count of
    whichever call finished last (rlms reads the client's last usage once per batch), so
    theirs are counted with the model's tokenizer: the answer's tokens plus the end
    token. `check` compares that count with the exact one on the single calls."""

    def __init__(self, tokenizer_json: str | bool | None = None) -> None:
        """tokenizer_json: a tokenizer.json path; None fetches the model's from the hub;
        False counts by characters (tests)."""
        self.tok = None
        if tokenizer_json is False:
            return
        try:
            from tokenizers import Tokenizer

            if tokenizer_json is None:
                from huggingface_hub import hf_hub_download

                tokenizer_json = hf_hub_download(TOKENIZER_REPO, "tokenizer.json")
            self.tok = Tokenizer.from_file(tokenizer_json)
        except Exception as e:  # noqa: BLE001 - fall back to a character rule
            print(f"[corpus] no tokenizer ({type(e).__name__}: {e}); counting by characters",
                  file=sys.stderr)

    def count(self, text: str) -> int:
        """Tokens the engine generated for this answer, the end token included."""
        if self.tok is None:
            return max(1, round(len(text) / 4.0)) + 1
        return len(self.tok.encode(text, add_special_tokens=False).ids) + 1


def recorded_usage(call: dict) -> tuple[int | None, int | None]:
    for m in ((call.get("usage_summary") or {}).get("model_usage_summaries") or {}).values():
        return m.get("total_input_tokens"), m.get("total_output_tokens")
    return None, None


# --------------------------------------------------------------------------- alignment
def groups_of(calls: list[dict]) -> list[int]:
    """Lengths of the runs of consecutive calls with one identical time: a batch's answers
    all carry the batch's wall time divided by its size."""
    out: list[int] = []
    last = None
    for c in calls:
        t = float(c.get("execution_time") or 0.0)
        if out and last is not None and math.isclose(last, t, rel_tol=0, abs_tol=1e-12):
            out[-1] += 1
        else:
            out.append(1)
        last = t
    return out


class BlockOracle:
    """What each sub-call of one recorded block returned, found by walking the block's
    recorded calls in order while the code runs again."""

    def __init__(self, calls: list[dict], tokens: Tokens, error_texts: list[str]) -> None:
        self.calls = calls
        self.sizes = groups_of(calls)
        self.starts = [sum(self.sizes[:i]) for i in range(len(self.sizes))]
        self.p = 0
        self.tokens = tokens
        self.error_texts = error_texts  # error strings seen in the block's recorded state
        self.log: list[dict] = []  # one entry per sub-call invocation
        self.problems: list[str] = []

    def _prompt(self, i: int):
        return self.calls[i]["prompt"]

    def _ok(self, i: int, batch: bool) -> dict:
        c = self.calls[i]
        text = str(c.get("response") if c.get("response") is not None else "")
        _, out_exact = recorded_usage(c)
        n = self.tokens.count(text) if batch or not out_exact else int(out_exact)
        return {"r": text, "n": n, "t": round(float(c.get("execution_time") or 0.0), 4)}

    def single(self, prompt: str) -> str:
        if self.p < len(self.calls) and self._prompt(self.p) == prompt:
            o = self._ok(self.p, batch=False)
            self.p += 1
            self.log.append({"kind": "single", "items": [(prompt, o)]})
            return o["r"]
        # no record: the program got an error string instead of an answer
        cands = [t for t in self.error_texts if t != LOOP_ERROR]
        if len(cands) == 1:
            text = cands[0]
        else:
            text = cands[0] if cands else "Error: unrecorded call"
            self.problems.append(f"single call without a record, {len(cands)} error candidates")
        self.log.append({"kind": "single", "items": [(prompt, {"e": text})]})
        return text

    def batch(self, prompts: list[str]) -> list[str]:
        prompts = list(prompts)
        n = len(prompts)
        g = 0
        if self.p < len(self.calls) and self.p in self.starts:
            g = self.sizes[self.starts.index(self.p)]
        items: list[tuple[str, dict]] = []
        if 0 < g <= n and [self._prompt(self.p + j) for j in range(g)] == prompts[n - g:]:
            # the usual shape: the first n - g prompts failed, the rest were answered
            for p in prompts[: n - g]:
                items.append((p, {"e": LOOP_ERROR}))
            for j in range(g):
                items.append((prompts[n - g + j], self._ok(self.p + j, batch=True)))
            self.p += g
        else:
            # answered prompts are not the tail: match them in order inside this group
            end = self.p + g if g and g <= n else self.p
            hit = 0
            for p in prompts:
                if self.p < end and self._prompt(self.p) == p:
                    items.append((p, self._ok(self.p, batch=True)))
                    self.p += 1
                    hit += 1
                else:
                    items.append((p, {"e": LOOP_ERROR}))
            if hit:
                self.problems.append(f"batch of {n}: {hit} answers not at its tail")
        self.log.append({"kind": "batch", "items": items})
        return [o["r"] if "r" in o else o["e"] for _, o in items]


def _error_strings(block: dict) -> list[str]:
    """Error strings in a recorded block's variables and output, most common first."""
    found: Counter = Counter()

    def walk(v, depth=0):
        if isinstance(v, str):
            if v.startswith("Error: "):
                found[v] += 1
        elif isinstance(v, (list, tuple)) and depth < 3:
            for x in v:
                walk(x, depth + 1)
        elif isinstance(v, dict) and depth < 3:
            for x in v.values():
                walk(x, depth + 1)

    walk((block.get("result") or {}).get("locals") or {})
    return [t for t, _ in found.most_common()]


# --------------------------------------------------------------------------- one session
def _make_repl(context: str):
    """A stock rlms LocalREPL whose sub-calls go to `repl.oracle` (set per block)."""
    from rlm.environments.local_repl import LocalREPL

    class BuilderREPL(LocalREPL):
        oracle: BlockOracle | None = None

        def _llm_query(self, prompt, model=None):  # type: ignore[override]
            return self.oracle.single(prompt)

        def _llm_query_batched(self, prompts, model=None):  # type: ignore[override]
            return self.oracle.batch(prompts)

    return BuilderREPL(context_payload=context)


def cuts_of(root: dict, reply: str) -> list[int]:
    """Characters received after each delta of a recorded root stream."""
    cuts = [int(a[1]) for a in (root.get("arrivals") or [])]
    if not cuts or cuts[-1] != len(reply) or any(b <= a for a, b in zip(cuts, cuts[1:], strict=False)):
        raise ValueError(f"delta boundaries do not cover the reply ({len(cuts)} deltas, "
                         f"last at {cuts[-1] if cuts else None}, reply {len(reply)} chars)")
    return cuts


def build_session(traj_path: Path, roots: list[dict], task: dict, session: str, source: dict,
                  tokens: Tokens) -> tuple[dict | None, dict]:
    """One recorded task run as a corpus session, checked by running it again.
    Returns (session, report); session is None if the run does not reproduce.
    `source["cut"]`: `timeout` if the task's timeout stopped it between two turns;
    `deadline` if a recording's sub-call deadline struck in its turn `turns_kept` + 1."""
    from rlm.core.types import CodeBlock, RLMIteration
    from rlm.utils.parsing import find_code_blocks, format_iteration
    from rlm.utils.prompts import (
        RLM_SYSTEM_PROMPT,
        QueryMetadata,
        build_rlm_system_prompt,
        build_user_prompt,
    )

    lines = [json.loads(x) for x in open(traj_path) if x.strip()]
    its = [d for d in lines if d.get("type") == "iteration"]
    report: dict = {"session": session, **source, "turns": 0, "problems": []}
    bad = report["problems"]
    dropped = None  # the first turn that is not the session's own, if a deadline struck
    if source.get("cut") == "deadline":
        kept = int(source.get("turns_kept") or 0)
        dropped = its[kept] if kept < len(its) else None
        its = its[:kept]
    root_prompt = root_prompt_of(task)
    history = build_rlm_system_prompt(system_prompt=RLM_SYSTEM_PROMPT,
                                      query_metadata=QueryMetadata(task["context"]),
                                      custom_tools=None, root_prompt=root_prompt,
                                      orchestrator=True)
    repl = _make_repl(task["context"])
    turns: list[dict] = []
    calls: dict[str, list] = defaultdict(list)
    final: dict | None = None
    n_ok = n_err = n_batches = n_singles = out_tokens = 0
    rec_call_s = 0.0
    try:
        for k, it in enumerate(its):
            blocks = it.get("code_blocks") or []
            if k >= MAX_ITERATIONS or (not blocks and it.get("final_answer") is not None
                                       and k == len(its) - 1 and k >= len(roots)):
                # out of iterations: rlms asked once more for an answer, without streaming
                prompt = history + [{"role": "assistant", "content":
                                     "Please provide a final answer to the user's question "
                                     "based on the information provided."}]
                if it.get("prompt") is not None and sha(it["prompt"]) != sha(prompt):
                    bad.append("the final-answer call's message history differs")
                text = str(it.get("response") or "")
                final = {"kind": "default_answer", "text": text, "prompt_sha": sha(prompt),
                         "tokens": tokens.count(text)}
                break
            if k >= len(roots):
                bad.append(f"turn {k + 1} has no root_stream record")
                break
            root = roots[k]
            history.append(build_user_prompt(root_prompt, k, 1, 0, max_iterations=MAX_ITERATIONS))
            prompt_sha = sha(history)
            if it.get("prompt") is not None and sha(it["prompt"]) != prompt_sha:
                bad.append(f"turn {k + 1}: message history differs from the recorded one")
            reply = it["response"]
            if root.get("truncated"):
                bad.append(f"turn {k + 1}: the recorded reply was cut")
            codes = find_code_blocks(reply)
            if codes != [b["code"] for b in blocks]:
                bad.append(f"turn {k + 1}: code blocks differ from the reply's")
            done_blocks, meta = [], []
            for bi, b in enumerate(blocks):
                rec = b.get("result") or {}
                repl.oracle = BlockOracle(rec.get("rlm_calls") or [], tokens, _error_strings(b))
                res = repl.execute_code(b["code"])
                o = repl.oracle
                if o.p != len(o.calls):
                    bad.append(f"turn {k + 1} block {bi + 1}: {len(o.calls) - o.p} of "
                               f"{len(o.calls)} recorded calls were not made again")
                bad += [f"turn {k + 1} block {bi + 1}: {p}" for p in o.problems]
                if res.stdout != rec.get("stdout") or res.stderr != rec.get("stderr"):
                    bad.append(f"turn {k + 1} block {bi + 1}: output differs from the recorded one")
                for inv in o.log:
                    n_batches += inv["kind"] == "batch"
                    n_singles += inv["kind"] == "single"
                    for p, out in inv["items"]:
                        calls[p].append(out)
                        if "r" in out:
                            n_ok += 1
                            out_tokens += out["n"]
                        else:
                            n_err += 1
                rec_call_s += sum(float(c.get("execution_time") or 0.0) for c in o.calls)
                done_blocks.append(CodeBlock(code=b["code"], result=res))
                meta.append({"stdout_sha": sha(res.stdout), "stderr_sha": sha(res.stderr),
                             "invocations": [[inv["kind"], len(inv["items"]),
                                              sum(1 for _, x in inv["items"] if "e" in x)]
                                             for inv in o.log],
                             "rec_exec_s": round(float(rec.get("execution_time") or 0.0), 3),
                             "answer": res.final_answer is not None})
            turns.append({
                "iteration": k + 1, "prompt_sha": prompt_sha, "reply": reply,
                "tokens": int(root.get("tokens") or 0), "n_deltas": int(root.get("n_deltas") or 0),
                "cuts": cuts_of(root, reply), "blocks": meta,
                "rec": {"prompt_tokens": root.get("prompt_tokens"), "ttft_s": root.get("ttft_s"),
                        "stream_s": root.get("stream_s"), "exec_s": root.get("exec_s"),
                        "tpot_ms": root.get("tpot_ms")}})
            iteration = RLMIteration(prompt=history, response=reply, code_blocks=done_blocks,
                                     iteration_time=0.0)
            answer = next((b.result.final_answer for b in done_blocks
                           if b.result.final_answer is not None), None)
            if answer is not None:
                final = {"kind": "answer", "text": answer}
                if it.get("final_answer") != answer:
                    bad.append(f"turn {k + 1}: final answer differs from the recorded one")
                break
            history.extend(format_iteration(iteration))
        if final is None and source.get("cut") in CUT_TEXT and turns and not bad:
            # stopped before turn len(turns) + 1: what that turn's root would have been sent
            nxt = history + [build_user_prompt(root_prompt, len(turns), 1, 0,
                                               max_iterations=MAX_ITERATIONS)]
            if dropped is not None and dropped.get("prompt") is not None \
                    and sha(dropped["prompt"]) != sha(nxt):
                bad.append(f"turn {len(turns) + 1}, the first one left out, was sent another "
                           "message history than the rebuilt one")
            else:
                final = {"kind": source["cut"], "text": CUT_TEXT[source["cut"]],
                         "prompt_sha": sha(nxt)}
    except Exception as e:  # noqa: BLE001 - a session that cannot be rebuilt is reported
        bad.append(f"{type(e).__name__}: {e}"[:200])
    finally:
        repl.cleanup()
    if final is None:
        bad.append("the recorded session has no final answer")
    dup = sum(1 for outs in calls.values() if len({json.dumps(o, sort_keys=True) for o in outs}) > 1)
    report.update(
        turns=len(turns), blocks=sum(len(t["blocks"]) for t in turns),
        root_tokens=sum(t["tokens"] for t in turns),
        rec_stream_s=round(sum(t["rec"]["stream_s"] or 0.0 for t in turns), 1),
        rec_after_s=round(sum(t["rec"]["exec_s"] or 0.0 for t in turns), 1),
        calls=n_ok, errors=n_err, batches=n_batches, singles=n_singles,
        call_out_tokens=out_tokens, rec_call_s=round(rec_call_s, 1),
        distinct_prompts=len(calls), prompts_with_differing_outcomes=dup,
        final=None if final is None else final["kind"],
        delta_token_gap=Counter(t["tokens"] - t["n_deltas"] for t in turns).most_common(4))
    if bad:
        return None, report
    sess = {"schema": SCHEMA, "session": session, "source": source,
            "task": {**task, "task_id": session}, "turns": turns, "final": final,
            "calls": dict(calls)}
    report["sha256"] = sha(sess)
    return sess, report


def check_tokens(traj_paths: list[Path], tokens: Tokens) -> dict:
    """The tokenizer's count against the exact one, on recorded single calls."""
    diffs = []
    for path in traj_paths:
        for d in (json.loads(x) for x in open(path) if x.strip()):
            for b in d.get("code_blocks") or []:
                calls = (b.get("result") or {}).get("rlm_calls") or []
                sizes = groups_of(calls)
                i = 0
                for g in sizes:
                    if g == 1:
                        _, exact = recorded_usage(calls[i])
                        if exact:
                            diffs.append(tokens.count(str(calls[i].get("response") or "")) - exact)
                    i += g
    if not diffs:
        return {"single_calls": 0}
    return {"single_calls": len(diffs), "exact": sum(1 for x in diffs if x == 0),
            "mean_diff": round(statistics.fmean(diffs), 3), "max_abs_diff": max(map(abs, diffs))}


# --------------------------------------------------------------------------- the corpus
def cut_of(task_row: dict) -> str | None:
    """`timeout` for a task rlms stopped between two turns (TimeoutExceededError);
    `deadline` for one whose sub-calls a recording refused (rlm_record.py)."""
    if task_row.get("ok"):
        return None
    err = str(task_row.get("error") or "")
    if err.startswith("TimeoutExceededError"):
        return "timeout"
    return "deadline" if err.startswith("SubcallDeadline") else None


def turns_before_deadline(events: list[dict], task_id: str) -> int:
    """How many of a task's turns had ended when its sub-call deadline came."""
    ev = [e for e in events if e.get("task_id") == task_id]
    begin = next((e for e in ev if e.get("kind") == "task_begin"), None)
    hit = next((e for e in ev if e.get("kind") == "subcall_deadline"), None)
    if begin is None or hit is None:
        return 0
    deadline = float(begin["t"]) + float(hit["deadline_s"])
    n = 0
    for r in sorted((e for e in ev if e.get("kind") == "root_stream"),
                    key=lambda e: e["iteration"]):
        end = (float(r["t_start"]) + float(r.get("stream_s") or 0.0)
               + float(r.get("shadow_wait_s") or 0.0) + float(r.get("exec_s") or 0.0))
        if end >= deadline:
            break
        n += 1
    return n


def discover(runs: Path) -> list[dict]:
    """Every task of a `nospec` unit under `runs` that finished, or that its timeout or a
    recording's deadline stopped, and has a raw trajectory."""
    found = []
    for udir in sorted(runs.glob("*/units/nospec_c*_r*")):
        if not (udir / "DONE").exists() or not (udir / "rlm_trajs").is_dir():
            continue
        stats = json.loads((udir / "unit_stats.json").read_text())
        server = udir.parents[1] / "server.json"
        window = 8192
        if server.exists():
            cmd = json.loads(server.read_text()).get("cmd") or []
            for a, b in zip(cmd, cmd[1:], strict=False):
                if a == "--max-model-len":
                    window = int(b)
        for t in stats.get("tasks", []):
            files = sorted((udir / "rlm_trajs").glob(f"{t['task_id']}_*.jsonl"))
            cut = cut_of(t)
            if (t.get("ok") or cut) and files:
                found.append({"run": udir.parents[1].name, "unit": udir.name,
                              "task_id": t["task_id"], "traj": files[-1], "udir": udir,
                              "window": window, "wall_s": t.get("wall_s"),
                              "score": t.get("score"), "n_subcalls": t.get("n_subcalls"),
                              "cut": cut})
    return found


def session_names(found: list[dict], tag: str | None = None) -> None:
    """Unique names: the task id, with the run's window or concurrency where a task was
    recorded more than once (the first, largest-window recording keeps the plain id).
    With a `tag`, every session is named <task>.<tag><repeat> instead: a second corpus
    then shares no name with the first."""
    if tag:
        for f in found:
            f["session"] = f"{f['task_id']}.{tag}{re.search(r'_r(\d+)$', f['unit']).group(1)}"
        names = [f["session"] for f in found]
        if len(set(names)) != len(names):
            raise SystemExit(f"--tag {tag}: a task has one repeat number in two runs")
        return
    order = sorted(found, key=lambda f: (-f["window"], f["run"]))
    seen: Counter = Counter()
    for f in order:
        tid = f["task_id"]
        conc = re.search(r"_c(\d+)_", f["unit"]).group(1)
        f["session"] = tid if not seen[tid] else f"{tid}.w{f['window'] // 1024}k-c{conc}"
        seen[tid] += 1


def build(runs: Path, tasks_path: Path, out: Path, only: list[str] | None = None,
          tokens: Tokens | None = None, tag: str | None = None) -> dict:
    tasks = {t["task_id"]: t for t in json.loads(Path(tasks_path).read_text())}
    tokens = tokens or Tokens()
    found = discover(Path(runs))
    session_names(found, tag)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for f in found:
        if only and f["session"] not in only:
            continue
        events = [json.loads(x) for x in open(f["udir"] / "events.jsonl") if x.strip()]
        roots = sorted((e for e in events if e.get("kind") == "root_stream"
                        and e.get("task_id") == f["task_id"]), key=lambda e: e["iteration"])
        source = {k: f[k] for k in ("run", "unit", "task_id", "window", "wall_s", "score")}
        if f["cut"]:  # only where it applies: a finished session's record is as it was
            source["cut"] = f["cut"]
        if f["cut"] == "deadline":
            source["turns_kept"] = turns_before_deadline(events, f["task_id"])
        sess, rep = build_session(f["traj"], roots, tasks[f["task_id"]], f["session"], source,
                                  tokens)
        rep["replayable"] = sess is not None
        rows.append(rep)
        if sess is not None:
            (out / f"{f['session']}.json").write_text(json.dumps(sess, ensure_ascii=False))
        print(f"[corpus] {f['session']:28s} {'ok' if sess else 'NOT REPLAYABLE':15s} "
              f"turns {rep['turns']:2d} calls {rep.get('calls', 0):5d} errors "
              f"{rep.get('errors', 0):5d} {'; '.join(rep['problems'])[:160]}", flush=True)
    manifest = {"schema": SCHEMA, "tokenizer": TOKENIZER_REPO if tokens.tok else None,
                "token_check": check_tokens([f["traj"] for f in found], tokens),
                "loop_error": LOOP_ERROR, "sessions": rows}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def load_session(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def load_corpus(corpus: Path, only: list[str] | None = None) -> list[dict]:
    """The corpus's sessions, in the manifest's order (or `only`, in that order)."""
    corpus = Path(corpus)
    manifest = json.loads((corpus / "manifest.json").read_text())
    names = [r["session"] for r in manifest["sessions"] if r.get("replayable")]
    if only:
        missing = [n for n in only if n not in names]
        if missing:
            raise SystemExit(f"not in the corpus: {missing}")
        names = list(only)
    return [load_session(corpus / f"{n}.json") for n in names]


def render(manifest: dict) -> str:
    out = ["# Replay corpus (built from recorded `nospec` sessions)", "",
           "Each session was run again offline while it was built: every block printed what "
           "it printed in the recorded run, and every turn's message history has the "
           "recorded sha256.", "",
           "| session | from | turns | root tokens | recorded stream s | recorded after-stream s "
           "| sub-calls answered | returned an error | batches / single calls "
           "| sub-call output tokens | ends with |", "|" + "---|" * 11]
    for r in manifest["sessions"]:
        if not r.get("replayable"):
            out.append(f"| {r['session']} | {r['run']} {r['unit']} | not replayable: "
                       f"{'; '.join(r['problems'])[:120]} |" + " |" * 8)
            continue
        out.append(f"| {r['session']} | {r['run']} {r['unit']} | {r['turns']} | {r['root_tokens']} "
                   f"| {r['rec_stream_s']} | {r['rec_after_s']} | {r['calls']} | {r['errors']} "
                   f"| {r['batches']} / {r['singles']} | {r['call_out_tokens']} | {r['final']} |")
    tc = manifest.get("token_check") or {}
    if tc.get("single_calls"):
        out += ["", f"Output tokens of batch elements are counted with the model's tokenizer. "
                f"On the {tc['single_calls']} recorded single calls, where the exact count is "
                f"known, the count is exact for {tc['exact']} (mean difference "
                f"{tc['mean_diff']}, largest {tc['max_abs_diff']})."]
    return "\n".join(out) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--runs", type=Path, required=True, help="folder of downloaded runs")
    b.add_argument("--tasks", type=Path, required=True, help="tasks.json of the campaign")
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--only", type=lambda s: s.split(","), default=None)
    b.add_argument("--tag", default=None,
                   help="name every session <task>.<tag><repeat> (see session_names)")
    s = sub.add_parser("show")
    s.add_argument("--corpus", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        if os.environ.get("PYTHONHASHSEED") != HASH_SEED:
            # recorded code iterates over sets: one fixed order here and in every replay
            os.execve(sys.executable, [sys.executable, *sys.argv],
                      {**os.environ, "PYTHONHASHSEED": HASH_SEED})
        m = build(a.runs, a.tasks, a.out, a.only, tag=a.tag)
        (a.out / "manifest.md").write_text(render(m))
        print(render(m))
    else:
        print(render(json.loads((a.corpus / "manifest.json").read_text())))


if __name__ == "__main__":
    main()
