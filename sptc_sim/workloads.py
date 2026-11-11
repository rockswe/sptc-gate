"""RLM-style agent sessions for the serving experiments.

The suite's sub-calls are tiny (a context line each). RLM sub-calls on OOLONG
carry chunks of a long document, so their prefill is real work. These
programs keep the RLM shape: the long context lives in the REPL, the root
model writes code over it, sub-calls get chunks. Each session is three turns:
probe the context, run the program, write the answer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache

from .agent import CallInfo
from .trace import SUITE_TOOLS, ToolDef, TurnTrace, compile_turn

TOOLS = SUITE_TOOLS + [ToolDef("search", kind="tool")]


def make_context(n_records: int = 800, seed: int = 7) -> str:
    """Synthetic OOLONG-like corpus: one labeled record per line (~80 chars)."""
    rng = random.Random(seed)
    topics = ["billing", "outage", "refund", "login", "shipping", "upgrade", "privacy", "api"]
    words = ("please help account order charge error page update reset slow broken "
             "missing confirm delay request").split()
    lines = []
    for i in range(n_records):
        body = " ".join(rng.choice(words) for _ in range(rng.randint(6, 10)))
        lines.append(f"[rec {i:04d}] user=u{rng.randint(100, 999)} topic={rng.choice(topics)} {body}")
    return "\n".join(lines)


PROBE = (
    "Let me look at the context before deciding how to split it. I should check "
    "its length and the format of the first few records.\n"
    "```repl\nprint(len(context))\nprint(context[:400])\n```\n"
)

FINAL = (
    "I have what I need. Let me write the final answer from the computed results.\n"
    "```repl\nanswer['content'] = str(result)[:2000]\nanswer['ready'] = True\n```\n"
)

PROGRAMS: dict[str, str] = {
    # parametric fan-out for the free-ride sweep: K chunks of {chunk} chars
    "fanout": (
        "I will label each chunk with a sub-call and then count.\n"
        "```repl\n"
        "chunks = [context[i * {chunk}:(i + 1) * {chunk}] for i in range({k})]\n"
        "labels = []\n"
        "for c in chunks:\n"
        "    labels.append(llm_query('Label every record below as urgent or routine, one "
        "label per line with its id.\\n' + c))\n"
        "\n"
        "result = llm_query('Count urgent vs routine records and list the urgent ids:\\n' "
        "+ '\\n'.join(str(x) for x in labels))\n"
        "```\n"
    ),
    # B: fan-out over chunks, then a dependent reduce
    "rlm_map": (
        "The context is a list of support records. I will split it into chunks, label "
        "each record's urgency in every chunk with a sub-call, then aggregate.\n"
        "```repl\n"
        "chunks = [context[i:i + {chunk}] for i in range(0, len(context), {chunk})]\n"
        "labels = []\n"
        "for c in chunks:\n"
        "    labels.append(llm_query('Label every record below as urgent or routine, one "
        "label per line with its id.\\n' + c))\n"
        "\n"
        "result = llm_query('Count urgent vs routine records and list the urgent ids:\\n' "
        "+ '\\n'.join(str(x) for x in labels))\n"
        "print(result)\n"
        "```\n"
    ),
    # A + B: per-chunk extract then verify (pipelined chains)
    "rlm_two_stage": (
        "I will extract the refund requests from each chunk, then double-check each "
        "extraction with a second sub-call before aggregating.\n"
        "```repl\n"
        "chunks = [context[i:i + {chunk}] for i in range(0, len(context), {chunk})]\n"
        "checked = []\n"
        "for c in chunks:\n"
        "    found = llm_query('Extract every record about refunds, with ids:\\n' + c)\n"
        "    checked.append(llm_query('Verify this extraction and drop false positives: ' "
        "+ str(found)))\n"
        "\n"
        "result = llm_query('Merge these verified lists into one: ' + ' | '.join(str(x) "
        "for x in checked))\n"
        "```\n"
    ),
    # C + head-of-line: a branch on a pending result, with independent work after it
    "rlm_branch": (
        "First I need to know whether the records mention outages at all; that decides "
        "the analysis. The per-chunk topic extraction does not depend on it.\n"
        "```repl\n"
        "chunks = [context[i:i + {chunk}] for i in range(0, len(context), {chunk})]\n"
        "verdict = llm_query('Think step by step, then answer yes or no: do these records "
        "mention an outage?\\n' "
        "+ chunks[0])\n"
        "if 'yes' in str(verdict).lower():\n"
        "    focus = llm_query('List every outage record id and its user:\\n' + chunks[0])\n"
        "else:\n"
        "    focus = llm_query('Summarize the main complaint themes:\\n' + chunks[0])\n"
        "topics = [llm_query('Extract the topic counts from these records:\\n' + c) "
        "for c in chunks[1:]]\n"
        "result = llm_query('Write a short report from: ' + str(focus) + ' ' + "
        "' '.join(str(t) for t in topics))\n"
        "```\n"
    ),
    # the model already parallelized (RLM's llm_query_batched): speculation can only
    # overlap the batch with the rest of the stream
    "rlm_map_batched": (
        "The context is a list of support records. I will split it into chunks and label "
        "all chunks in one batched call, then aggregate.\n"
        "```repl\n"
        "chunks = [context[i:i + {chunk}] for i in range(0, len(context), {chunk})]\n"
        "labels = llm_query_batched(['Label every record below as urgent or routine, one "
        "label per line with its id.\\n' + c for c in chunks])\n"
        "result = llm_query('Count urgent vs routine records and list the urgent ids:\\n' "
        "+ '\\n'.join(str(x) for x in labels))\n"
        "print(result)\n"
        "```\n"
    ),
    # literal-friendly: searches with constant queries, then summaries
    "research": (
        "I will look up the three policies that matter, then summarize each against "
        "the records.\n"
        "```repl\n"
        "a = search('refund policy for duplicate charges')\n"
        "b = search('outage credit policy')\n"
        "c = search('account recovery steps')\n"
        "notes = [llm_query('Summarize this policy in three bullets:\\n' + str(d)) "
        "for d in [a, b, c]]\n"
        "result = llm_query('Combine into one guidance note: ' + ' '.join(str(n) for n "
        "in notes))\n"
        "```\n"
    ),
}

# expected output tokens by instruction (Qwen-class instruct models, rough)
OUTPUT_TOKENS = [
    ("label every record", 220),
    ("count urgent", 160),
    ("extract every record about refunds", 140),
    ("verify this extraction", 120),
    ("merge these verified", 220),
    ("think step by step", 150),
    ("list every outage", 120),
    ("summarize the main complaint", 140),
    ("extract the topic counts", 90),
    ("write a short report", 260),
    ("summarize this policy", 80),
    ("combine into one guidance", 200),
]


def output_weight(info: CallInfo) -> float:
    h = info.head.lower()
    for key, toks in OUTPUT_TOKENS:
        if h.startswith(key[:30]) or key in h:
            return float(toks)
    return 100.0


@dataclass
class TurnSpec:
    name: str
    trace: TurnTrace
    think_tokens: int  # prose before the text we trace (reasoning)
    exec_out_tokens: int  # REPL output appended to the next prompt


@lru_cache(maxsize=None)
def session_turns(program: str, chunk_chars: int = 8000, n_records: int = 800,
                  think: int = 200, trace_chunk: int = 4, k: int = 8) -> tuple[TurnSpec, ...]:
    ctx = make_context(max(n_records, k * chunk_chars // 60 + 10))
    body = PROGRAMS[program].replace("{chunk}", str(chunk_chars)).replace("{k}", str(k))
    t1 = compile_turn(PROBE, ctx, TOOLS, chunk=trace_chunk)
    t2 = compile_turn(body, ctx, TOOLS, chunk=trace_chunk, real_locals=t1.notes["real_locals"])
    t3 = compile_turn(FINAL, ctx, TOOLS, chunk=trace_chunk, real_locals=t2.notes["real_locals"])
    return (
        TurnSpec("probe", t1, think, 150),
        TurnSpec(program, t2, think, 200),
        TurnSpec("final", t3, think // 2, 20),
    )
