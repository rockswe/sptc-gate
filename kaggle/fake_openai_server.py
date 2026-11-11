"""A tiny OpenAI-compatible streaming server for testing the Kaggle clients locally
(kaggle/vllm_bench.py, kaggle/bench_general.py). Standard library only (asyncio); no model,
no GPU, deterministic token timing. The one fake server of the repo.

  python kaggle/fake_openai_server.py MODEL --port 8011 [--scheduling-policy priority]
        [--scheduler-cls sptc_vllm.scheduler.SptcScheduler --additional-config JSON]
        [--max-running 8] [--step-ms 4] [--kv-tokens 4000] [--log-json PATH]

In a test process: `srv, seen = serve(port, "--step-ms", "1")` runs it in a daemon thread;
`seen` gets every request body as sent, srv.shutdown() stops it.

It takes `vllm serve`'s command line (unknown flags are ignored), so the bench's --launch
path can start it in place of vLLM. What it imitates, and nothing more:
- /v1/completions and /v1/chat/completions, streamed as SSE with chunked encoding, with
  per-chunk logprobs.tokens (completions), finish_reason, stop_reason, a final usage chunk
  (stream_options.include_usage) and `data: [DONE]`.
- A batch loop: every step lasts step_ms + 0.5 ms per running request; a new request
  spends one step per 512 prompt tokens in prefill, then gets one token per step.
  ignore_eos runs to max_tokens; otherwise the length is a hash of the prompt.
- Scheduling: at most --max-running requests run. fcfs admits in arrival order; priority
  (--scheduling-policy priority) by (priority, arrival), as vLLM's waiting heap. When the
  running requests hold more than --kv-tokens tokens, one is preempted: the newest
  (fcfs), max (priority, arrival) (priority), or, with the sptc plugin, the newest bet is
  DROPPED (finish abort, stop_reason sptc_bet_dropped).
- The sptc plugin (--scheduler-cls ...Sptc...): a bet (vllm_xargs or custom_params
  sptc_class=bet) is admitted only if no non-bet request waits and running + 1 <=
  free_window; otherwise it is REJECTED at once. Streamed, a rejected request sends no
  choice chunk at all, only usage and [DONE] (as vLLM, which drops the empty final chunk).
- A client that disconnects aborts its request (running or waiting).
- GET /v1/models, GET /metrics (vllm:num_requests_running, ..._waiting,
  vllm:num_preemptions_total, vllm:kv_cache_usage_perc), GET /fake/log (every request).
- Fault injection: --fail-once TEXT: the first request whose prompt contains TEXT streams
  zero tokens and no finish_reason (the silent failure of the first T4 load test).
  --exit-if-config TEXT: exit at startup (code 1) if --additional-config contains TEXT
  (a server that fails to start).
- cache_salt: taken if a non-empty string (as vLLM's request field) and logged; it
  changes nothing here (no prefix cache). --refuse-cache-salt answers HTTP 400 instead
  (a server without the field).
- Compile cache (--compile-cache DIR): prints vLLM 0.32's startup lines for a fresh
  torch.compile ('Using cache directory', 'saved AOT compiled function to') the first
  time a --additional-config / --enforce-eager pair starts, and 'Directly load AOT
  compilation from path' after that, as results/kaggle_t4/sptc_out/vllm*.log.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import threading
import time
import zlib

PREFILL_CHUNK = 512


class FakeReq:
    def __init__(self, rid: int, body: dict, chat: bool) -> None:
        self.rid, self.chat = rid, chat
        if chat:
            prompt = "".join(str(m.get("content", "")) for m in body.get("messages", []))
        else:
            prompt = str(body.get("prompt", ""))
        self.prompt = prompt
        self.prompt_tokens = max(1, len(prompt) // 4)
        self.max_tokens = int(body.get("max_tokens") or 16)
        if body.get("ignore_eos"):
            self.target, self.natural_finish = self.max_tokens, "length"
        else:
            n = 3 + zlib.crc32(prompt.encode()) % 40
            self.target = min(n, self.max_tokens)
            self.natural_finish = "stop" if n < self.max_tokens else "length"
        self.priority = int(body.get("priority") or 0)
        tags = body.get("vllm_xargs") or body.get("custom_params") or {}
        self.cls = tags.get("sptc_class") if isinstance(tags, dict) else None
        self.logprobs = body.get("logprobs") is not None and not chat
        self.arrival = time.monotonic()
        self.prefill_steps = 1 + self.prompt_tokens // PREFILL_CHUNK
        self.emitted = 0
        self.state = "waiting"
        self.finish = self.stop = None
        self.q: asyncio.Queue = asyncio.Queue()
        self.log = {"rid": rid, "path": "chat" if chat else "completions",
                    "priority": body.get("priority"), "vllm_xargs": body.get("vllm_xargs"),
                    "custom_params": body.get("custom_params"),
                    "ignore_eos": bool(body.get("ignore_eos")), "max_tokens": self.max_tokens,
                    "cache_salt": body.get("cache_salt"),
                    "prompt_head": prompt[:60], "outcome": None, "tokens": 0}

    @property
    def kv(self) -> int:
        return self.prompt_tokens + self.emitted


class Engine:
    def __init__(self, a) -> None:
        self.a = a
        self.policy = a.scheduling_policy
        self.plugin = bool(a.scheduler_cls and "Sptc" in a.scheduler_cls)
        cfg = json.loads(a.additional_config or "{}").get("sptc", {})
        self.free_window = int(cfg.get("free_window", 8))
        self.waiting: list[FakeReq] = []
        self.running: list[FakeReq] = []
        self.preemptions = 0
        self.wake = asyncio.Event()
        self.reqs: list[FakeReq] = []

    def key(self, r: FakeReq):
        if self.policy == "priority":
            return (r.priority, r.arrival, r.rid)
        return (r.arrival, r.rid)

    def add(self, r: FakeReq) -> None:
        self.reqs.append(r)
        self.waiting.append(r)
        self.wake.set()

    def finish(self, r: FakeReq, finish: str | None, stop: str | None = None,
               quiet: bool = False) -> None:
        """quiet: the finish already went out with the last token."""
        if r in self.running:
            self.running.remove(r)
        if r in self.waiting:
            self.waiting.remove(r)
        r.state, r.finish, r.stop = "done", finish, stop
        r.log["outcome"] = stop or finish
        r.log["tokens"] = r.emitted
        if not quiet:
            r.q.put_nowait(("end", "", finish, stop))

    def abort(self, r: FakeReq) -> None:
        """The client went away."""
        if r.state != "done":
            self.finish(r, "abort")
            r.log["outcome"] = "client_abort"

    def bet_gate(self) -> bool:
        nonbet_waiting = any(w.cls != "bet" for w in self.waiting)
        return not nonbet_waiting and len(self.running) + 1 <= self.free_window

    def schedule(self) -> None:
        self.waiting.sort(key=self.key)
        for r in list(self.waiting):
            if self.plugin and r.cls == "bet" and not self.bet_gate():
                self.waiting.remove(r)
                self.finish(r, "abort", "sptc_bet_rejected")
                continue
            if len(self.running) >= self.a.max_running:
                break
            self.waiting.remove(r)
            r.state = "running"
            self.running.append(r)
        while sum(r.kv for r in self.running) > self.a.kv_tokens and len(self.running) > 1:
            self.preempt()

    def preempt(self) -> None:
        self.preemptions += 1
        bets = [r for r in self.running if r.cls == "bet"]
        if self.plugin and bets:
            self.finish(bets[-1], "abort", "sptc_bet_dropped")
            return
        if self.policy == "priority":
            v = max(self.running, key=lambda r: (r.priority, r.arrival))
        else:
            v = self.running[-1]
        self.running.remove(v)
        v.state = "waiting"
        v.prefill_steps = 1 + v.kv // PREFILL_CHUNK  # recompute
        self.waiting.append(v)

    async def loop(self) -> None:
        while True:
            if not self.running and not self.waiting:
                self.wake.clear()
                await self.wake.wait()
            self.schedule()
            if not self.running:
                await asyncio.sleep(self.a.step_ms / 1000)
                continue
            await asyncio.sleep((self.a.step_ms + 0.5 * len(self.running)) / 1000)
            for r in list(self.running):
                if r.state != "running":
                    continue
                if r.prefill_steps > 0:
                    r.prefill_steps -= 1
                    if r.prefill_steps > 0:
                        continue
                r.emitted += 1
                last = r.emitted >= r.target
                r.q.put_nowait(("tok", f" w{r.emitted}", r.natural_finish if last else None,
                                None))
                if last:
                    self.finish(r, r.natural_finish, quiet=True)

    def metrics(self) -> str:
        kv = sum(r.kv for r in self.running) / max(1, self.a.kv_tokens)
        return ("# HELP vllm:num_requests_running fake\n"
                f'vllm:num_requests_running{{model_name="{self.a.model}"}} {len(self.running)}\n'
                f'vllm:num_requests_waiting{{model_name="{self.a.model}"}} {len(self.waiting)}\n'
                f'vllm:kv_cache_usage_perc{{model_name="{self.a.model}"}} {kv}\n'
                f'vllm:num_preemptions_total{{model_name="{self.a.model}"}} {self.preemptions}\n'
                f'vllm:num_preemptions_created{{model_name="{self.a.model}"}} 1.7e9\n')


class Server:
    def __init__(self, a) -> None:
        self.a = a
        self.engine = Engine(a)
        self.rid = 0
        self.fail_once = a.fail_once
        self.seen: list[dict] = []  # every request body, as sent
        self.srv: asyncio.AbstractServer | None = None

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
            writer.close()
            return
        lines = head.decode(errors="replace").split("\r\n")
        method, path, _ = (lines[0].split(" ") + ["", ""])[:3]
        hdr = {k.strip().lower(): v.strip() for k, v in
               (x.split(":", 1) for x in lines[1:] if ":" in x)}
        body = b""
        if int(hdr.get("content-length", 0)):
            body = await reader.readexactly(int(hdr["content-length"]))
        try:
            if method == "GET" and path == "/v1/models":
                await self.send_json(writer, {"object": "list", "data": [{"id": self.a.model}]})
            elif method == "GET" and path == "/metrics":
                await self.send(writer, 200, self.engine.metrics().encode(), "text/plain")
            elif method == "GET" and path == "/fake/log":
                await self.send_json(writer, [r.log for r in self.engine.reqs])
            elif method == "POST" and path in ("/v1/completions", "/v1/chat/completions"):
                await self.generate(reader, writer, json.loads(body or b"{}"),
                                    chat=path.endswith("chat/completions"))
            else:
                await self.send(writer, 404, b'{"error": "not found"}', "application/json")
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass

    async def send(self, writer, status: int, data: bytes, ctype: str) -> None:
        writer.write(f"HTTP/1.1 {status} {'OK' if status == 200 else 'ERR'}\r\n"
                     f"Content-Type: {ctype}\r\nContent-Length: {len(data)}\r\n"
                     "Connection: close\r\n\r\n".encode() + data)
        await writer.drain()

    async def send_json(self, writer, obj) -> None:
        await self.send(writer, 200, json.dumps(obj).encode(), "application/json")

    async def generate(self, reader, writer, body: dict, chat: bool) -> None:
        if "priority" in body and not isinstance(body["priority"], int):
            await self.send(writer, 400, b'{"error": "priority must be an int"}',
                            "application/json")
            return
        if "cache_salt" in body and (self.a.refuse_cache_salt or not (
                isinstance(body["cache_salt"], str) and body["cache_salt"])):
            await self.send(writer, 400, b'{"error": "bad cache_salt"}', "application/json")
            return
        self.seen.append(body)
        self.rid += 1
        r = FakeReq(self.rid, body, chat)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                     b"Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n")

        async def event(obj) -> None:
            data = f"data: {obj if isinstance(obj, str) else json.dumps(obj)}\n\n".encode()
            writer.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
            await writer.drain()

        if self.fail_once and self.fail_once in r.prompt:
            self.fail_once = None
            r.log["outcome"] = "injected_failure"
            self.engine.reqs.append(r)
            self.write_log(r)
            await event("[DONE]")
            writer.write(b"0\r\n\r\n")
            await writer.drain()
            return
        self.engine.add(r)
        gone = asyncio.ensure_future(reader.read(1))  # EOF: the client disconnected
        oid, created = f"cmpl-{r.rid}", int(time.time())
        first = True
        try:
            while True:
                get = asyncio.ensure_future(r.q.get())
                done, _ = await asyncio.wait({get, gone}, return_when=asyncio.FIRST_COMPLETED)
                if get not in done:
                    get.cancel()
                    self.engine.abort(r)
                    return
                kind, text, fin, stop = get.result()
                if kind == "end" and r.emitted == 0:
                    break  # no token: vLLM sends no choice chunk at all
                if chat:
                    if first:  # vLLM's first chat chunk carries only the role
                        await event({"id": oid, "object": "chat.completion.chunk",
                                     "created": created, "model": self.a.model,
                                     "choices": [{"index": 0, "finish_reason": None,
                                                  "delta": {"role": "assistant",
                                                            "content": ""}}]})
                        first = False
                    ch = {"index": 0, "delta": {"content": text}, "finish_reason": fin,
                          "stop_reason": stop}
                    obj = {"id": oid, "object": "chat.completion.chunk", "created": created,
                           "model": self.a.model, "choices": [ch]}
                else:
                    ch = {"index": 0, "text": text, "finish_reason": fin, "stop_reason": stop}
                    if r.logprobs:
                        ch["logprobs"] = {"tokens": [text] if text else [],
                                          "token_logprobs": [-0.1] if text else [],
                                          "top_logprobs": None, "text_offset": [0] if text else []}
                    obj = {"id": oid, "object": "text_completion", "created": created,
                           "model": self.a.model, "choices": [ch]}
                await event(obj)
                if fin is not None:
                    break
            await event({"id": oid, "object": "chat.completion.chunk" if chat else
                         "text_completion", "created": created, "model": self.a.model,
                         "choices": [], "usage": {"prompt_tokens": r.prompt_tokens,
                                                  "completion_tokens": r.emitted,
                                                  "total_tokens": r.prompt_tokens + r.emitted}})
            await event("[DONE]")
            writer.write(b"0\r\n\r\n")
            await writer.drain()
        except ConnectionError:
            self.engine.abort(r)
        finally:
            gone.cancel()
            if r.state == "done":
                self.write_log(r)

    def write_log(self, r: FakeReq) -> None:
        if self.a.log_json:
            with open(self.a.log_json, "a") as f:
                f.write(json.dumps({**r.log, "flags": self.flags()}) + "\n")

    def flags(self) -> dict:
        return {"policy": self.a.scheduling_policy, "plugin": self.engine.plugin}

    async def start(self) -> None:
        self.srv = await asyncio.start_server(self.handle, "127.0.0.1", self.a.port)
        self.loop_task = asyncio.ensure_future(self.engine.loop())
        print(f"fake server on :{self.a.port} {self.flags()}", flush=True)

    async def main(self) -> None:
        await self.start()
        async with self.srv:
            await self.srv.serve_forever()
        self.loop_task.cancel()


class Thread:
    """A Server on its own event loop in a daemon thread (serve())."""

    def __init__(self, server: Server) -> None:
        self.server = server
        self.loop = asyncio.new_event_loop()
        up = threading.Event()

        def run() -> None:
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(server.start())
            up.set()
            self.loop.run_forever()

        threading.Thread(target=run, daemon=True).start()
        if not up.wait(10):
            raise RuntimeError("fake server did not start")

    def shutdown(self) -> None:
        async def close() -> None:
            self.server.srv.close()
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        asyncio.run_coroutine_threadsafe(close(), self.loop).result(10)
        self.loop.call_soon_threadsafe(self.loop.stop)


def serve(port: int, *flags: str, model: str = "fake-model") -> tuple[Thread, list[dict]]:
    """Start in a daemon thread of this process; returns (handle, request bodies seen).
    flags are the command line's (e.g. "--step-ms", "1"); --max-running defaults to 64."""
    argv = [model, "--port", str(port), "--max-running", "64", *flags]
    srv = Server(parser().parse_known_args(argv)[0])
    return Thread(srv), srv.seen


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", nargs="?", default="fake-model")
    ap.add_argument("--port", type=int, default=8011)
    ap.add_argument("--scheduling-policy", default="fcfs", choices=["fcfs", "priority"])
    ap.add_argument("--scheduler-cls", default=None)
    ap.add_argument("--additional-config", default=None)
    ap.add_argument("--max-running", type=int, default=8)
    ap.add_argument("--step-ms", type=float, default=4.0)
    ap.add_argument("--kv-tokens", type=int, default=100_000)
    ap.add_argument("--log-json", default=None)
    ap.add_argument("--fail-once", default=None)
    ap.add_argument("--refuse-cache-salt", action="store_true")
    ap.add_argument("--exit-if-config", default=None)
    ap.add_argument("--compile-cache", default=None)
    ap.add_argument("--enforce-eager", action="store_true")
    return ap


