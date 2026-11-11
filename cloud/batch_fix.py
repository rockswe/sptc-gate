"""Make rlms 0.1.3's llm_query_batched answer every prompt.

rlms runs each batch in a new event loop (rlm/core/lm_handler.py, _handle_batched:
asyncio.run), but its OpenAI client keeps one async HTTP client for all of them
(rlm/clients/openai.py, OpenAIClient.__init__). The connections that client keeps alive
belong to the loop of the batch that opened them. The next batch runs in another loop, is
handed those connections first, and every prompt that gets one comes back as the string

    Error: llm() call failed - Event loop is closed

16 or 4 of every batch of 20 after a session's first, in the H100 runs of November 9 (30%
of one unit's batched prompts; results/modal_h100_rlm/RESULTS.md, Corrections 3). The
model's code counts those strings as labels, and one root gave up on batches because of
them. rlm's main branch has the same two files on November 10, 2026.

apply() changes one thing: where a client's async requests run. The stock coroutine
(OpenAIClient.acompletion, unchanged) is run on an event loop that belongs to the client
and lives as long as it does, on a thread of its own. The batch's loop only waits for the
result. So the async HTTP client is used from one loop for its whole life, which is what
it needs, and its connections stay usable from batch to batch. Nothing else moves: the
request is the stock one, and rlms' own semaphore still keeps 16 prompts of a batch in
flight (LMHandler.batch_max_concurrent).

The replay's client has done the same since November 10 (replay.py, ReplayClient).

probe() sends batches through rlms' own path against a running engine and counts the
prompts that came back as an error string. A recording runs it before its first unit,
with and without the fix (rlm_record.py).
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
import weakref
from collections import Counter

from rlm.clients.openai import OpenAIClient

LOOP_ERROR = "Event loop is closed"
STOCK = OpenAIClient.acompletion

_lock = threading.Lock()
_stats: dict = {"calls": 0, "failed": Counter()}


# --------------------------------------------------------------------------- the client's loop
def _serve(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    finally:
        loop.close()


def _shutdown(loop: asyncio.AbstractEventLoop, aclient) -> None:
    """The client is gone: close its connections on their loop, then end the loop."""

    async def close() -> None:
        try:
            await aclient.close()
        except Exception:  # noqa: BLE001 - nothing is waiting for these connections
            pass
        loop.stop()

    try:
        asyncio.run_coroutine_threadsafe(close(), loop)
    except RuntimeError:  # the loop is closed already
        pass


def loop_of(client: OpenAIClient) -> asyncio.AbstractEventLoop:
    """The event loop that runs this client's async requests (started on first use)."""
    loop = getattr(client, "_sptc_loop", None)
    if loop is None:
        with _lock:
            loop = getattr(client, "_sptc_loop", None)
            if loop is None:
                loop = asyncio.new_event_loop()
                threading.Thread(target=_serve, args=(loop,), daemon=True,
                                 name="rlms-batch-http").start()
                # the finalizer holds the async client, never the client itself
                fin = weakref.finalize(client, _shutdown, loop, client.async_client)
                fin.atexit = False  # the thread is a daemon: nothing to wait for at exit
                client._sptc_loop = loop
    return loop


async def acompletion(self, prompt, model=None):
    """OpenAIClient.acompletion, run on the client's own loop."""
    fut = asyncio.run_coroutine_threadsafe(STOCK(self, prompt, model), loop_of(self))
    try:
        out = await asyncio.wrap_future(fut)
    except Exception as e:
        with _lock:
            _stats["calls"] += 1
            _stats["failed"][LOOP_ERROR if LOOP_ERROR in str(e) else type(e).__name__] += 1
        raise
    with _lock:
        _stats["calls"] += 1
    return out


def apply() -> None:
    OpenAIClient.acompletion = acompletion


def revert() -> None:
    OpenAIClient.acompletion = STOCK


def applied() -> bool:
    return OpenAIClient.acompletion is acompletion


def stats(reset: bool = False) -> dict:
    """Batched prompts sent through the fix since the last reset, and those that failed,
    by exception type. A failure here is the engine's or the network's: the prompt comes
    back to the program as an error string, as it would from a correct rlms."""
    with _lock:
        out = {"calls": _stats["calls"], "failed": dict(_stats["failed"])}
        if reset:
            _stats["calls"] = 0
            _stats["failed"] = Counter()
    return out


# --------------------------------------------------------------------------- the probe
def probe(base_url: str, model: str, batches: int = 4, size: int = 20,
          gaps: tuple[float, ...] = (0.0, 0.0, 6.0), max_tokens: int = 4) -> dict:
    """Send `batches` batches of `size` short prompts the way a REPL's llm_query_batched
    does (LocalREPL -> LMHandler -> the client's acompletion -> the engine) and count the
    prompts that came back as an error string.

    `gaps` are the seconds slept before the second, third, ... batch (the last one is
    reused). The default leaves one gap longer than uvicorn's keep-alive timeout of 5 s:
    after it the server has closed the idle connections, which is another way for a
    kept connection to fail.

    Stock rlms 0.1.3 loses the first 16 prompts of the second batch and the first 4 of the
    third. With the fix applied, none."""
    from rlm.core.lm_handler import LMHandler
    from rlm.environments.local_repl import LocalREPL

    client = OpenAIClient(api_key="EMPTY", model_name=model, base_url=base_url,
                          sampling_args={"max_tokens": max_tokens, "temperature": 0.0})
    rows = []
    with LMHandler(client) as handler:
        repl = LocalREPL(lm_handler_address=handler.address, context_payload="probe")
        try:
            for b in range(batches):
                if b and gaps:
                    time.sleep(gaps[min(b - 1, len(gaps) - 1)])
                tag = uuid.uuid4().hex[:12]  # unique prompts: nothing from a prefix cache
                prompts = [f"[{tag}-{i}] Reply with the single word: ok" for i in range(size)]
                t0 = time.perf_counter()
                res = repl._llm_query_batched(prompts)
                errs = [r for r in res if isinstance(r, str) and r.startswith("Error:")]
                rows.append({"batch": b + 1, "size": size, "errors": len(errs),
                             "loop_errors": sum(1 for r in errs if LOOP_ERROR in r),
                             "wall_s": round(time.perf_counter() - t0, 3),
                             "first_error": errs[0][:160] if errs else None})
        finally:
            repl.cleanup()
    return {"fixed": applied(), "prompts": batches * size, "batches": rows,
            "errors": sum(r["errors"] for r in rows),
            "loop_errors": sum(r["loop_errors"] for r in rows)}
