"""A fake vLLM for the replay bench: one process, one event loop, a clock that steps.

    python fake_engine.py --port 8399 --step-ms 45

It answers what the replay sends (chat completions, streamed or not, with a forced output
length; /v1/models; /metrics) and it models the engine the campaign ran on, an eager vLLM,
closely enough to plan a run with:

- The engine works in steps. Every running request gets one token per step, whatever the
  batch size (with --enforce-eager a decode step is mostly Python on the host's CPU).
- A request's prompt is prefilled before its first token, in steps that share a budget of
  `--batch-tokens` prompt tokens (vLLM's max_num_batched_tokens), first come first served.
  A step costs `--step-ms` plus `--prefill-us` per prompt token it prefills.
- A prompt's tokens that were prefilled before, as a prefix of an earlier prompt, cost
  nothing (the prefix cache; no eviction here).
- At most `--max-seqs` requests run; the rest wait, first come first served.
- A step takes `--alpha` longer per running request (0: a batch is free, as on the eager
  H100 of the campaign up to about 128 requests).
- A prompt is 3.3 characters a token. With `--long-chars-per-token`, a prompt of more
  than 20,000 characters is counted at that rate instead: OOLONG's context text, full of
  numbers and identifiers, runs at 2.8 (100,276 characters were 36,000 tokens).
- The KV cache holds `--kv-tokens` tokens. A request is admitted when its prompt fits; one
  that does not fit waits, and so does everything behind it (vLLM does the same). A
  running request that needs a token when the cache is full preempts the request admitted
  last, which goes back to the head of the queue and is prefilled again from its start.

Nothing here is measured. The step time and the prefill cost are set from the recorded
runs (root token gap 33 to 53 ms by host; a 36,000-token prompt stalled the root for 1 to
3 s). Output text is filler: the replay returns the recorded text itself.

/metrics has what spec_ptc.engine.load reads: requests running and waiting, the KV
cache's use and size, preemptions, and the time between two tokens of a request.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import threading
import time
from collections import deque

from aiohttp import web

CHARS_PER_TOKEN = 3.3
BLOCK_CHARS = 53  # 16 tokens: the prefix cache's block
LONG_CHARS = 20_000  # a prompt longer than this is context text (--long-chars-per-token)


class Request:
    __slots__ = ("out_tokens", "prefill_left", "done_tokens", "queue", "finished", "stream",
                 "prompt_tokens", "t_arrive", "t_token")

    def __init__(self, prompt_tokens: int, uncached: int, out_tokens: int, stream: bool):
        self.prompt_tokens = prompt_tokens
        self.prefill_left = uncached
        self.out_tokens = max(1, out_tokens)
        self.done_tokens = 0
        self.stream = stream
        self.queue: asyncio.Queue | None = asyncio.Queue() if stream else None
        self.finished = asyncio.Event()
        self.t_arrive = time.perf_counter()
        self.t_token: float | None = None  # when its last token came

    def kv(self) -> int:
        """Tokens of KV cache it holds once admitted: its prompt and what it has written."""
        return self.prompt_tokens + self.done_tokens


class Engine:
    def __init__(self, step_s: float, prefill_s: float, batch_tokens: int, max_seqs: int,
                 natural_tokens: int, alpha: float = 0.0, kv_tokens: int = 154_816) -> None:
        self.step_s, self.prefill_s = step_s, prefill_s
        self.batch_tokens, self.max_seqs = batch_tokens, max_seqs
        self.natural_tokens = natural_tokens
        self.alpha, self.kv_tokens = alpha, kv_tokens
        self.long_chars_per_token = CHARS_PER_TOKEN
        self.running: list[Request] = []
        self.waiting: deque[Request] = deque()
        self.seen_blocks: set[bytes] = set()
        self.wake = asyncio.Event()
        self.counters = {"requests": 0, "prompt_tokens": 0, "gen_tokens": 0, "steps": 0,
                         "cached_tokens": 0, "max_running": 0, "max_waiting": 0,
                         "preemptions": 0, "itl_sum": 0.0, "itl_count": 0, "kv_peak": 0.0}

    def kv_used(self) -> int:
        return sum(r.kv() for r in self.running)

    # ---- prefix cache: the tokens of a prompt whose blocks were all seen before
    def uncached_tokens(self, text: str) -> tuple[int, int]:
        per = self.long_chars_per_token if len(text) > LONG_CHARS else CHARS_PER_TOKEN
        total = max(1, round(len(text) / per))
        h = hashlib.blake2b(digest_size=8)
        cached_blocks = 0
        fresh: list[bytes] = []
        hit = True
        for i in range(0, len(text) - BLOCK_CHARS + 1, BLOCK_CHARS):
            h.update(text[i:i + BLOCK_CHARS].encode("utf-8", "surrogatepass"))
            d = h.digest()
            if hit and d in self.seen_blocks:
                cached_blocks += 1
            else:
                hit = False
                fresh.append(d)
        self.seen_blocks.update(fresh)
        per_block = 16 if per == CHARS_PER_TOKEN else BLOCK_CHARS / per
        cached = min(total, round(cached_blocks * per_block))
        return total, total - cached

    def submit(self, text: str, out_tokens: int, stream: bool) -> Request:
        total, uncached = self.uncached_tokens(text)
        req = Request(total, uncached, out_tokens, stream)
        c = self.counters
        c["requests"] += 1
        c["prompt_tokens"] += total
        c["cached_tokens"] += total - uncached
        self.waiting.append(req)
        c["max_waiting"] = max(c["max_waiting"], len(self.waiting))
        self.wake.set()
        return req

    async def run(self) -> None:
        while True:
            if not self.running and not self.waiting:
                self.wake.clear()
                await self.wake.wait()
            # admission, first come first served: a prompt that does not fit the KV cache
            # waits, and so does everything behind it
            used = self.kv_used()
            while self.waiting and len(self.running) < self.max_seqs:
                r = self.waiting[0]
                if self.running and used + r.kv() > self.kv_tokens:
                    break
                used += r.kv()
                self.running.append(self.waiting.popleft())
            c = self.counters
            c["max_running"] = max(c["max_running"], len(self.running))
            c["max_waiting"] = max(c["max_waiting"], len(self.waiting))
            # a token needs a place in the cache: while the step's tokens do not fit, the
            # request admitted last is preempted and goes back to the head of the queue
            while len(self.running) > 1 and used + len(self.running) > self.kv_tokens:
                victim = self.running.pop()
                used -= victim.kv()
                victim.prefill_left = victim.kv()  # prefilled again, from its start
                self.waiting.appendleft(victim)
                c["preemptions"] += 1
            c["kv_peak"] = max(c["kv_peak"], used / self.kv_tokens)
            # one step: decode tokens first, then prefill chunks with what is left of the budget
            budget = self.batch_tokens
            prefilled = 0
            emit: list[Request] = []
            for r in self.running:
                if r.prefill_left <= 0:
                    budget -= 1
                    emit.append(r)
            for r in self.running:
                if r.prefill_left > 0 and budget > 0:
                    take = min(r.prefill_left, budget)
                    r.prefill_left -= take
                    budget -= take
                    prefilled += take
                    if r.prefill_left == 0:
                        emit.append(r)  # the step that ends the prefill gives the first token
            await asyncio.sleep(self.step_s * (1.0 + self.alpha * len(self.running))
                                + self.prefill_s * prefilled)
            self.counters["steps"] += 1
            now = time.perf_counter()
            still: list[Request] = []
            emitted = set(map(id, emit))
            for r in self.running:
                if id(r) in emitted:
                    r.done_tokens += 1
                    self.counters["gen_tokens"] += 1
                    if r.t_token is not None:
                        c["itl_sum"] += now - r.t_token
                        c["itl_count"] += 1
                    r.t_token = now
                    if r.queue is not None:
                        r.queue.put_nowait(r.done_tokens)
                    if r.done_tokens >= r.out_tokens:
                        r.finished.set()
                        if r.queue is not None:
                            r.queue.put_nowait(None)
                        continue
                still.append(r)
            self.running = still

    def metrics(self) -> str:
        c = self.counters
        kv = self.kv_used() / self.kv_tokens
        blocks = self.kv_tokens // 16
        return (f'vllm:num_requests_running{{model_name="fake"}} {len(self.running)}\n'
                f'vllm:num_requests_waiting{{model_name="fake"}} {len(self.waiting)}\n'
                f'vllm:kv_cache_usage_perc{{model_name="fake"}} {min(1.0, kv):.4f}\n'
                f'vllm:num_preemptions_total{{model_name="fake"}} {c["preemptions"]}\n'
                f'vllm:inter_token_latency_seconds_sum{{model_name="fake"}} {c["itl_sum"]:.6f}\n'
                f'vllm:inter_token_latency_seconds_count{{model_name="fake"}} {c["itl_count"]}\n'
                f'vllm:cache_config_info{{block_size="16",num_gpu_blocks="{blocks}"}} 1.0\n'
                f'vllm:prefix_cache_queries_total{{model_name="fake"}} {c["prompt_tokens"]}\n'
                f'vllm:prefix_cache_hits_total{{model_name="fake"}} {c["cached_tokens"]}\n'
                f'vllm:prompt_tokens_total{{model_name="fake"}} {c["prompt_tokens"]}\n'
                f'vllm:generation_tokens_total{{model_name="fake"}} {c["gen_tokens"]}\n')


def make_app(engine: Engine, model: str) -> web.Application:
    async def models(_req):
        return web.json_response({"object": "list", "data": [{"id": model, "object": "model"}]})

    async def metrics(_req):
        return web.Response(text=engine.metrics())

    async def stats(_req):
        return web.json_response(engine.counters)

    async def chat(request: web.Request):
        body = await request.json()
        msgs = body.get("messages") or []
        text = "\x1e".join(str(m.get("content", "")) for m in msgs)
        limit = body.get("max_completion_tokens") or body.get("max_tokens")
        if body.get("ignore_eos") and limit:
            n = int(limit)
        else:
            n = min(int(limit or engine.natural_tokens), engine.natural_tokens)
        stream = bool(body.get("stream"))
        req = engine.submit(text, n, stream)
        base = {"id": "fake", "created": 0, "model": model}
        if not stream:
            try:
                await req.finished.wait()
            except asyncio.CancelledError:
                req.out_tokens = req.done_tokens  # the client went away: stop generating
                raise
            usage = {"prompt_tokens": req.prompt_tokens, "completion_tokens": req.done_tokens,
                     "total_tokens": req.prompt_tokens + req.done_tokens}
            return web.json_response({**base, "object": "chat.completion", "usage": usage,
                                      "choices": [{"index": 0, "finish_reason": "length",
                                                   "message": {"role": "assistant",
                                                               "content": "x " * req.done_tokens}}]})
        opts = body.get("stream_options") or {}
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream",
                                           "Cache-Control": "no-cache"})
        await resp.prepare(request)

        async def send(obj) -> None:
            await resp.write(f"data: {json.dumps(obj)}\n\n".encode())

        def usage_of(k: int) -> dict:
            return {"prompt_tokens": req.prompt_tokens, "completion_tokens": k,
                    "total_tokens": req.prompt_tokens + k}

        chunk = {**base, "object": "chat.completion.chunk"}
        try:
            first = {**chunk, "choices": [{"index": 0, "delta": {"role": "assistant",
                                                                "content": ""},
                                           "finish_reason": None}]}
            if opts.get("continuous_usage_stats"):
                first["usage"] = usage_of(0)
            await send(first)
            while True:
                k = await req.queue.get()
                if k is None:
                    break
                c = {**chunk, "choices": [{"index": 0, "delta": {"content": "x "},
                                           "finish_reason": "length" if k >= req.out_tokens
                                           else None}]}
                if opts.get("continuous_usage_stats"):
                    c["usage"] = usage_of(k)
                await send(c)
            if opts.get("include_usage"):
                await send({**chunk, "choices": [], "usage": usage_of(req.done_tokens)})
            await resp.write(b"data: [DONE]\n\n")
        except (asyncio.CancelledError, ConnectionResetError):
            req.out_tokens = req.done_tokens
            raise
        await resp.write_eof()
        return resp

    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.add_routes([web.get("/v1/models", models), web.get("/metrics", metrics),
                    web.get("/stats", stats), web.post("/v1/chat/completions", chat)])

    tasks: list[asyncio.Task] = []

    async def start(app_):
        tasks.append(asyncio.create_task(engine.run()))

    async def stop(app_):
        for t in tasks:
            t.cancel()

    app.on_startup.append(start)
    app.on_cleanup.append(stop)
    return app


class FakeEngineServer:
    """The fake engine in a background thread, for tests: `with FakeEngineServer() as srv`."""

    def __init__(self, step_ms: float = 2.0, prefill_us: float = 1.0, model: str = "fake-model",
                 batch_tokens: int = 8192, max_seqs: int = 1024, natural_tokens: int = 8,
                 alpha: float = 0.0, kv_tokens: int = 154_816) -> None:
        self.model = model
        self._cfg = (step_ms / 1000.0, prefill_us / 1e6, batch_tokens, max_seqs, natural_tokens,
                     alpha, kv_tokens)
        self.engine: Engine | None = None
        self.port = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def _serve(self) -> None:
        loop = self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def start():
            self.engine = Engine(*self._cfg)
            runner = web.AppRunner(make_app(self.engine, self.model), access_log=None)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0, backlog=4096)
            await site.start()
            self.port = site._server.sockets[0].getsockname()[1]
            self._ready.set()

        loop.run_until_complete(start())
        loop.run_forever()

    def __enter__(self) -> FakeEngineServer:
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("the fake engine did not start")
        return self

    def __exit__(self, *exc) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8399)
    ap.add_argument("--model", default="fake-model")
    ap.add_argument("--step-ms", type=float, default=45.0)
    ap.add_argument("--prefill-us", type=float, default=50.0,
                    help="microseconds a step takes longer per prompt token it prefills")
    ap.add_argument("--batch-tokens", type=int, default=8192)
    ap.add_argument("--max-seqs", type=int, default=1024)
    ap.add_argument("--natural-tokens", type=int, default=8,
                    help="output length of a request that does not force one")
    ap.add_argument("--alpha", type=float, default=0.0,
                    help="share of a step's time each running request adds (0: a batch is free)")
    ap.add_argument("--kv-tokens", type=int, default=154_816,
                    help="size of the KV cache in tokens (the H100 run: 154,816)")
    ap.add_argument("--long-chars-per-token", type=float, default=CHARS_PER_TOKEN,
                    help="characters a token in prompts of more than 20,000 characters")
    a = ap.parse_args(argv)
    engine = Engine(a.step_ms / 1000.0, a.prefill_us / 1e6, a.batch_tokens, a.max_seqs,
                    a.natural_tokens, a.alpha, a.kv_tokens)
    engine.long_chars_per_token = a.long_chars_per_token
    web.run_app(make_app(engine, a.model), host="127.0.0.1", port=a.port, print=None,
                access_log=None, backlog=4096)


if __name__ == "__main__":
    main()
