"""Replay recorded RLM sessions on a real engine: same code, same calls, same answers.

A live RLM run cannot show what a speculation policy does: the root samples, and one arm's
two repeats of a task differ by a factor of 1.9 (results/modal_h100_rlm, section 9). A
replay fixes everything but the policy:

- **The root** is a real streamed request with the message history rlms builds, forced to
  the recorded number of output tokens (`max_completion_tokens` with `ignore_eos`). The
  engine's text is thrown away: each token that arrives releases the next recorded delta.
  So the root's reply is the recorded one, at the pace this engine gives it under this
  arm's load, and its code is the recorded code.
- **A sub-call** is a real request with the recorded prompt, forced to the recorded output
  length, and returns the recorded answer. A prompt the recorded run got an error string
  for (replay_corpus.py) returns that string at once, without a request.
- **Everything between** is the campaign's own stack: rlms' loop and LM handler, spec-ptc's
  runner, and the REPL of the arm (stock rlms, spec-ptc as shipped, or the fork).

So every arm runs the same program and gets the same answers, and what differs is when
each sub-call is sent. `replay.json` says how well that held: every turn's message history
is hashed and compared with the recorded one.

A session its timeout stopped, or a recording's deadline (replay_corpus.py), is replayed up
to the turn boundary where its own turns end. There the replay hands rlms a reply that
sets the session's answer, with no request to the engine, so the session ends at the same
place in every arm, however fast the arm was. The message history of that last step is
checked like a turn's.

Two identical prompts can have different recorded answers (OOLONG repeats questions, and
answers are sampled). They are handed out in program order. For calls the program makes
itself that is the order they arrive in. A speculative call is launched in program order
but runs on its own thread, so its answer is fixed when it is launched (a subscriber on
spec-ptc's event bus) and travels with the call as a ticket in front of the prompt, which
the client takes off again before the request (spec-ptc's own `spec_fn` hook carries it).
A speculation that is evicted gives its answer back.

Run as a script by replay_campaign.py, one process per unit, so each arm can import its
own spec-ptc:

    PYTHONPATH=<pkg dir>:<spec-ptc root> python replay.py unit --arm stream --corpus <dir> \
        --out <unit dir> --base-url http://localhost:8210/v1 --model <name> --rep 1
"""

from __future__ import annotations

import argparse
import asyncio
import bisect
import hashlib
import json
import os
import re
import statistics
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
HASH_SEED = "0"  # as replay_corpus.py: recorded code iterates over sets
TICKET = re.compile(r"^\x00sptc:(\d+)\x00")
UNRECORDED_TEXT = "[replay: this call was not made in the recorded run]"
CUT_KINDS = ("timeout", "deadline")  # final.kind of a session replayed up to a turn boundary
TASK_TIMEOUT_S = 3600.0  # the campaign's 900 s would cut a fixed amount of work on a slow host
# For dry runs only: seconds each speculative launch takes on the launching thread. On the
# H100 a launch took 2 ms in a process busy with 128 calls in flight (other sessions held
# the GIL); a local run launches in 0.2 ms and would not show what that does.
LAUNCH_DELAY_S = float(os.environ.get("SPTC_REPLAY_LAUNCH_DELAY_MS", "0")) / 1000.0