def compile_lines(a) -> None:
    """vLLM 0.32's compile-state lines on stdout (see the module docstring)."""
    print(f"INFO with config: model='{a.model}', enforce_eager={a.enforce_eager}", flush=True)
    if a.enforce_eager:
        return
    key = hashlib.sha256(str(a.additional_config).encode()).hexdigest()
    path = os.path.join(a.compile_cache, "torch_aot_compile", key, "rank_0_0", "model")
    if os.path.exists(path):
        print(f"INFO [backbone] Directly load AOT compilation from path {path}", flush=True)
        print("INFO torch.compile took 0.26 s in total", flush=True)
        return
    print(f"INFO Using cache directory: {a.compile_cache}/{key[:10]}/rank_0_0/backbone for "
          "vLLM's torch.compile", flush=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()
    print(f"INFO [backbone] saved AOT compiled function to {path}", flush=True)
    print("INFO torch.compile took 32.04 s in total", flush=True)


def main() -> None:
    a, _unknown = parser().parse_known_args()  # vllm serve flags (--dtype ...) are ignored
    if a.exit_if_config and a.exit_if_config in str(a.additional_config):
        print(f"fake server: refusing to start ({a.exit_if_config})", flush=True)
        sys.exit(1)
    if a.compile_cache:
        compile_lines(a)
    try:
        asyncio.run(Server(a).main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
