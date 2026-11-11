"""Streamed root completions for rlms 0.1.3, so spec-ptc can speculate while the root writes.

Stock rlms (0.1.3, the latest on PyPI, and rlm's main branch as of 2026-11-08) calls the
root model without streaming, then runs the reply's ```repl blocks one by one. spec-ptc's
SpeculativeLocalREPL therefore runs its shadow over each finished block just before
executing it (spec-ptc demo/rlm.py, execute_code): a block's sub-calls run in parallel,
but never overlap the root's generation. That is the mode spec-ptc's OOLONG campaign measured.

This module adds the streaming mode without changing rlms or spec-ptc:

- StreamingRLM: an rlm.RLM whose turn streams the root completion with the request the
  stock client would send (same messages, extra_body and sampling args), records the root's
  token timing, and, when the REPL is a StreamingSpecREPL, feeds every text delta to
  spec-ptc's stream turn as it arrives.
- StreamingSpecREPL: a SpeculativeLocalREPL with no per-block shadow pre-pass (the stream
  feeds the shadow) that, while a streamed turn is open, does not end spec-ptc's turn after
  each block. Stock rlms runs blocks one at a time, and ending the turn after the first
  block would evict the speculations of the blocks after it.

Every arm of the campaign uses StreamingRLM, so root timing is measured the same way in
each; only the stream arm feeds spec-ptc. The text the root returns is the concatenation
of the streamed deltas, which is what the non-streamed call returns.

Needs spec-ptc's repository root on sys.path (for demo.rlm), or SPEC_PTC_ROOT set.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any

_root = os.environ.get("SPEC_PTC_ROOT")
if _root and _root not in sys.path:
    sys.path.insert(0, _root)

from demo.rlm import SpeculativeLocalREPL  # noqa: E402  (spec-ptc's RLM REPL)
from rlm import RLM  # noqa: E402
from rlm.clients.openai import (  # noqa: E402
    DEFAULT_PRIME_INTELLECT_BASE_URL,
    _merge_extra_body,
    _normalize_sampling_args,
)
from rlm.core.types import CodeBlock, RLMIteration  # noqa: E402
from rlm.utils.parsing import find_code_blocks  # noqa: E402

SHADOW_TIMEOUT_S = 600.0  # SpeculativeLocalREPL.end_stream_turn's default
# A root reply is cut after this many deltas (about one token each; 0: never). rlms sets
# no max_tokens on the root, so with a large --max-model-len a root stuck repeating itself
# writes until the window is full: on 2026-11-09 one did so for 30 minutes (65,536-token
# window, 53 ms per token), and its unit waited for it. The longest healthy reply in these
# runs was about 1,000 tokens.
ROOT_MAX_DELTAS = int(os.environ.get("SPTC_ROOT_MAX_DELTAS", "3000"))
# rlms' LM handler keeps 16 prompts of one llm_query_batched in flight
# (LMHandler.batch_max_concurrent; RLM() has no argument for it). 0 leaves that alone; a
# number sets it for every task of the process, whatever the REPL (a control arm: rlms'
# own batches, wider, with no speculation).
HANDLER_BATCH_WIDTH = int(os.environ.get("SPTC_HANDLER_BATCH_WIDTH", "0"))
# The handler's socket server listens with Python's default backlog of 5 connections. A
# number sets it for handlers started after this module is imported (0: leave it).
HANDLER_BACKLOG = int(os.environ.get("SPTC_HANDLER_BACKLOG", "0"))
if HANDLER_BACKLOG:
    from rlm.core.lm_handler import ThreadingLMServer

    ThreadingLMServer.request_queue_size = HANDLER_BACKLOG

# --------------------------------------------------------------------------- task context
_ctx = threading.local()


def bind_task(task_id: str, sink: Any) -> None:
    """Route this thread's root-stream records to sink.log(kind, **data) (a TrajectoryLogger)."""
    _ctx.task_id, _ctx.sink, _ctx.iteration = task_id, sink, 0


def unbind_task() -> None:
    for k in ("task_id", "sink", "iteration"):
        if hasattr(_ctx, k):
            delattr(_ctx, k)


def _record(rec: dict) -> None:
    sink = getattr(_ctx, "sink", None)
    if sink is None:
        return
    _ctx.iteration += 1
    sink.log("root_stream", task_id=_ctx.task_id, iteration=_ctx.iteration, **rec)


