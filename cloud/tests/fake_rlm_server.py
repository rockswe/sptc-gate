"""A small OpenAI-compatible server for testing the RLM campaign locally.

- POST /v1/chat/completions, streamed (SSE, with stream_options.include_usage) or not.
  A request with a system message is the RLM root: it gets script[k], where k is the number
  of assistant messages already in the request (the iteration), one word per token with
  `token_s` between tokens. Any other request is a sub-call: it waits `sub_s`, then answers
  a deterministic label.
- GET /v1/models, GET /metrics (vllm:num_requests_running and the gauges and counters
  cloud/rlm_campaign.py's poller reads).
- `log`: every request's kind, start and end time (time.time()), stream flag, prompt head
  and the client's port (one per connection), for ordering checks.
- `idle_close_s`: the server closes a kept connection after this long without a request,
  as uvicorn does after 5 s.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:
        # a client that drops its connection is part of some tests: no traceback for it
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class FakeRLMServer:
    def __init__(self, script: list[str], token_s: float = 0.01, sub_s: float = 0.3,
                 model: str = "fake-model", idle_close_s: float | None = None) -> None:
        self.script, self.token_s, self.sub_s, self.model = script, token_s, sub_s, model
        self.idle_close_s = idle_close_s
        self.log: list[dict] = []
        self.running = 0
        self._lock = threading.Lock()
        self._httpd = _Server(("127.0.0.1", 0), self._handler())
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self._th = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> FakeRLMServer:
        self._th.start()
        return self

    def __exit__(self, *exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    # ------------------------------------------------------------------ replies
    def reply_for(self, body: dict) -> tuple[str, str]:
        msgs = body.get("messages") or []
        if any(m.get("role") == "system" for m in msgs):
            k = sum(1 for m in msgs if m.get("role") == "assistant")
            return "root", self.script[min(k, len(self.script) - 1)]
        prompt = str(msgs[-1].get("content", "")) if msgs else ""
        h = int(hashlib.sha1(prompt.encode()).hexdigest()[:8], 16)
        return "sub", f"label: {'yes' if h % 2 else 'no'}"

    @staticmethod
    def tokens(text: str) -> list[str]:
        return re.findall(r"\S+\s*|\s+", text)

    def metrics(self) -> str:
        with self._lock:
            running = self.running
        return (
            f'vllm:num_requests_running{{model_name="{self.model}"}} {running}\n'
            f'vllm:num_requests_waiting{{model_name="{self.model}"}} 0\n'
            f'vllm:kv_cache_usage_perc{{model_name="{self.model}"}} {0.01 * running}\n'
            f'vllm:num_preemptions_total{{model_name="{self.model}"}} 0\n'
            f'vllm:prefix_cache_queries_total{{model_name="{self.model}"}} 100\n'
            f'vllm:prefix_cache_hits_total{{model_name="{self.model}"}} 40\n'
        )

    # ------------------------------------------------------------------ http
    def _handler(self):
        srv = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            timeout = srv.idle_close_s  # a read that waits this long ends the connection

            def log_message(self, *a) -> None:  # quiet
                pass

            def _send(self, code: int, data: bytes, ctype: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                if self.path.startswith("/metrics"):
                    self._send(200, srv.metrics().encode(), "text/plain")
                elif self.path.startswith("/v1/models"):
                    body = {"object": "list", "data": [{"id": srv.model, "object": "model"}]}
                    self._send(200, json.dumps(body).encode(), "application/json")
                else:
                    self._send(404, b"{}", "application/json")

            def do_POST(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                kind, text = srv.reply_for(body)
                stream = bool(body.get("stream"))
                msgs = body.get("messages", [])
                prompt_tokens = sum(len(str(m.get("content", ""))) for m in msgs) // 4
                toks = srv.tokens(text)
                rec = {"kind": kind, "stream": stream, "t_start": time.time(),
                       "port": self.client_address[1],
                       "head": str((body.get("messages") or [{}])[-1].get("content", ""))[:60]}
                with srv._lock:
                    srv.running += 1
                    srv.log.append(rec)
                try:
                    usage = {"prompt_tokens": prompt_tokens, "completion_tokens": len(toks),
                             "total_tokens": prompt_tokens + len(toks)}
                    if not stream:
                        time.sleep(srv.sub_s if kind == "sub" else srv.token_s * len(toks))
                        out = {"id": "x", "object": "chat.completion", "created": 0,
                               "model": srv.model, "usage": usage,
                               "choices": [{"index": 0, "finish_reason": "stop",
                                            "message": {"role": "assistant", "content": text}}]}
                        self._send(200, json.dumps(out).encode(), "application/json")
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Connection", "close")
                    self.end_headers()

                    def event(obj) -> None:
                        self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
                        self.wfile.flush()

                    base = {"id": "x", "object": "chat.completion.chunk", "created": 0,
                            "model": srv.model}
                    if kind == "sub":
                        time.sleep(srv.sub_s)
                    for t in toks:
                        if kind == "root":
                            time.sleep(srv.token_s)
                        event({**base, "choices": [{"index": 0, "delta": {"content": t},
                                                    "finish_reason": None}]})
                    event({**base, "choices": [{"index": 0, "delta": {},
                                                "finish_reason": "stop"}]})
                    if (body.get("stream_options") or {}).get("include_usage"):
                        event({**base, "choices": [], "usage": usage})
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    self.close_connection = True
                finally:
                    rec["t_end"] = time.time()
                    with srv._lock:
                        srv.running -= 1

        return H