# Arms. `tree` is the spec-ptc the unit's process imports; `repl` the REPL class;
# `kwargs` what the REPL is built with; `handler_width` rlms' batch width (16 if absent);
# `inflight_chars` spec-ptc's character budget (120,000 if absent); `govern`: the REPL is
# also given the engine's /metrics URL (spec_load_url), which only a unit knows.
ARMS: dict[str, dict] = {
    # stock rlms: sub-calls run when the program reaches them
    "nospec": {"tree": "stock", "repl": "stock"},
    # spec-ptc at 9b78b7d, fed by the root's stream: what the campaign called `stream`
    "stream": {"tree": "stock", "repl": "stream", "kwargs": {}},
    # the fork, scout pass on, everything else as shipped (16 calls in flight)
    "scout": {"tree": "fork", "repl": "stream",
              "kwargs": {"spec_scout": True, "spec_rlm_query": True}},
    # the fork after stage 3 (README.md): scout, 128 calls in flight, a batch launched as a batch
    "wide": {"tree": "fork", "repl": "stream",
             "kwargs": {"spec_scout": True, "spec_rlm_query": True, "spec_max_inflight": 128,
                        "spec_batch_launch": True}},
    # spec-ptc at 9b78b7d with its character budget lifted. As shipped it keeps at most
    # 120,000 characters of speculative prompts in flight per session (Budget.
    # max_inflight_chars, "the prefill-pressure control"): of three 100,000-character
    # calls launched together, one runs at a time. This arm shows what that budget holds
    # back, and what the engine does without it. spec-ptc itself is not changed: the
    # replay sets the number on the session it built.
    "stream-open": {"tree": "stock", "repl": "stream", "kwargs": {},
                    "inflight_chars": 10**9},
    # the fork with limits that follow the load: as `wide`, but the window
    # is not 128. It starts at spec-ptc's 16 and moves between 1 and 256 by what the engine
    # reports (a standing queue, the KV cache, preemptions) and by this process's own CPU;
    # long prompts are admitted against the KV cache the engine has free, in place of
    # 120,000 characters per session; and a batch goes out in requests of at most 32
    # prompts, so that the window bounds a batch of any size.
    "auto": {"tree": "fork", "repl": "stream", "govern": True,
             "kwargs": {"spec_scout": True, "spec_rlm_query": True, "spec_batch_launch": True,
                        "spec_batch_chunk": 32, "spec_govern": True}},
    # `auto`, and the scout goes on past a test on a result when no arm of the test can
    # leave the loop it is in
    "auto-past": {"tree": "fork", "repl": "stream", "govern": True,
                  "kwargs": {"spec_scout": "past", "spec_rlm_query": True,
                             "spec_batch_launch": True, "spec_batch_chunk": 32,
                             "spec_govern": True}},
    # controls
    # `wide` with the scout going on past such tests: what that alone adds at a fixed window
    "wide-past": {"tree": "fork", "repl": "stream",
                  "kwargs": {"spec_scout": "past", "spec_rlm_query": True,
                             "spec_max_inflight": 128, "spec_batch_launch": True}},
    # the fork at a fixed window of 128 with spec-ptc's character budget lifted: what long
    # prompts do to the engine when nothing holds them back
    "wide-open": {"tree": "fork", "repl": "stream", "inflight_chars": 10**9,
                  "kwargs": {"spec_scout": True, "spec_rlm_query": True,
                             "spec_max_inflight": 128, "spec_batch_launch": True}},
    # the same window with one thread per prompt: what launching a batch as a batch changes
    "wide-threads": {"tree": "fork", "repl": "stream",
                     "kwargs": {"spec_scout": True, "spec_rlm_query": True,
                                "spec_max_inflight": 128}},
    # no speculation, rlms' own batches 128 wide: what the width alone does
    "nospec-wide": {"tree": "stock", "repl": "stock", "handler_width": 128},
}


def sha(obj) -> str:
    """As replay_corpus.sha."""
    if not isinstance(obj, str):
        obj = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(obj.encode("utf-8", "surrogatepass")).hexdigest()


class ReplayDivergence(RuntimeError):
    """The replay left the recorded session (more turns, or another ending)."""


class ReplayedError(Exception):
    """An error the recorded run got for this prompt. rlms turns it back into the string
    the program saw."""