# --------------------------------------------------------------------------- the root call
def stream_root(client: Any, prompt: str | list[dict], on_delta=None) -> tuple[str, dict]:
    """rlms OpenAIClient.completion, streamed. Returns (text, timing).

    Same request as the stock call (rlm/clients/openai.py, completion), plus stream=True and
    stream_options.include_usage; usage is tracked with the client's own _track_cost.
    """
    if isinstance(prompt, str):
        messages = [{"role": "user", "content": prompt}]
    elif isinstance(prompt, list) and all(isinstance(m, dict) for m in prompt):
        messages = prompt
    else:
        raise ValueError(f"Invalid prompt type: {type(prompt)}")
    model = client.model_name
    if not model:
        raise ValueError("Model name is required for OpenAI client.")
    extra_body: dict[str, Any] = {}
    if client.client.base_url == DEFAULT_PRIME_INTELLECT_BASE_URL:
        extra_body["usage"] = {"include": True}
    extra_body = _merge_extra_body(extra_body, client.sampling_args)

    t_wall = time.time()
    t0 = time.perf_counter()
    stream = client.client.chat.completions.create(
        model=model,
        messages=messages,
        extra_body=extra_body,
        stream=True,
        stream_options={"include_usage": True},
        **_normalize_sampling_args(client.sampling_args),
    )
    parts: list[str] = []
    usage = None
    t_first = t_last = None
    n_deltas = 0
    n_chars = 0
    truncated = False
    arrivals: list[list] = []  # per delta: [ms since the request was sent, characters so far]
    for chunk in stream:
        if getattr(chunk, "usage", None) is not None:
            usage = chunk.usage
        if not chunk.choices:
            continue
        text = getattr(chunk.choices[0].delta, "content", None)
        if not text:
            continue
        now = time.perf_counter()
        if t_first is None:
            t_first = now
        t_last = now
        n_deltas += 1
        n_chars += len(text)
        arrivals.append([round(1000 * (now - t0), 1), n_chars])
        parts.append(text)
        if on_delta is not None:
            on_delta(text)
        if ROOT_MAX_DELTAS and n_deltas >= ROOT_MAX_DELTAS:
            truncated = True
            stream.close()  # the server aborts the request
            break
    t_end = time.perf_counter()
    if usage is None and not truncated:  # the stock call raises too (_track_cost needs usage)
        raise ValueError("No usage data received. Tracking tokens not possible.")
    if usage is None:  # cut before the usage chunk: count what arrived
        usage = SimpleNamespace(prompt_tokens=0, completion_tokens=n_deltas,
                                total_tokens=n_deltas)
    client._track_cost(SimpleNamespace(usage=usage), model)

    tokens = int(usage.completion_tokens or 0)
    timing = {
        "t_start": round(t_wall, 4),
        "ttft_s": None if t_first is None else round(t_first - t0, 4),
        "stream_s": round(t_end - t0, 4),
        "tokens": tokens,
        "prompt_tokens": int(usage.prompt_tokens or 0),
        "truncated": truncated,  # cut at ROOT_MAX_DELTAS (prompt_tokens is then unknown: 0)
        "n_deltas": n_deltas,
        # time per output token after the first, as vLLM defines TPOT
        "tpot_ms": (
            round(1000 * (t_last - t_first) / (tokens - 1), 3)
            if t_first is not None and t_last is not None and tokens > 1
            else None
        ),
        # when each piece of the reply arrived: with the reply's text (rlm_trajs), this
        # gives the time any call in the code finished streaming
        "arrivals": arrivals,
    }
    return "".join(parts), timing


# --------------------------------------------------------------------------- REPL and RLM
class StreamingSpecREPL(SpeculativeLocalREPL):
    """spec-ptc's RLM REPL for a streamed root: no per-block pre-pass, one turn per reply."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["auto_speculate"] = False  # the stream feeds the shadow instead
        self._streamed_turn_open = False  # LocalREPL.__init__ already runs code (the context load)
        super().__init__(*args, **kwargs)

    def open_streamed_turn(self) -> None:
        self.begin_stream_turn()
        self._streamed_turn_open = True

    def close_stream(self, timeout: float = SHADOW_TIMEOUT_S) -> None:
        """The root finished: flush the segmenter and wait for the shadow (spec-ptc's order:
        the real run starts after the stream ends and the shadow finishes)."""
        self.end_stream_turn(timeout)

    def finish_turn(self) -> None:
        """After the reply's last block: evict unclaimed speculations, reset the budget."""
        self._streamed_turn_open = False
        if self._turn is not None:  # the stream failed before close_stream
            self.end_stream_turn(SHADOW_TIMEOUT_S)
        self.session.end_turn()

    def execute_code(self, code: str):  # type: ignore[override]
        if self._streamed_turn_open:
            # LocalREPL's own execute_code, past SpeculativeLocalREPL's: the REPL's hooks
            # still claim the stream's speculations, but the turn stays open for the next
            # block (SpeculativeLocalREPL would end it here)
            return super(SpeculativeLocalREPL, self).execute_code(code)
        return super().execute_code(code)


class StreamingRLM(RLM):
    """rlm.RLM with a streamed root call (rlms 0.1.3 RLM._completion_turn otherwise)."""

    def _completion_turn(self, prompt, lm_handler, environment) -> RLMIteration:  # type: ignore[override]
        iter_start = time.perf_counter()
        client = lm_handler.get_client()  # depth 0: the root's client
        if HANDLER_BATCH_WIDTH:
            lm_handler.batch_max_concurrent = HANDLER_BATCH_WIDTH
        follow = getattr(environment, "follow_window", None)
        if follow is not None:  # the sptc-hints fork: a batch as wide as the REPL's window
            follow(lm_handler)
        fed = isinstance(environment, StreamingSpecREPL)
        if fed:
            environment.open_streamed_turn()
        try:
            response, timing = stream_root(client, prompt, environment.feed if fed else None)
            t_stream_end = time.perf_counter()
            if fed:
                environment.close_stream()
            t_exec = time.perf_counter()
            code_blocks = []
            for code_block_str in find_code_blocks(response):
                code_result = environment.execute_code(code_block_str)
                code_blocks.append(CodeBlock(code=code_block_str, result=code_result))
        finally:
            if fed:
                environment.finish_turn()
        t_done = time.perf_counter()
        iteration_time = t_done - iter_start
        _record({
            **timing,
            "fed": fed,
            "shadow_wait_s": round(t_exec - t_stream_end, 4),  # 0 unless fed
            "exec_s": round(t_done - t_exec, 4),
            "iteration_s": round(iteration_time, 4),
            "n_blocks": len(code_blocks),
        })
        return RLMIteration(
            prompt=prompt,
            response=response,
            code_blocks=code_blocks,
            iteration_time=iteration_time,
        )