# --------------------------------------------------------------------------- outcomes
class Outcomes:
    """One session's recorded sub-call outcomes, handed out in program order."""

    def __init__(self, calls: dict[str, list[dict]]) -> None:
        self.calls = calls
        self.free: dict[str, list[int]] = {}  # per prompt: indices not handed out yet
        self.bound: dict[int, tuple[str, int, dict]] = {}  # speculation -> its outcome
        self.lock = threading.Lock()
        ns = sorted(o["n"] for outs in calls.values() for o in outs if "n" in o)
        self.default_n = ns[len(ns) // 2] if ns else 8
        self.unrecorded = 0  # calls for a prompt the recorded run never sent
        self.repeats = 0  # calls beyond the number recorded for their prompt
        self.released = 0  # outcomes given back by evicted speculations

    def _next(self, prompt: str) -> tuple[int, dict]:
        outs = self.calls.get(prompt)
        if outs is None:
            self.unrecorded += 1
            return -1, {"r": UNRECORDED_TEXT, "n": self.default_n, "u": True}
        free = self.free.get(prompt)
        if free is None:
            free = self.free[prompt] = list(range(len(outs)))
        if free:
            i = free.pop(0)
            return i, outs[i]
        self.repeats += 1
        return -1, outs[-1]

    def take(self, prompt: str) -> dict:
        """A call the program makes itself: the next outcome recorded for its prompt."""
        with self.lock:
            return self._next(prompt)[1]

    def bind(self, seq: int, prompt: str) -> None:
        """A speculative launch. Launches happen in program order, so this one's outcome
        is fixed now, whenever its thread gets to run."""
        with self.lock:
            i, out = self._next(prompt)
            self.bound[seq] = (prompt, i, out)

    def claim(self, seq: int, prompt: str) -> dict:
        """The launched call asks for the outcome fixed at its launch."""
        with self.lock:
            b = self.bound.get(seq)
            if b is not None and b[0] == prompt:
                return b[2]
            return self._next(prompt)[1]

    def release(self, seq: int) -> None:
        """An evicted speculation: the program never used its answer, so it is the next
        one for that prompt again."""
        with self.lock:
            b = self.bound.pop(seq, None)
            if b is not None and b[1] >= 0:
                bisect.insort(self.free.setdefault(b[0], []), b[1])
                self.released += 1


class Session:
    """A corpus session being replayed by one task thread."""

    def __init__(self, data: dict, salt: str) -> None:
        self.name: str = data["session"]
        self.turns: list[dict] = data["turns"]
        self.final: dict = data["final"]
        self.source: dict = data.get("source") or {}
        self.outcomes = Outcomes(data["calls"])
        self.salt = salt  # in front of every prompt sent: no prefix-cache hit across units
        self.k = 0
        self.lock = threading.Lock()
        self.sink: Any = None
        self.turn_log: list[dict] = []
        self.diverged: str | None = None
        self.calls = self.errors = 0

    def next_turn(self) -> tuple[int, dict | None]:
        with self.lock:
            k = self.k
            self.k += 1
        return k, (self.turns[k] if k < len(self.turns) else None)

    def log_call(self, **rec) -> None:
        with self.lock:
            if rec.get("err"):
                self.errors += 1
            else:
                self.calls += 1
        if self.sink is not None:
            self.sink.log("replay_call", task_id=self.name, **rec)


_ctx = threading.local()


def bind(session: Session, sink: Any) -> None:
    session.sink = sink
    _ctx.session = session


def unbind() -> None:
    if hasattr(_ctx, "session"):
        del _ctx.session


def current() -> Session:
    s = getattr(_ctx, "session", None)
    if s is None:
        raise RuntimeError("no replay session bound to this thread")
    return s


def split_ticket(prompt: str) -> tuple[int | None, str]:
    m = TICKET.match(prompt)
    return (int(m.group(1)), prompt[m.end():]) if m else (None, prompt)


def ticket(seq: int) -> str:
    return f"\x00sptc:{seq}\x00"


# --------------------------------------------------------------------------- the client
def make_client_class():
    """ReplayClient, built here because rlms is imported by the unit, not by this module's
    importers (replay_campaign.py runs without it)."""
    import openai
    from rlm.clients.openai import OpenAIClient, _merge_extra_body, _normalize_sampling_args

    class ReplayClient(OpenAIClient):
        """rlms' OpenAI client, replaying. One per task and role (root, sub-calls)."""

        def __init__(self, session: Session, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.session = session
            # rlms runs each llm_query_batched in a new event loop, and an async client
            # must not be used from a loop other than its own (that is the bug behind
            # 'Event loop is closed'). Batch requests are therefore sent from one loop of
            # this client's own, on its own thread, which keeps its connections.
            self._loop: asyncio.AbstractEventLoop | None = None
            self._aclient: Any = None
            self._loop_lock = threading.Lock()

        # ---- requests
        def _args(self, content: str, n: int) -> dict:
            args = _normalize_sampling_args(self.sampling_args)
            args.pop("max_completion_tokens", None)
            extra = _merge_extra_body({}, self.sampling_args)
            extra["ignore_eos"] = True  # exactly n tokens, as recorded
            return {"model": self.model_name, "max_completion_tokens": max(1, int(n)),
                    "messages": [{"role": "user", "content": self.session.salt + content}],
                    "extra_body": extra, **args}

        def _http_loop(self) -> asyncio.AbstractEventLoop:
            with self._loop_lock:
                if self._loop is None:
                    self._loop = asyncio.new_event_loop()
                    threading.Thread(target=self._loop.run_forever, daemon=True,
                                     name="replay-http").start()
                return self._loop

        async def _send(self, args: dict):
            if self._aclient is None:  # made on its loop, used on its loop only
                # Built as rlms builds its own (OpenAIClient.__init__): the SDK's default
                # connection pool. Not a detail: with 256 keep-alive connections in
                # place of the default 100, httpx's async pool fell to 50 calls a second
                # at 128 in flight, where the default does 130 (measured, 2026-11-10).
                self._aclient = openai.AsyncOpenAI(
                    api_key=self.client.api_key, base_url=self.base_url, timeout=self.timeout)
            return await self._aclient.chat.completions.create(**args)

        def _outcome(self, prompt: str) -> tuple[int | None, str, dict]:
            seq, text = split_ticket(prompt)
            out = (self.session.outcomes.take(text) if seq is None
                   else self.session.outcomes.claim(seq, text))
            return seq, text, out

        def _note(self, t0: float, p0: float, path: str, seq, out: dict, usage=None) -> None:
            self.session.log_call(
                t0=round(t0, 4), ms=round(1000 * (time.perf_counter() - p0), 1), path=path,
                spec=seq, err="e" in out, unrec=bool(out.get("u")), n=out.get("n"),
                pt=getattr(usage, "prompt_tokens", None),
                ct=getattr(usage, "completion_tokens", None))

        # ---- sub-calls
        def completion(self, prompt, model=None):  # type: ignore[override]
            if not isinstance(prompt, str):
                return self._final_answer(prompt)
            seq, text, out = self._outcome(prompt)
            t0, p0 = time.time(), time.perf_counter()
            if "e" in out:
                self._note(t0, p0, "single", seq, out)
                # rlms' handler sends str(e) back and the REPL puts 'Error: ' in front
                raise ReplayedError(out["e"].removeprefix("Error: "))
            resp = self.client.chat.completions.create(**self._args(text, out["n"]))
            self._track_cost(resp, self.model_name)
            self._note(t0, p0, "single", seq, out, resp.usage)
            return out["r"]

        async def acompletion(self, prompt, model=None):  # type: ignore[override]
            seq, text, out = self._outcome(prompt)
            t0, p0 = time.time(), time.perf_counter()
            if "e" in out:
                self._note(t0, p0, "batch", seq, out)
                # in a batch rlms writes 'llm() call failed - ' + str(e) itself
                raise ReplayedError(out["e"].removeprefix("Error: ")
                                    .removeprefix("llm() call failed - "))
            fut = asyncio.run_coroutine_threadsafe(self._send(self._args(text, out["n"])),
                                                   self._http_loop())
            resp = await asyncio.wrap_future(fut)
            self._track_cost(resp, self.model_name)
            self._note(t0, p0, "batch", seq, out, resp.usage)
            return out["r"]

        # ---- the root's last, unstreamed call (out of iterations)
        def _final_answer(self, messages: list[dict]) -> str:
            s = self.session
            final = s.final
            if final.get("kind") != "default_answer":
                s.diverged = "ran out of iterations; the recorded session ended with an answer"
                raise ReplayDivergence(f"{s.name}: {s.diverged}")
            match = sha(messages) == final.get("prompt_sha")
            t0 = time.perf_counter()
            resp = self.client.chat.completions.create(
                model=self.model_name, messages=salted(messages, s.salt),
                max_completion_tokens=max(1, int(final.get("tokens") or 1)),
                extra_body={"ignore_eos": True})
            self._track_cost(resp, self.model_name)
            s.turn_log.append({"turn": "final", "prompt_match": match,
                               "s": round(time.perf_counter() - t0, 3)})
            return final["text"]

    return ReplayClient


def salted(messages: list[dict], salt: str) -> list[dict]:
    """The message history with the unit's salt in front of its first message."""
    if not salt or not messages:
        return messages
    first = dict(messages[0])
    first["content"] = salt + str(first.get("content", ""))
    return [first, *messages[1:]]


# --------------------------------------------------------------------------- the root
def stream_root(client: Any, prompt: str | list[dict], on_delta=None) -> tuple[str, dict]:
    """rlm_stream.stream_root, replaying: (the recorded reply, this engine's timing).

    The request is the one the stock call sends, plus a forced length. A recorded delta is
    released for each token the engine has produced (its running usage count, so a token
    with no text of its own still counts), and the rest when the stream ends."""
    from rlm.clients.openai import _merge_extra_body, _normalize_sampling_args

    s: Session = client.session
    k, rec = s.next_turn()
    messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
    if rec is None and k == len(s.turns) and s.final.get("kind") in CUT_KINDS:
        return end_of_cut_session(s, messages)
    if rec is None:
        s.diverged = f"asked for turn {k + 1}; the recorded session has {len(s.turns)}"
        raise ReplayDivergence(f"{s.name}: {s.diverged}")
    match = sha(messages) == rec["prompt_sha"]
    reply, cuts = rec["reply"], rec["cuts"]
    args = _normalize_sampling_args(client.sampling_args)
    args.pop("max_completion_tokens", None)
    extra = _merge_extra_body({}, client.sampling_args)
    extra["ignore_eos"] = True

    t_wall = time.time()
    t0 = time.perf_counter()
    stream = client.client.chat.completions.create(
        model=client.model_name, messages=salted(messages, s.salt), extra_body=extra,
        stream=True, stream_options={"include_usage": True, "continuous_usage_stats": True},
        max_completion_tokens=max(1, int(rec["tokens"])), **args)
    arrivals: list[list] = []
    released = seen = 0
    usage = None
    t_first = t_last = None

    def release(upto: int, now: float) -> None:
        nonlocal released
        while released < upto:
            a = cuts[released - 1] if released else 0
            b = cuts[released]
            released += 1
            arrivals.append([round(1000 * (now - t0), 1), b])
            if on_delta is not None:
                on_delta(reply[a:b])

    for chunk in stream:
        u = getattr(chunk, "usage", None)
        if u is not None:
            usage = u
            now_seen = int(u.completion_tokens or 0)
        elif chunk.choices and getattr(chunk.choices[0].delta, "content", None):
            now_seen = seen + 1  # a server without running usage counts: one chunk, one token
        else:
            continue
        if now_seen > seen:
            now = time.perf_counter()
            if t_first is None:
                t_first = now
            t_last = now
            seen = now_seen
            release(min(seen, len(cuts)), now)
    t_end = time.perf_counter()
    release(len(cuts), t_end)  # deltas the engine's token count did not reach
    if usage is None:
        usage = SimpleNamespace(prompt_tokens=0, completion_tokens=seen, total_tokens=seen)
    client._track_cost(SimpleNamespace(usage=usage), client.model_name)
    tokens = int(usage.completion_tokens or 0)
    s.turn_log.append({"turn": k + 1, "prompt_match": match, "tokens": tokens,
                       "rec_tokens": rec["tokens"]})
    timing = {
        "t_start": round(t_wall, 4),
        "ttft_s": None if t_first is None else round(t_first - t0, 4),
        "stream_s": round(t_end - t0, 4),
        "tokens": tokens,
        "prompt_tokens": int(usage.prompt_tokens or 0),
        "truncated": False,
        "n_deltas": len(arrivals),
        "tpot_ms": (round(1000 * (t_last - t_first) / (tokens - 1), 3)
                    if t_first is not None and t_last is not None and tokens > 1 else None),
        "arrivals": arrivals,
        "prompt_match": match,  # this turn's message history is the recorded one
        "rec_tokens": rec["tokens"],
    }
    return reply, timing


def end_of_cut_session(s: Session, messages: list[dict]) -> tuple[str, dict]:
    """The step after the last replayed turn of a session that was stopped (CUT_KINDS). No
    request is sent and nothing is fed to the shadow: the reply only sets the session's
    answer, so rlms ends the session here. `messages` is what the next turn's root would
    have been sent, and its hash is in the corpus: that checks the last turn's output."""
    match = sha(messages) == s.final.get("prompt_sha")
    s.turn_log.append({"turn": "end", "prompt_match": match})
    reply = f"```repl\nanswer['content'] = {s.final['text']!r}\nanswer['ready'] = True\n```\n"
    timing = {"t_start": round(time.time(), 4), "ttft_s": None, "stream_s": 0.0, "tokens": 0,
              "prompt_tokens": 0, "truncated": False, "n_deltas": 0, "tpot_ms": None,
              "arrivals": [], "prompt_match": match, "rec_tokens": 0,
              "synthetic": True}  # not a turn of the session: reports leave it out
    return reply, timing


# --------------------------------------------------------------------------- the REPL
def _tagged_single(fn):
    def call(prompt, model=None, _spec=None):
        return fn(prompt if _spec is None else ticket(_spec.seq) + prompt)

    call.wants_spec = True  # type: ignore[attr-defined]
    return call


def _tagged_batch(fn):
    def call(prompts, model=None, _spec=None):
        if _spec is None:
            return fn(prompts)
        return fn([ticket(sp.seq) + p for p, sp in zip(prompts, _spec, strict=True)])

    call.wants_spec = True  # type: ignore[attr-defined]
    return call


def spec_repl_class(base, arm_kwargs: dict, inflight_chars: int | None = None):
    """The arm's speculative REPL, with the two things a replay adds: each launch fixes its
    recorded outcome (bus subscriber), and each speculative call carries its ticket."""

    class ReplayREPL(base):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            for k, v in arm_kwargs.items():
                kwargs.setdefault(k, v)
            super().__init__(*args, **kwargs)
            if inflight_chars:  # the arm's character budget, in place of spec-ptc's own
                self.spec_launcher.budget.max_inflight_chars = int(inflight_chars)
            self._replay = current()
            self.bus.subscribe(self._replay_event)
            for name in ("llm_query", "rlm_query"):
                tool = self.reg.get(name)
                if tool is not None and tool.speculatable:
                    tool.spec_fn = _tagged_single(tool.fn)
            for name in ("llm_query_batched", "rlm_query_batched"):
                tool = self.reg.get(name)
                if tool is not None and tool.speculatable:
                    tool.spec_fn = _tagged_batch(tool.fn)

        def _replay_event(self, ev) -> None:
            if ev.kind == "dispatch":
                if LAUNCH_DELAY_S:
                    time.sleep(LAUNCH_DELAY_S)
                seq = ev.data.get("seq")
                for spec in reversed(self.spec_store.all):
                    if spec.seq == seq:
                        self._replay.outcomes.bind(seq, spec.args[0])
                        break
            elif ev.kind == "evict":
                self._replay.outcomes.release(ev.data.get("seq"))

    ReplayREPL.__name__ = f"Replay{base.__name__}"
    return ReplayREPL


# --------------------------------------------------------------------------- one unit
def tree_hash(root: Path) -> tuple[str, int]:
    """sha256 over a spec-ptc tree's Python sources (as rlm_campaign.provenance)."""
    tree = hashlib.sha256()
    n = 0
    for p in sorted(Path(root).rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        if "__pycache__" in rel or rel.startswith((".venv", "tests/")):
            continue
        tree.update(f"{rel}\0{hashlib.sha256(p.read_bytes()).hexdigest()}\n".encode())
        n += 1
    return tree.hexdigest(), n


def run_unit(a) -> dict:
    arm = ARMS[a.arm]
    spec_root = Path(os.environ["SPEC_PTC_ROOT"])
    for p in (str(spec_root), str(HERE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        want = 65536 if hard == resource.RLIM_INFINITY else min(hard, 65536)
        if soft < want:
            resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
    except Exception:  # noqa: BLE001 - best effort
        pass

    import benchmark.oolong_campaign.runner as runner
    import repl_fix
    import replay_corpus
    import rlm.core.rlm as rlm_core
    import rlm.environments as rlm_envs
    import rlm_campaign
    import rlm_stream
    import spec_ptc
    from benchmark.oolong_campaign.data import Task

    here = Path(spec_ptc.__file__).resolve()
    if spec_root.resolve() not in here.parents:
        raise SystemExit(f"spec_ptc was imported from {here}, not from {spec_root}")
    repl_fix.apply()
    if arm.get("handler_width"):
        rlm_stream.HANDLER_BATCH_WIDTH = int(arm["handler_width"])

    client_cls = make_client_class()
    rlm_core.get_client = lambda backend, kwargs: client_cls(current(), **(kwargs or {}))
    rlm_stream.stream_root = stream_root
    runner.RLM = rlm_stream.StreamingRLM
    stock = runner._STOCK_LOCAL_REPL
    if arm["repl"] == "stock":
        repl_cls = stock
    else:
        kwargs = dict(arm.get("kwargs") or {})
        if arm.get("govern"):  # the engine's /metrics, next to its /v1
            kwargs["spec_load_url"] = a.base_url.rstrip("/").removesuffix("/v1") + "/metrics"
        repl_cls = spec_repl_class(rlm_stream.StreamingSpecREPL, kwargs,
                                   arm.get("inflight_chars"))

    def set_spec(enabled: bool) -> None:
        cls = repl_cls if enabled else stock
        rlm_envs.LocalREPL = cls
        rlm_envs.local_repl.LocalREPL = cls

    runner._set_speculation = set_spec

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    data = replay_corpus.load_corpus(a.corpus, a.sessions)
    salt = f"[{a.salt}] " if a.salt else ""
    sessions = {d["session"]: Session(d, salt) for d in data}
    tasks = [Task(**d["task"]) for d in data]
    orig_run_task = runner._run_task

    def run_task(task, model, base_url, spec, log, outdir, **kw):
        s = sessions[task.task_id]
        bind(s, log)
        rlm_stream.bind_task(task.task_id, log)
        try:
            kw.setdefault("max_timeout", TASK_TIMEOUT_S)
            return orig_run_task(task, model, base_url, spec, log, outdir, **kw)
        finally:
            rlm_stream.unbind_task()
            unbind()

    runner._run_task = run_task
    poller = rlm_campaign.Poller(a.base_url.rsplit("/v1", 1)[0], out / "metrics.csv",
                                 a.metrics_every)
    poller.start()
    t0 = time.time()
    try:
        stats = runner.run_unit(a.model, a.base_url, arm["repl"] != "stock", a.conc, a.rep,
                                tasks, out)
    finally:
        poller.stop()
    t1 = time.time()

    rows = {t["task_id"]: t for t in stats.get("tasks", [])}
    fidelity = []
    for name, s in sessions.items():
        row = rows.get(name, {})
        turns = [t for t in s.turn_log if t["turn"] not in ("final", "end")]
        want = s.final["text"]
        fidelity.append({
            "session": name, "ok": bool(row.get("ok")), "error": (row.get("error") or "")[:200],
            "cut": s.final.get("kind") in CUT_KINDS,
            "turns": len(turns), "rec_turns": len(s.turns),
            "prompt_matches": sum(1 for t in s.turn_log if t["prompt_match"]),
            "prompts": len(s.turn_log),
            "answer_match": bool(row.get("ok")) and row.get("final_answer") == str(want)[:300],
            "score": row.get("score"), "rec_score": s.source.get("score"),
            "calls": s.calls, "errors": s.errors, "unrecorded": s.outcomes.unrecorded,
            "repeats": s.outcomes.repeats, "released": s.outcomes.released,
            "diverged": s.diverged, "wall_s": row.get("wall_s"),
        })
    exact = all(f["ok"] and f["turns"] == f["rec_turns"] and f["prompt_matches"] == f["prompts"]
                and f["answer_match"] and not f["diverged"] for f in fidelity)
    th, tn = tree_hash(spec_root)
    unit = {"arm": a.arm, "conc": a.conc, "rep": a.rep, "t0": t0, "t1": t1,
            "tasks": [t.task_id for t in tasks], "arm_config": arm, "salt": a.salt,
            "spec_ptc": str(spec_root), "spec_ptc_file": str(here), "spec_ptc_py_tree": th,
            "spec_ptc_py_files": tn, "hash_seed": os.environ.get("PYTHONHASHSEED"),
            "exact": exact}
    (out / "replay.json").write_text(json.dumps({"exact": exact, "sessions": fidelity}, indent=1))
    (out / "unit.json").write_text(json.dumps(unit, indent=1))
    if (out / "rlm_trajs").is_dir():
        rlm_campaign.compact_unit(out)
    (out / "DONE").write_text(str(t1))
    walls = [f["wall_s"] for f in fidelity if f["wall_s"]]
    print(f"{out.name}: {t1 - t0:.0f} s, session wall p50 "
          f"{statistics.median(walls) if walls else 0:.0f} s, errors {stats.get('n_errors')}, "
          f"{'exact' if exact else 'NOT EXACT'}", flush=True)
    return unit


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("unit")
    u.add_argument("--arm", required=True, choices=sorted(ARMS))
    u.add_argument("--corpus", type=Path, required=True)
    u.add_argument("--sessions", type=lambda s: s.split(","), default=None)
    u.add_argument("--out", type=Path, required=True)
    u.add_argument("--base-url", required=True)
    u.add_argument("--model", required=True)
    u.add_argument("--conc", type=int, default=8)
    u.add_argument("--rep", type=int, default=1)
    u.add_argument("--salt", default="")
    u.add_argument("--metrics-every", type=float, default=0.5)
    return ap


def main(argv=None) -> None:
    a = parser().parse_args(argv)
    if os.environ.get("PYTHONHASHSEED") != HASH_SEED:
        raise SystemExit(f"run with PYTHONHASHSEED={HASH_SEED} (replay_campaign.py does)")
    if not os.environ.get("SPEC_PTC_ROOT"):
        raise SystemExit("SPEC_PTC_ROOT must name the arm's spec-ptc checkout")
    run_unit(a)
    # The unit's files are written. Leave without waiting for the clients' worker threads:
    # one that still waits for a place or for room (spec-ptc lets it wait 600 s) would
    # keep a finished unit, and a paid engine, waiting with it.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
