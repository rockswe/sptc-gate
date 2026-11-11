"""Real-GPU validation on a Kaggle T4 (vLLM 0.32, Qwen3-1.7B fp16). OpenAI-compatible
API only, so it also runs (tiny) against Ollama's /v1 for a local smoke test, against
SGLang (--engine sglang: scheduler tags go in `custom_params` instead of `vllm_xargs`), and
against kaggle/fake_openai_server.py for the local end-to-end test.

  python kaggle/vllm_bench.py calib   --base-url URL --model M --out DIR
  python kaggle/vllm_bench.py predict --out DIR [--gpu T4]            # before concur!
  python kaggle/vllm_bench.py concur  --base-url URL --model M --out DIR
  python kaggle/vllm_bench.py suite   --base-url URL --model M --out DIR --spec-ptc PATH
  python kaggle/vllm_bench.py load    --base-url URL --model M --out DIR --spec-ptc PATH
        [--agents 1,4,8] [--decoys 0,1] [--tag-bets] [--engine vllm|sglang]
  python kaggle/vllm_bench.py sweep   --out DIR --spec-ptc PATH --preset PRESET
        [--launch] [--arms a,b] [--agents 1,4] [--reps 3] [--rounds 2] [--warm-pass]
        [--pressure-config chosen|fallback]
        PRESET: ab | ab_eager | prio8 (the regression A/B and the priority baseline),
                baselines (bets-only priority and a client-side cap on bets, at 4 and 8
                agents, next to stock FCFS and the plugin), probe | pressure (KV pressure
                and a real queue, the third T4 run: the probe that picks the T4 config,
                then every arm on it; --serve-cmd with --max-model-len 512),
                both_default (the `both` workload on the default servers), core | full |
                quick (the saturation sweep)
  python kaggle/vllm_bench.py report  --out DIR [--slo-session 2 --slo-tpot 2]
  python kaggle/vllm_bench.py plan    --preset core [--predictions results/sweep_prep/predictions.json]

calib/concur measure the decode window, prefill interference and fan-out.
suite   reruns spec-ptc's benchmark patterns (scripted root stream, real sub-calls) and
        logs every sub-call's prompt/completion tokens: the per-call data runs.csv lacks.
load    N agents run spec-ptc turns whose ROOT STREAM IS SERVED by the same vLLM (each
        root token releases 4 characters of the scripted program, like the simulator's
        ServedStream), baseline vs spec-ptc, optionally with one decoy (bad guess) per
        speculation, optionally tagging decoys as bets / speculations as early for the
        sptc_vllm / sptc_sglang scheduler plugin. Reports session latency p50/p99 and root
        TPOT p99. Kept for the existing notebooks; `sweep` is the full version.
sweep   the same agents, over a ladder of loads, for every ARM (server flags + client
        tagging + workload, one line each in ARMS; plugin servers in each prefill_allowance
        mode, and --enforce-eager twins), with repeats. One JSON file per
        (arm, load, repeat) under DIR/sweep/runs: a rerun skips finished files, so a
        crashed or timed-out session resumes. --launch starts and stops `vllm serve` itself
        (one server per scheduling setup); without it the server at --base-url is used and
        --server says which setup it is. Every decoy's outcome is logged. Each launch's
        compile state goes to DIR/sweep/launches.jsonl; with rounds > 1 every server is
        launched that many times, in turn, so stock vs stock across launches is measured.
report  session p50/p99 and root TPOT p50/p99 with bootstrap CIs across repeats,
        throughput, goodput under an SLO, decoy outcomes: DIR/sweep/summary.{json,md}.
plan    the runs of a preset and their estimated GPU minutes.

The HTTP client is the standard library (no openai package): it reads vLLM's extra stream
fields (stop_reason) directly, and it can cancel a stream from another thread.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import random
import shlex
import socket
import statistics
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import zlib
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

FILLER = ("The quarterly report covers revenue, latency, safety and quality across all "
          "regions, with per-item notes on cloud spend and energy use. ")
COUNT = "Count upward from 1, writing each number in words, separated by commas. Do not stop."
# request body field that carries {"sptc_class": ...} to the scheduler plugin
TAG_FIELDS = {"vllm": "vllm_xargs", "sglang": "custom_params"}
TAG_FIELD = TAG_FIELDS["vllm"]
SPEC_PRIORITY = 1  # vLLM priority of speculative calls in the `priority` tag scheme (0 = normal)
SIM_ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------------------- http client
class Endpoint:
    """An OpenAI-compatible server: base URL split for http.client."""

    def __init__(self, base_url: str, timeout: float = 600.0) -> None:
        u = urllib.parse.urlsplit(base_url)
        self.https = u.scheme == "https"
        self.host, self.port = u.hostname, u.port or (443 if self.https else 80)
        self.path = u.path.rstrip("/")  # e.g. /v1
        self.timeout = timeout

    def connect(self) -> http.client.HTTPConnection:
        cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
        conn = cls(self.host, self.port, timeout=self.timeout)
        conn.connect()  # now, so a canceller from another thread finds a socket
        return conn

    def get(self, path: str, timeout: float = 5.0) -> str:
        """GET path (absolute, e.g. /metrics, or relative to the base, e.g. models)."""
        full = path if path.startswith("/") else f"{self.path}/{path}"
        cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
        conn = cls(self.host, self.port, timeout=timeout)
        try:
            conn.request("GET", full)
            r = conn.getresponse()
            body = r.read().decode(errors="replace")
            if r.status != 200:
                raise RuntimeError(f"GET {full}: HTTP {r.status}")
            return body
        finally:
            conn.close()


def client(base_url: str) -> Endpoint:
    return Endpoint(base_url)


def long_prompt(tokens: int, tag: str) -> str:
    return f"[{tag} {time.perf_counter_ns()}] " + FILLER * max(1, tokens // 28) + "\nSummarize."


def stream(cl: Endpoint, model: str, prompt: str, max_tokens: int, out: dict, start=None,
           xargs: dict | None = None, stop_evt=None, natural: bool = False,
           body: dict | None = None, should_stop=None) -> None:
    """One streamed request: per-TOKEN arrival times + usage + finish/stop reason.

    Default: a raw completion that ignores EOS, so the token count is fixed (vLLM honours
    ignore_eos; Ollama ignores it). natural=True: a chat completion that stops where the
    model stops (thinking off), for measuring real output lengths. vLLM may merge several
    tokens into one chunk when the client lags, so tokens are counted from per-chunk
    logprobs where the server provides them.

    xargs go in the scheduler-tag field; body is merged into the request (e.g. priority).
    stop_evt (an Event) or should_stop (a callable) is checked at every chunk; cancel(out)
    closes the stream from another thread at once, even before the first token."""
    req = {"model": model, "max_tokens": max_tokens, "temperature": 0.0, "stream": True,
           "stream_options": {"include_usage": True}}
    if natural:
        path = "/chat/completions"
        req.update(messages=[{"role": "user", "content": prompt}],
                   chat_template_kwargs={"enable_thinking": False})
    else:
        path = "/completions"
        req.update(prompt=prompt, logprobs=0, ignore_eos=True)
    if xargs:
        req[TAG_FIELD] = xargs
    req.update(body or {})
    if stop_evt is not None and should_stop is None:
        should_stop = stop_evt.is_set
    if start is not None:
        start.wait()
    t0 = time.perf_counter()
    times: list[float] = []
    usage = finish = stop = None
    out.update(t0=t0, times=times)  # shared live: readers see tokens as they arrive
    conn = None
    try:
        conn = cl.connect()
        # keep the socket itself: http.client drops conn.sock once a response will close
        out["_sock"] = conn.sock
        if out.get("cancelled"):  # cancel() ran before the socket existed
            raise ConnectionAbortedError("cancelled before send")
        conn.request("POST", cl.path + path, json.dumps(req),
                     {"Content-Type": "application/json", "Accept": "text/event-stream"})
        resp = conn.getresponse()
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {resp.read(300).decode(errors='replace')}")
        while True:
            line = resp.readline()
            if not line:
                break  # connection closed without [DONE]
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                out["done_marker"] = True
                break
            ch = json.loads(data)
            if ch.get("error") and not ch.get("choices"):
                raise RuntimeError(f"stream error: {str(ch['error'])[:150]}")
            for c in ch.get("choices") or []:
                if natural:
                    text = (c.get("delta") or {}).get("content")
                    n = 1 if text else 0  # the first chunk carries only the role
                else:
                    text = c.get("text")
                    lp = c.get("logprobs")
                    toks = lp.get("tokens") if isinstance(lp, dict) else None
                    # no logprobs (Ollama): one chunk ~ one token
                    n = len(toks) if toks else (1 if text else 0)
                now = time.perf_counter() - t0
                times.extend([now] * n)
                if c.get("finish_reason"):
                    finish = c["finish_reason"]
                    # vLLM: stop_reason; SGLang: matched_stop
                    stop = c.get("stop_reason", c.get("matched_stop"))
            if ch.get("usage"):
                usage = {"prompt": ch["usage"].get("prompt_tokens"),
                         "completion": ch["usage"].get("completion_tokens")}
            if should_stop is not None and should_stop():
                out["cancelled"] = True
                break
    except Exception as e:  # noqa: BLE001 - a rejected or cancelled request may error
        if not out.get("cancelled"):
            finish = f"error: {type(e).__name__}: {e}"[:200]
    finally:
        if conn is not None:
            conn.close()
    if out.get("cancelled") and finish is None:
        finish = "client_abort"
    out.update(end=time.perf_counter() - t0, usage=usage, finish=finish, stop=stop, done=True)
    out.pop("_sock", None)


def cancel(out: dict) -> None:
    """Close a stream from another thread (the server sees a disconnect and aborts it)."""
    if out.get("done"):
        return
    out["cancelled"] = True
    sock = out.get("_sock")
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass  # already closed


def outcome(o: dict) -> str:
    """completed | rejected | dropped | cancelled | aborted | error | unknown.

    A streamed request the sptc plugin rejects before its first token ends with no
    finish_reason at all: vLLM drops the empty final chunk (chunked-prefill guard in the
    serving code), so 'no tokens, no finish, a clean [DONE]' counts as rejected. The same
    guard hides the stop_reason of a running bet dropped before its first token, so
    'rejected' means "refused, or dropped before its first token" and 'dropped' means
    "dropped after at least one token". The client cannot tell the first two apart."""
    fin, stop = o.get("finish"), o.get("stop")
    if stop == "sptc_bet_dropped":
        return "dropped"
    if stop in ("sptc_bet_rejected", "proxy_rejected"):
        return "rejected"
    if fin in ("length", "stop"):
        return "completed"
    if fin == "client_abort" or o.get("cancelled"):
        return "cancelled"
    if fin == "abort":
        return "aborted"
    if fin is not None and str(fin).startswith("error"):
        return "error"
    if fin is None and not o.get("times") and o.get("done_marker"):
        return "rejected"
    return "unknown"


def itl(times):
    return [b - a for a, b in zip(times, times[1:])]


def med(xs):
    return statistics.median(xs) if xs else math.nan


# ----------------------------------------------------------------------------- calib
def calib(a) -> dict:
    cl = client(a.base_url)
    o = {}
    stream(cl, a.model, "Say hi.", 4, o)
    res = {"M1_solo_decode": [], "M2_solo_prefill": []}
    for i in range(3):
        o = {}
        stream(cl, a.model, COUNT + f" ({i})", 128, o)
        res["M1_solo_decode"].append({"itl_median_ms": 1000 * med(itl(o["times"])[5:])})
    for n in (500, 1500, 3000):
        o = {}
        stream(cl, a.model, long_prompt(n, "m2"), 1, o)
        res["M2_solo_prefill"].append({"prompt_tokens": (o["usage"] or {}).get("prompt"),
                                       "ttft_s": o["times"][0] if o["times"] else o["end"]})
    return res


# ----------------------------------------------------------------------------- predict
def predict(a) -> dict:
    """Simulator predictions from calib.json alone (written before concur runs)."""
    sys.path.insert(0, str(SIM_ROOT))
    from sptc_sim.des import Sim
    from sptc_sim.hardware import GPU, MODELS, Overheads, StepCost
    from sptc_sim.server import Request, Server, ServerConfig

    cal = json.loads((Path(a.out) / "calib.json").read_text())
    gpu = {"T4": GPU("T4", 16, 0.320, 65.0), "L4": GPU("L4", 24, 0.300, 121.0)}[a.gpu]
    m = MODELS["Qwen3-1.7B"]
    d1 = statistics.mean(x["itl_median_ms"] for x in cal["M1_solo_decode"]) / 1000
    pts = [x for x in cal["M2_solo_prefill"] if x["prompt_tokens"]]
    # effective compute from the longest solo prefill (TTFT minus one decode step)
    big = max(pts, key=lambda x: x["prompt_tokens"])
    # same FLOP accounting as StepCost: body GEMMs per token, lm_head once per sequence
    body = m.active_params - m.lm_head_params
    work = 2.0 * (body * big["prompt_tokens"] + m.lm_head_params)
    flops = work / max(1e-3, big["ttft_s"] - d1)
    g = GPU(gpu.name, gpu.mem_gb, gpu.bw_tbs, flops / 1e12)
    probe = StepCost(g, m, ov=Overheads(t_fixed=0.0, t_per_seq=0.0, bw_eff=0.8, mfu=1.0,
                                        client_s=0.002))
    cost = probe.with_overheads(t_fixed=max(0.0, d1 - probe.decode_step(1, 150)))
    budget = 2048  # vLLM V1 default max_num_batched_tokens on GPUs < 70 GiB

    def stall(n):
        steps, left, c = [], n, 0
        while left > 0:
            ch = min(budget - 1, left)
            steps.append(cost.step_time([(1, 150), (ch, c)]))
            c += ch
            left -= ch
        return {"root_itl_max_ms": 1000 * max(steps), "sub_ttft_s": sum(steps)}

    def makespan(k):
        sim = Sim()
        srv = Server(sim, cost, ServerConfig(max_batched_tokens=budget, max_num_seqs=256))
        done = sim.all_of([srv.submit(Request(prompt=300, out=64)) for _ in range(k)])
        sim.run(until=done)
        return sim.now

    return {
        "stamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "eff_tflops": flops / 1e12, "t_fixed_ms": 1000 * cost.ov.t_fixed,
        "M3_root_itl_ratio": {k: cost.decode_step(k + 1, 150) / cost.decode_step(1, 150)
                              for k in (1, 3, 7, 15)},
        "M4": {n: stall(n) for n in (500, 1500, 3000)},
        "M5_makespan_s": {k: makespan(k) for k in (1, 2, 4, 8, 16)},
    }


# ----------------------------------------------------------------------------- concur
def concur(a) -> dict:
    cl = client(a.base_url)
    res = {"M3": [], "M4": [], "M5": []}
    for k in (0, 1, 3, 7, 15):
        outs = [{} for _ in range(k + 1)]
        go = threading.Event()
        ths = [threading.Thread(target=stream, args=(cl, a.model, COUNT + f" m3-{k}-{j}", 160,
                                                     outs[j], go)) for j in range(k + 1)]
        for t in ths:
            t.start()
        go.set()
        for t in ths:
            t.join()
        lo = max(o["t0"] + o["times"][10] for o in outs)
        hi = min(o["t0"] + o["times"][-1] for o in outs)
        per = [med([b - a_ for a_, b in zip([o["t0"] + t for t in o["times"]],
                                            [o["t0"] + t for t in o["times"][1:]])
                    if a_ >= lo and b <= hi]) for o in outs]
        res["M3"].append({"k_other": k, "itl_median_ms": 1000 * med(per)})
    for n in (500, 1500, 3000):
        root, sub = {}, {}
        rt = threading.Thread(target=stream, args=(cl, a.model, COUNT + f" m4-{n}", 200, root))
        rt.start()
        time.sleep(0.8)
        t_inj = time.perf_counter()
        stream(cl, a.model, long_prompt(n, f"m4s{n}"), 4, sub)
        rt.join()
        abs_t = [root["t0"] + t for t in root["times"]]
        win = [b - a_ for a_, b in zip(abs_t, abs_t[1:])
               if t_inj - 0.05 <= a_ <= t_inj + (sub["times"][0] if sub["times"] else 1) + 0.05]
        res["M4"].append({"prompt_tokens": (sub["usage"] or {}).get("prompt"),
                          "root_itl_max_ms": 1000 * max(win) if win else None,
                          "root_itl_median_ms": 1000 * med(itl(root["times"])),
                          "sub_ttft_s": sub["times"][0] if sub["times"] else None})
    for k in (1, 2, 4, 8, 16):
        outs = [{} for _ in range(k)]
        go = threading.Event()
        ths = [threading.Thread(target=stream, args=(cl, a.model, long_prompt(300, f"m5{k}{j}"),
                                                     64, outs[j], go)) for j in range(k)]
        for t in ths:
            t.start()
        t0 = time.perf_counter()
        go.set()
        for t in ths:
            t.join()
        res["M5"].append({"k": k, "makespan_s": time.perf_counter() - t0})
    return res


# ----------------------------------------------------------------------------- spec-ptc glue
def _spec_ptc(path: str):
    sys.path.insert(0, path)
    import benchmark.suite.patterns_v2  # noqa: F401
    import benchmark.suite.patterns_v3  # noqa: F401
    import benchmark.suite.patterns_v4  # noqa: F401
    import benchmark.suite.patterns_v5  # noqa: F401
    import benchmark.suite.patterns_v6  # noqa: F401
    try:  # loop shapes recorded from real RLM runs: in the sptc-hints fork only
        import benchmark.suite.patterns_v7  # noqa: F401
    except ImportError:
        pass
    from benchmark.suite.patterns import CONTEXT, PATTERNS, response_text
    from benchmark.suite.runner import SuiteEngine
    from spec_ptc import EventBus, Harness

    return CONTEXT, {p.name: p for p in PATTERNS}, response_text, SuiteEngine, EventBus, Harness


def tag_body(scheme: str, kind: str) -> dict:
    """Request fields that carry a call's class to the server.

    kind: root | call (normal sub-call) | early (spec-ptc speculative dispatch) | bet
    (decoy, and with Arm.spec_kind bet a speculative dispatch too) | fallback (a refused
    speculation re-run for real). Only early and bet are tagged. sptc: the plugin's class
    tag; sptc_bets: the same for bets only (early calls go untagged, as normal work: the
    class as the drafted RFC had it); priority: vLLM's request priority (lower runs first),
    spec calls at SPEC_PRIORITY and everything else at the default 0; priority_bets: the
    same for bets only (early calls are almost surely used, so they stay at the default,
    as the plugin treats them)."""
    if kind not in ("early", "bet") or scheme == "none":
        return {}
    if scheme == "sptc":
        return {TAG_FIELD: {"sptc_class": kind}}
    if scheme == "sptc_bets":
        return {TAG_FIELD: {"sptc_class": "bet"}} if kind == "bet" else {}
    if scheme == "priority":
        return {"priority": SPEC_PRIORITY}
    if scheme == "priority_bets":
        return {"priority": SPEC_PRIORITY} if kind == "bet" else {}
    raise ValueError(f"unknown tag scheme {scheme!r}")


TAG_SCHEMES = ("none", "sptc", "sptc_bets", "priority", "priority_bets")
SPEC_KINDS = ("early", "bet")  # Arm.spec_kind


def speculation_rejected() -> type:
    """spec-ptc's SpeculationRejected: raised by a speculative call, a claim re-runs the
    call for real. Only spec-ptc with the sptc-hints patch has it."""
    try:
        from spec_ptc.contracts.hints import SpeculationRejected
    except ImportError as e:
        raise RuntimeError("spec_kind 'bet' needs spec-ptc with the sptc-hints patch "
                           "(integrations/spec-ptc-sptc-hints.patch)") from e
    return SpeculationRejected


class ProxyGate:
    """A client-side cap on bets, shared by all agent processes of a run: what a proxy in
    front of the server could do if clients tag their bets (no scheduler change, no KV or
    queue view, no dropping of running work). A refused bet is never sent; a bet is never
    queued (a late bad guess is worthless). Modes, with cap = the plugin's free window:
      window  refuse a bet unless (requests in flight to the server, every class) + 1 <= cap:
              the plugin's sequence-count rule as a proxy sees it (it counts waiting
              requests too, and the time on the wire)
      bets    refuse a bet unless (bets in flight) + 1 <= cap: a plain semaphore on bets
    It runs inside the client, so it adds no forwarding hop: a best case for a proxy."""

    MODES = ("window", "bets")

    def __init__(self, spec: str, ctx=None) -> None:
        import multiprocessing as mp

        mode, cap = spec.split(":")
        if mode not in self.MODES or int(cap) < 0:
            raise ValueError(f"bad gate {spec!r}: MODE:CAP with MODE in {self.MODES}")
        ctx = ctx or mp.get_context("spawn")
        self.mode, self.cap = mode, int(cap)
        self.lock = ctx.Lock()
        # in flight: all requests, bets; peak of all; bets admitted, refused
        self.v = ctx.Array("i", 5, lock=False)

    def enter(self, kind: str) -> bool:
        """A request is about to be sent. False: a bet the gate refuses (do not send)."""
        v = self.v
        with self.lock:
            if kind == "bet":
                n = v[0] if self.mode == "window" else v[1]
                if n + 1 > self.cap:
                    v[4] += 1
                    return False
                v[1] += 1
                v[3] += 1
            v[0] += 1
            v[2] = max(v[2], v[0])
            return True

    def exit(self, kind: str) -> None:
        with self.lock:
            self.v[0] -= 1
            if kind == "bet":
                self.v[1] -= 1

    def stats(self) -> dict:
        with self.lock:
            return {"gate": f"{self.mode}:{self.cap}", "in_flight_end": self.v[0],
                    "peak_in_flight": self.v[2], "bets_sent": self.v[3],
                    "bets_refused": self.v[4]}


def gated_stream(gate, kind: str, *args, **kwargs) -> None:
    """stream() through a ProxyGate (None: no gate). A refused bet ends at once with no
    tokens and stop 'proxy_rejected' (outcome: rejected)."""
    out = args[4]  # stream(cl, model, prompt, max_tokens, out, ...)
    if gate is not None and not gate.enter(kind):
        now = time.perf_counter()
        out.update(t0=now, times=[], end=0.0, usage=None, finish=None, stop="proxy_rejected",
                   done=True)
        return
    try:
        stream(*args, **kwargs)
    finally:
        if gate is not None:
            gate.exit(kind)


class LoggedEngine:
    """spec-ptc's SuiteEngine with token logging, optional served root stream, decoys
    and scheduler hints. Wraps an instance so spec-ptc's own tool registration is used.

    spec_kind: the class of spec-ptc's own speculative calls (Arm.spec_kind). early: a
    refused or dropped one is run for real at once, inside the speculation. bet: it raises
    SpeculationRejected instead, and spec-ptc (sptc-hints patch) runs the call for real
    when the program claims it: the program's next call of a prompt whose last bet was
    refused is that run, logged as kind fallback with at_claim. A failed speculation is
    invisible to spec-ptc's store, so its shadow may bet on the same call again (a loop
    peek re-peeked, then dispatched by its statement); every call record has a prompt_id
    (crc32 of the prompt, without the run's salt) to count bets per call."""

    def __init__(self, base, cl, model, served: bool, decoys: int, tags: str, log: list,
                 natural: bool = False, salt: str = "", gate: ProxyGate | None = None,
                 cache_salt: str = "", spec_kind: str = "early"):
        if spec_kind not in SPEC_KINDS:
            raise ValueError(f"spec_kind {spec_kind!r} not in {SPEC_KINDS}")
        self.base, self.cl, self.model, self.natural = base, cl, model, natural
        self.served, self.decoys, self.tags, self.log = served, decoys, tags, log
        self.gate = gate  # a client-side cap on bets (ProxyGate), or None
        self.salt = salt  # prefix of every prompt: no prefix-cache hits across runs
        # vLLM's cache_salt on every request (a prefix cache of its own), or nothing
        self.extra = {"cache_salt": cache_salt} if cache_salt else {}
        self.spec_kind = spec_kind
        self.rejected = speculation_rejected() if spec_kind == "bet" else None
        self.refused_bets: set[str] = set()  # prompts whose last bet was refused, not re-run
        self.decoy_runs: list[tuple[threading.Thread, dict]] = []
        self.root_outs: list[dict] = []
        lock = threading.Lock()

        def call(prompt, _spec=None):
            spec = _spec is not None
            kind = self.spec_kind if spec else "call"
            if not spec:
                with lock:
                    if str(prompt) in self.refused_bets:  # its claim: spec-ptc re-runs it
                        self.refused_bets.discard(str(prompt))
                        kind = "fallback"
            rec = {"t0": time.perf_counter(), "spec": spec, "kind": kind,
                   "prompt_id": zlib.crc32(str(prompt).encode())}
            if kind == "fallback":
                rec["at_claim"] = True
            if spec:
                for d in range(self.decoys):  # a bad guess the same size, never claimed
                    o = {"kind": "bet", "t_issue": time.perf_counter()}
                    th = threading.Thread(target=gated_stream, daemon=True, args=(
                        self.gate, "bet", self.cl, self.model,
                        self.salt + str(prompt) + f" [alt {d}]", base.sub_max_tokens, o),
                        kwargs={"body": {**tag_body(self.tags, "bet"), **self.extra}})
                    with lock:
                        self.decoy_runs.append((th, o))
                    th.start()
            out = {}
            # honour spec-ptc's own eviction, as its SuiteEngine does
            evicted = (lambda: _spec.state == "evicted") if spec else None
            gated_stream(self.gate, kind, self.cl, self.model, self.salt + str(prompt),
                         base.sub_max_tokens, out, natural=self.natural,
                         body={**tag_body(self.tags, kind), **self.extra},
                         should_stop=evicted)
            rec.update(dur=time.perf_counter() - rec["t0"], usage=out.get("usage"),
                       finish=out.get("finish"), stop=out.get("stop"), outcome=outcome(out),
                       tokens=len(out.get("times", [])))
            with lock:
                self.log.append(rec)
                if kind == "bet" and rec["outcome"] == "completed":
                    self.refused_bets.discard(str(prompt))  # a claim takes this one
                elif kind == "bet" and rec["outcome"] != "cancelled":
                    self.refused_bets.add(str(prompt))  # a claim runs it for real
            if rec["outcome"] == "cancelled":
                raise RuntimeError("evicted")
            if rec["outcome"] != "completed":
                rec["refused"] = True
                if kind == "bet":  # refused or dropped (or failed)
                    raise self.rejected(rec["outcome"])
                # refused or dropped by the sptc scheduler (or failed): run it for real now
                fb = {}
                gated_stream(self.gate, "fallback", self.cl, self.model,
                             self.salt + str(prompt), base.sub_max_tokens, fb,
                             natural=self.natural, body=self.extra or None)
                self.log.append({"t0": rec["t0"] + rec["dur"], "spec": False, "kind": "fallback",
                                 "dur": fb.get("end"), "usage": fb.get("usage"),
                                 "finish": fb.get("finish"), "stop": fb.get("stop"),
                                 "outcome": outcome(fb), "tokens": len(fb.get("times", [])),
                                 "prompt_id": rec["prompt_id"]})
                out = fb
            return "".join("x" for _ in out.get("times", [])) or "ok"

        base._call = call

    def stream_main(self, text: str):
        if not self.served:
            yield from self.base.stream_main(text)
            return
        n = max(1, math.ceil(len(text) / 4))
        done = threading.Event()
        out: dict = {}
        self.root_outs.append(out)

        def root():
            gated_stream(self.gate, "root", self.cl, self.model, self.salt + COUNT, n, out,
                         body={**tag_body(self.tags, "root"), **self.extra})
            done.set()

        th = threading.Thread(target=root, daemon=True)
        th.start()
        sent = 0
        while sent < len(text):
            k = len(out.get("times", []))
            target = min(len(text), 4 * k) if not done.is_set() else len(text)
            if target > sent:
                yield text[sent:target]
                sent = target
            else:
                time.sleep(0.002)
        th.join()

    def end_turn(self, join_s: float = 30.0) -> list[dict]:
        """Cancel the decoys still running and return every decoy's record."""
        for _, o in self.decoy_runs:
            cancel(o)
        recs = []
        deadline = time.perf_counter() + join_s
        for th, o in self.decoy_runs:
            th.join(max(0.0, deadline - time.perf_counter()))
            recs.append({"dur": o.get("end"), "tokens": len(o.get("times", [])),
                         "usage": o.get("usage"), "finish": o.get("finish"),
                         "stop": o.get("stop"),
                         "outcome": outcome(o) if o.get("done") else "unfinished"})
        self.decoy_runs.clear()
        return recs

    def __getattr__(self, k):
        return getattr(self.base, k)


def launched_before_first_answer(history) -> int:
    """Speculative calls dispatched before any speculative call had answered."""
    n = 0
    for e in history:
        if e.kind == "ready":
            break
        n += e.kind == "dispatch"
    return n


def run_turn(spec_mods, name, mode, a, served, decoys, tags, log, natural=False, salt="",
             gate=None, cache_salt="", spec_kind="early", scout=False):
    """One session (one spec-ptc turn of one agent). tags: TAG_SCHEMES (a bool is
    accepted for the old --tag-bets flag). gate: a ProxyGate shared by the run's agents.
    cache_salt: vLLM's cache_salt on every request ('': none). spec_kind: Arm.spec_kind."""
    if isinstance(tags, bool):
        tags = "sptc" if tags else "none"
    CONTEXT, PATS, response_text, SuiteEngine, EventBus, Harness = spec_mods
    p = PATS[name]
    base = SuiteEngine(a.base_url, a.model, tps=60.0, sub_max_tokens=p.sub_max_tokens)
    eng = LoggedEngine(base, client(a.base_url), a.model, served, decoys, tags, log, natural,
                       salt, gate, cache_salt, spec_kind)
    # scout: spec-ptc's scout pass (the sptc-hints fork; an older Harness has no such option)
    h = Harness(eng, mode, bus=EventBus(), context=CONTEXT, **({"scout": True} if scout else {}))
    t0 = time.perf_counter()
    for text in p.turns or (response_text(p),):
        h.run_turn(eng.stream_main(text))
    wall = time.perf_counter() - t0
    dec = eng.end_turn()
    h.launcher.shutdown()
    roots = [o for o in eng.root_outs if len(o.get("times", [])) > 1]
    span = sum(o["times"][-1] - o["times"][0] for o in roots)
    gaps = sorted(g for o in roots for g in itl(o["times"]))
    stops = [e.data.get("reason") for e in h.bus.history if e.kind == "shadow_stop"]
    kinds = [e.kind for e in h.bus.history]
    try:
        score = p.check(h.repl.locals) if p.check else None
    except Exception:  # noqa: BLE001 - a pattern's own check must not fail a run
        score = None
    return {"pattern": name, "mode": mode + ("+scout" if scout else ""), "wall_s": wall,
            "score": score,
            "dispatched": kinds.count("dispatch"), "hits": kinds.count("claim_hit"),
            "misses": kinds.count("claim_miss"), "evicted": kinds.count("evict"),
            "launched_before_first_answer": launched_before_first_answer(h.bus.history),
            "root_tpot_ms": 1000 * span / sum(len(o["times"]) - 1 for o in roots) if roots else None,
            "root_itl_p99_ms": 1000 * pctl(gaps, 0.99) if gaps else None,
            "root_tokens": sum(len(o.get("times", [])) for o in eng.root_outs),
            "root_finish": ",".join(str(o.get("finish")) for o in eng.root_outs) or "None",
            "sub_finish": [str(c.get("finish")) for c in log],
            "sub_refused": sum(bool(c.get("refused")) for c in log),
            "calls": [{k: c.get(k) for k in ("kind", "spec", "dur", "usage", "finish", "stop",
                                             "outcome", "tokens", "refused", "at_claim",
                                             "prompt_id")} for c in log],
            "decoys": dec,
            # as the simulator's sessions: the speculative calls sent as bets (spec_kind
            # bet), the refused ones re-run at their claim, and whether the shadow stopped
            # at a refused bet it forced (spec-ptc's shadow.py _abort("force-failed")).
            # Not in the simulator: the distinct calls those bets were for
            "real_bets": [{"outcome": c["outcome"]} for c in log if c["kind"] == "bet"],
            "real_bet_calls": len({c["prompt_id"] for c in log if c["kind"] == "bet"}),
            "reissued": sum(bool(c.get("at_claim")) for c in log),
            "shadow_stopped": "force-failed" in stops, "shadow_stops": stops}


def suite(a) -> dict:
    mods = _spec_ptc(a.spec_ptc)
    rows = []
    modes = [("baseline", False), ("spec", False)] + ([("spec", True)] if a.scout else [])
    for name in a.patterns.split(","):
        for rep in range(a.reps):
            for mode, scout in (modes if rep % 2 == 0 else modes[::-1]):  # ABBA over repeats
                log: list = []
                # natural output lengths: the per-call token counts runs.csv lacks
                r = run_turn(mods, name, mode, a, False, 0, "none", log, natural=True,
                             scout=scout)
                r.update(rep=rep, calls=[{"spec": c["spec"], "dur_s": c["dur"], "usage": c["usage"]}
                                         for c in log])
                rows.append(r)
                print(json.dumps({k: v for k, v in r.items() if k != "calls"}), flush=True)
    return {"suite": rows}


# ----------------------------------------------------------------------------- arms
@dataclass(frozen=True)
class Arm:
    """One measured configuration: which server, which client, which workload."""

    name: str
    server: str  # key of SERVERS
    mode: str  # spec-ptc mode: baseline (no speculation) | spec
    decoys: int  # bad guesses per speculation (raw completions forced to max length)
    tags: str  # client tagging: TAG_SCHEMES (see tag_body)
    workload: str = "mix4"  # key of WORKLOADS
    gate: str = ""  # client-side cap on bets, ProxyGate "MODE:CAP" ("": none)
    # the class of spec-ptc's own speculative calls (SPEC_KINDS): early, as every run
    # before the pressure run; bet, the `both` workload (both arms of a branch launched, one
    # used): tagged, prioritised and capped as bets, a refused one re-run at its claim
    spec_kind: str = "early"


def plugin_cfg(allowance: str = "fixed") -> dict:
    """The plugin's --additional-config; allowance: prefill_allowance fixed | adaptive | off
    (integrations/README.md)."""
    return {"sptc": {"free_window": 8, "kv_reserve": 0.10, "spec_prefill_budget": 512,
                     "prefill_allowance": allowance}}


PLUGIN_CFG = plugin_cfg("fixed")
# Stock and priority servers carry the plugin-fixed arm's exact --additional-config. They
# ignore it, but it is part of vLLM's compile hash (vllm/config/vllm.py:549-557) and
# --scheduler-cls is not, so stock, priority and plugin-fixed compile and run one
# torch.compile artifact (results/t4_run1_analysis/root_cause.md, candidate 8). The adaptive and off
# arms necessarily compile their own; compare allowance modes on the *_eager servers
# (--enforce-eager: no torch.compile, no CUDA graphs, vllm/config/vllm.py ~1691).
SHARED_CFG = ["--additional-config", json.dumps(PLUGIN_CFG)]
PLUGIN_CLS = ["--scheduler-cls", "sptc_vllm.scheduler.SptcScheduler"]
PLUGIN_ENV = {"PYTHONPATH": str(SIM_ROOT / "integrations")}
# server flags appended to --serve-cmd; env added to the server's environment
SERVERS = {
    "fcfs": {"flags": [*SHARED_CFG], "env": {}},
    "priority": {"flags": ["--scheduling-policy", "priority", *SHARED_CFG], "env": {}},
    "plugin": {"flags": [*PLUGIN_CLS, *SHARED_CFG], "env": PLUGIN_ENV},
    "plugin_adaptive": {"flags": [*PLUGIN_CLS, "--additional-config",
                                  json.dumps(plugin_cfg("adaptive"))], "env": PLUGIN_ENV},
    "plugin_off": {"flags": [*PLUGIN_CLS, "--additional-config", json.dumps(plugin_cfg("off"))],
                   "env": PLUGIN_ENV},
}
for _k in ("fcfs", "plugin", "plugin_adaptive", "plugin_off"):
    SERVERS[_k + "_eager"] = {"flags": [*SERVERS[_k]["flags"], "--enforce-eager"],
                              "env": SERVERS[_k]["env"]}
# The pressure run: KV pressure and a real queue on the T4. The simulated study chose the config from
# the stock FCFS arms (results/pressure, flags in results/prereg_v4); its fallback, half
# the blocks, runs only if the probe shows no pressure (results/prereg_v4_fallback).
# --max-model-len goes in --serve-cmd (PRESSURE_SERVE_CMD; sweep checks it): vLLM starts
# only if the blocks hold one request of that length.
PRESSURE_CONFIGS = {"chosen": {"num_gpu_blocks_override": 257, "max_num_seqs": 256},
                    "fallback": {"num_gpu_blocks_override": 129, "max_num_seqs": 256}}
PRESSURE_MAX_LEN = 512
PRESSURE_SERVE_CMD = (f"vllm serve {{model}} --dtype half --max-model-len {PRESSURE_MAX_LEN} "
                      "--gpu-memory-utilization 0.90 --port {port}")
PRESSURE_SERVERS = ("fcfs_p", "priority_p", "plugin_p")


def pressure_flags(config: str) -> list[str]:
    c = PRESSURE_CONFIGS[config]
    return ["--num-gpu-blocks-override", str(c["num_gpu_blocks_override"]),
            "--max-num-seqs", str(c["max_num_seqs"])]


def pressure_servers(config: str) -> dict:
    """fcfs_p, priority_p, plugin_p: fcfs, priority and plugin with one config's flags.
    They keep SHARED_CFG, so all three run one compiled artifact."""
    return {k + "_p": {"flags": [*SERVERS[k]["flags"], *pressure_flags(config)],
                       "env": SERVERS[k]["env"]} for k in ("fcfs", "priority", "plugin")}


SERVERS.update(pressure_servers("chosen"))  # main() applies --pressure-config
# the prefill_allowance each server runs with (None: not the plugin); for the predictions
ALLOWANCE = {k: (None if not k.startswith("plugin") else
                 "adaptive" if "adaptive" in k else "off" if "_off" in k else "fixed")
             for k in SERVERS}
WORKLOADS = {
    # the T4 load test's mix (results/kaggle_t4/RESULTS.md section 3)
    "mix4": {"patterns": "map16,map_reduce,two_stage,side_branch_chain", "turns": 4},
}
WINDOW_CAP = f"window:{PLUGIN_CFG['sptc']['free_window']}"  # run 2's client-side cap
ARMS = [
    Arm("fcfs/nospec", "fcfs", "baseline", 0, "none"),
    Arm("fcfs/spec", "fcfs", "spec", 0, "none"),
    Arm("fcfs/spec+bad", "fcfs", "spec", 1, "none"),
    Arm("prio/nospec", "priority", "baseline", 0, "priority"),
    Arm("prio/spec", "priority", "spec", 0, "priority"),
    Arm("prio/spec+bad", "priority", "spec", 1, "priority"),
    Arm("plugin/nospec", "plugin", "baseline", 0, "sptc"),
    Arm("plugin/spec", "plugin", "spec", 0, "sptc"),
    Arm("plugin/spec+bad", "plugin", "spec", 1, "sptc"),
    # the regression A/B (results/t4_run1_analysis/root_cause.md): allowance modes,
    # the plugin server with untagged traffic, and eager launches of every arm
    Arm("plugin-adaptive/spec", "plugin_adaptive", "spec", 0, "sptc"),
    Arm("plugin-adaptive/spec+bad", "plugin_adaptive", "spec", 1, "sptc"),
    Arm("plugin-off/spec", "plugin_off", "spec", 0, "sptc"),
    Arm("plugin-off/spec+bad", "plugin_off", "spec", 1, "sptc"),
    Arm("plugin-untagged/spec", "plugin", "spec", 0, "none"),
    Arm("fcfs-eager/spec", "fcfs_eager", "spec", 0, "none"),
    Arm("plugin-eager/spec", "plugin_eager", "spec", 0, "sptc"),
    Arm("plugin-adaptive-eager/spec", "plugin_adaptive_eager", "spec", 0, "sptc"),
    Arm("plugin-off-eager/spec", "plugin_off_eager", "spec", 0, "sptc"),
    # stock FCFS again, launched next to the priority runs (prio8): the priority claims'
    # denominators otherwise come from launches hours earlier
    Arm("fcfs-adj/spec", "fcfs", "spec", 0, "none"),
    Arm("fcfs-adj/spec+bad", "fcfs", "spec", 1, "none"),
    # fairer baselines (preset `baselines`, notebook section B4), all with bad guesses:
    # vLLM priority with only the bets at low priority; a client-side cap on bets on stock
    # FCFS, in the two ProxyGate modes, its cap the plugin's free window (fixed in advance,
    # not tuned); and stock FCFS and the plugin launched next to them
    Arm("prio-bets/spec+bad", "priority", "spec", 1, "priority_bets"),
    Arm("proxy/spec+bad", "fcfs", "spec", 1, "none",
        gate=f"window:{PLUGIN_CFG['sptc']['free_window']}"),
    Arm("proxy-sem/spec+bad", "fcfs", "spec", 1, "none",
        gate=f"bets:{PLUGIN_CFG['sptc']['free_window']}"),
    Arm("fcfs-b4/spec+bad", "fcfs", "spec", 1, "none"),
    Arm("plugin-b4/spec+bad", "plugin", "spec", 1, "sptc"),
    # B4's no-bets reference: stock FCFS, speculation without bad guesses. In B4 every bet
    # is a worthless decoy, so this is what a gate that refuses every bet achieves
    Arm("fcfs-b4/spec", "fcfs", "spec", 0, "none"),
    # The pressure run (preset `pressure`, results/prereg_v4): the pressure servers, only
    # the bets tagged, the cap run 2's window. spec+bad: one decoy per speculative call
    # (workload `decoys`); both: the speculative calls are bets too, each with a decoy, so
    # half the bets are needed. No fcfs-p/both: on stock FCFS it is fcfs-p/spec+bad
    Arm("fcfs-p/nospec", "fcfs_p", "baseline", 0, "none"),
    Arm("fcfs-p/spec", "fcfs_p", "spec", 0, "none"),
    Arm("fcfs-p/spec+bad", "fcfs_p", "spec", 1, "none"),
    Arm("prio-p/spec+bad", "priority_p", "spec", 1, "priority_bets"),
    Arm("cap-p/spec+bad", "fcfs_p", "spec", 1, "none", gate=WINDOW_CAP),
    Arm("plugin-p/spec+bad", "plugin_p", "spec", 1, "sptc_bets"),
    Arm("prio-p/both", "priority_p", "spec", 1, "priority_bets", spec_kind="bet"),
    Arm("cap-p/both", "fcfs_p", "spec", 1, "none", gate=WINDOW_CAP, spec_kind="bet"),
    Arm("plugin-p/both", "plugin_p", "spec", 1, "sptc_bets", spec_kind="bet"),
    # Its step 5 (preset both_default, results/prereg_v4b): `both` on the default
    # servers, no pressure: what a fixed window costs when bets are often needed
    Arm("fcfs-d/nospec", "fcfs", "baseline", 0, "none"),
    Arm("fcfs-d/spec", "fcfs", "spec", 0, "none"),
    Arm("fcfs-d/spec+bad", "fcfs", "spec", 1, "none"),
    Arm("prio-d/both", "priority", "spec", 1, "priority_bets", spec_kind="bet"),
    Arm("cap-d/both", "fcfs", "spec", 1, "none", gate=WINDOW_CAP, spec_kind="bet"),
    Arm("plugin-d/both", "plugin", "spec", 1, "sptc_bets", spec_kind="bet"),
]
BASELINE_ARMS = ["fcfs-b4/spec+bad", "proxy/spec+bad", "proxy-sem/spec+bad",
                 "prio-bets/spec+bad", "plugin-b4/spec+bad"]
BASELINE_REF = "fcfs-b4/spec+bad"  # the B4 ratios' denominator (same launches as the proxy)
BASELINE_NOBETS = "fcfs-b4/spec"  # the no-bets reference (prereg_v3b, claims B4C-*)
B4_ARMS = [*BASELINE_ARMS, BASELINE_NOBETS]
# The pressure run: the Pressure table's groups, each reference arm with its arms, and the
# decision rule's arms per workload (plugin, cap, priority). The rule: the plugin wins if
# its session p50 is at least D1_MARGIN below the cap's at 4 agents, in `decoys` or `both`
# on the pressure servers, with the pressure check passed (PRESSURE_CLEAR on
# fcfs-p/spec+bad, PRESSURE_QUIET on fcfs-p/spec: experiments/pressure.py's thresholds)
PRESSURE_ARMS = [x.name for x in ARMS if x.server in PRESSURE_SERVERS]
PRESSURE_REF = "fcfs-p/spec+bad"
BOTH_DEFAULT_ARMS = ["fcfs-d/nospec", "fcfs-d/spec", "fcfs-d/spec+bad", "prio-d/both",
                     "cap-d/both", "plugin-d/both"]
BOTH_DEFAULT_REF = "fcfs-d/spec+bad"
PRESSURE_GROUPS = {PRESSURE_REF: PRESSURE_ARMS, BOTH_DEFAULT_REF: BOTH_DEFAULT_ARMS}
D1_ARMS = {"decoys": ("plugin-p/spec+bad", "cap-p/spec+bad", "prio-p/spec+bad"),
           "both": ("plugin-p/both", "cap-p/both", "prio-p/both"),
           "both, default servers": ("plugin-d/both", "cap-d/both", "prio-d/both")}
D1_RULE = ("decoys", "both")  # the default servers have no pressure: reported, not ruled
D1_MARGIN = 0.05
D1_AGENTS = 4
PRESSURE_CLEAR = {"preemptions": 16, "queue_frac": 0.25}  # per run: preempts or queues clearly
PRESSURE_QUIET = {"preemptions": 2, "queue_frac": 0.05}  # per run: barely does
ARM = {x.name: x for x in ARMS}
_SWEEP_ARMS = ARMS[:9]
# a preset: arms, ladder, repeats; optional: turns, reps_at {load: repeats}, only {arm:
# [loads]} (an arm runs at these loads only), rounds (each server is launched `rounds`
# times, in turn, and repeat r runs in launch r % rounds), warm_pass (one throwaway
# 1-agent run of the server's first arm after each launch, results/t4_run1_analysis protocol),
# same_prompts (every arm sends the same prompts; runs that share a launch are kept apart
# in the prefix cache by vLLM's cache_salt instead of the prompt text, see run_point).
# With rounds > 1 odd rounds launch the servers in reverse order (ABBA).
PRESETS = {
    "full": {"arms": [x.name for x in _SWEEP_ARMS], "agents": "1,2,4,8,12,16,24,32", "reps": 3},
    "core": {"arms": ["fcfs/nospec", "fcfs/spec", "fcfs/spec+bad", "prio/spec",
                      "prio/spec+bad", "plugin/spec", "plugin/spec+bad"],
             "agents": "1,4,8,16,24", "reps": 3},
    "quick": {"arms": ["fcfs/nospec", "fcfs/spec+bad", "prio/spec+bad", "plugin/spec+bad"],
              "agents": "1,4", "reps": 1, "turns": 2},
    # regression A/B, compiled: stock vs plugin fixed / adaptive / off; 1-agent rows 5 times
    "ab": {"arms": ["fcfs/nospec", "fcfs/spec", "fcfs/spec+bad", "plugin/spec",
                    "plugin/spec+bad", "plugin-untagged/spec", "plugin-adaptive/spec",
                    "plugin-adaptive/spec+bad", "plugin-off/spec", "plugin-off/spec+bad"],
           "agents": "1,4,8", "reps": 3, "reps_at": {1: 5}, "rounds": 2, "warm_pass": True,
           "only": {"fcfs/nospec": [1], "plugin-untagged/spec": [1]}},
    # the same at 1 agent on --enforce-eager launches: the allowance modes with the code
    # equal; two launches per server, so the eager rows have a launch-to-launch noise floor
    "ab_eager": {"arms": ["fcfs-eager/spec", "plugin-eager/spec", "plugin-adaptive-eager/spec",
                          "plugin-off-eager/spec"],
                 "agents": "1", "reps": 5, "rounds": 2, "warm_pass": True},
    # vLLM's own priority scheduling at 8 agents, with stock FCFS launched next to it
    # (priority, stock, stock, priority)
    "prio8": {"arms": ["prio/spec", "prio/spec+bad", "fcfs-adj/spec", "fcfs-adj/spec+bad"],
              "agents": "8", "reps": 3, "rounds": 2, "warm_pass": True},
    # fairer baselines: bets-only priority, a client-side cap on bets (two modes), stock and
    # the plugin, and stock without bets, at 8 agents (and 4); servers fcfs, priority,
    # plugin, then in reverse. Every arm sends the same prompts
    "baselines": {"arms": B4_ARMS, "agents": "8,4", "reps": 3, "rounds": 2,
                  "warm_pass": True, "same_prompts": True},
    # The pressure run, on the pressure servers (--serve-cmd PRESSURE_SERVE_CMD,
    # --pressure-config). probe: one fcfs_p launch, stock FCFS with and without bad guesses
    # once each; probe_verdict picks the config from it. pressure: every arm, servers
    # fcfs_p, priority_p, plugin_p, then in reverse; same prompts on every arm
    "probe": {"arms": ["fcfs-p/spec", "fcfs-p/spec+bad"], "agents": "4", "reps": 1,
              "rounds": 1, "warm_pass": True, "same_prompts": True},
    "pressure": {"arms": PRESSURE_ARMS, "agents": "4", "reps": 3, "rounds": 2,
                 "warm_pass": True, "same_prompts": True},
    # step 5: `both` on the default servers, the same protocol (default --serve-cmd)
    "both_default": {"arms": BOTH_DEFAULT_ARMS, "agents": "4", "reps": 3, "rounds": 2,
                     "warm_pass": True, "same_prompts": True},
}
SLO_REF = "fcfs/nospec"  # goodput thresholds are multiples of this arm's 1-agent sessions


# ----------------------------------------------------------------------------- runs
def run_file(out: Path, arm: str, agents: int, rep: int) -> Path:
    safe = arm.replace("/", "__").replace("+", "_plus_")
    return out / "sweep" / "runs" / f"{safe}__n{agents}__r{rep}.json"


def load_runs(out: Path) -> list[dict]:
    runs = []
    for f in sorted((out / "sweep" / "runs").glob("*.json")):
        try:
            runs.append(json.loads(f.read_text()))
        except (OSError, json.JSONDecodeError):
            pass  # a half-written file from a killed session: rerun it
    return runs


def save_run(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, default=str))
    os.replace(tmp, path)  # atomic: a crash leaves the old file or none


def _sweep_agent(ns: dict, i: int, arm: dict, salt: str, q, go, gate=None,
                 cache_salt: str = "") -> None:
    """One agent in its own process: spec-ptc's REPL redirects stdout/stderr with
    contextlib (process-global), so concurrent agents must not share a process. Every
    failure is reported to the parent (the first T4 load test failed silently here)."""
    global TAG_FIELD
    try:
        a = argparse.Namespace(**ns)
        TAG_FIELD = TAG_FIELDS[a.engine]  # a spawned process starts from the module default
        mods = _spec_ptc(a.spec_ptc)
        mix = a.patterns.split(",")
    except BaseException:  # noqa: BLE001
        q.put(("done", i, {"sessions": [], "cpu_s": 0.0, "error": traceback.format_exc()}))
        return
    q.put(("ready", i, None))
    if not go.wait(a.run_timeout):
        return
    cpu0, sessions, err = time.process_time(), [], None
    try:
        for j in range(a.turns):
            r = run_turn(mods, mix[(i + j) % len(mix)], arm["mode"], a, True, arm["decoys"],
                         arm["tags"], [], natural=True, salt=salt, gate=gate,
                         cache_salt=cache_salt, spec_kind=arm["spec_kind"])
            r.update(agent=i, turn=j)
            sessions.append(r)
    except BaseException:  # noqa: BLE001
        err = traceback.format_exc()
    q.put(("done", i, {"sessions": sessions, "cpu_s": time.process_time() - cpu0, "error": err}))


def cpu_times(text: str) -> tuple[float, float] | None:
    """(busy, total) jiffies of all CPUs from /proc/stat text; None if absent."""
    for line in text.splitlines():
        if line.startswith("cpu "):
            v = [float(x) for x in line.split()[1:9]]  # user..steal; guest is inside user
            idle = v[3] + v[4]  # idle + iowait
            return sum(v) - idle, sum(v)
    return None


class HostCpu:
    """Whole-host CPU use from /proc/stat (Linux; None elsewhere): every process, so the
    vLLM API server and engine core count too, not only the agents. mean over the run,
    peak 1-s interval, and the fraction of 1-s intervals at >= SAT busy."""

    SAT = 0.95

    def __init__(self, path: str = "/proc/stat") -> None:
        self.path = path
        self.first = self.last = None
        self.parts: list[float] = []

    def read(self) -> tuple[float, float] | None:
        try:
            with open(self.path) as f:
                return cpu_times(f.read())
        except OSError:
            return None

    def sample(self) -> None:
        t = self.read()
        if t is None:
            return
        if self.last is not None and t[1] > self.last[1]:
            self.parts.append((t[0] - self.last[0]) / (t[1] - self.last[1]))
        self.first = self.first or t
        self.last = t

    def result(self) -> dict:
        if self.first is None or self.last[1] <= self.first[1]:
            return {"host_cpu_util": None, "host_cpu_peak": None, "host_cpu_sat_frac": None}
        n = len(self.parts)
        return {"host_cpu_util": (self.last[0] - self.first[0]) / (self.last[1] - self.first[1]),
                "host_cpu_peak": max(self.parts) if n else None,
                "host_cpu_sat_frac": sum(x >= self.SAT for x in self.parts) / n if n else None}


GPU_FIELDS = {"sm_mhz": "clocks.sm", "mem_mhz": "clocks.mem", "temp_c": "temperature.gpu",
              "power_w": "power.draw"}
# the active clock-limit reasons bitmask (0x0: none); renamed in newer drivers
GPU_REASONS = ["clocks_event_reasons.active", "clocks_throttle_reasons.active"]


def _smi(fields: str) -> str | None:
    try:
        r = subprocess.run(["nvidia-smi", "-i", "0", f"--query-gpu={fields}",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else None


def gpu_state() -> dict | None:
    """GPU 0's SM and memory clocks (MHz), temperature (C), power (W) and clock-limit
    reasons, from nvidia-smi; None without one. A T4 that warms up and drops its clocks
    over a block of runs would otherwise look like a slower arm."""
    line = _smi(",".join(GPU_FIELDS.values()))
    if line is None:
        return None
    out = {}
    for k, v in zip(GPU_FIELDS, line.split(",")):
        try:
            out[k] = float(v)
        except ValueError:  # [N/A]
            out[k] = None
    while GPU_REASONS:
        r = _smi(GPU_REASONS[0])
        if r is not None:
            out["reasons"] = r.strip()
            break
        GPU_REASONS.pop(0)  # this driver does not know the field: try the other name
    return out


class GpuLog:
    """gpu_state() samples over a run: clock min/max/mean, peak temperature and power,
    the clock-limit reasons seen."""

    def __init__(self) -> None:
        self.xs: list[dict] = []

    def sample(self) -> None:
        g = gpu_state()
        if g is not None:
            self.xs.append(g)

    def result(self) -> dict | None:
        if not self.xs:
            return None
        col = lambda k: [x[k] for x in self.xs if x.get(k) is not None]  # noqa: E731
        sm = col("sm_mhz")
        return {"samples": len(self.xs), "sm_mhz_min": min(sm, default=None),
                "sm_mhz_max": max(sm, default=None),
                "sm_mhz_mean": statistics.mean(sm) if sm else None,
                "temp_c_first": self.xs[0].get("temp_c"), "temp_c_max": max(col("temp_c"),
                                                                             default=None),
                "power_w_max": max(col("power_w"), default=None),
                "reasons": sorted({x["reasons"] for x in self.xs if x.get("reasons")})}


class MetricsPoller:
    """Polls the server's Prometheus /metrics while a run is going: peak running/waiting
    requests and KV use, the preemption counter's increase, and the share of samples
    with a request waiting (waiting_frac). All None if absent. Also samples the host's
    CPU use (HostCpu) on the same clock."""

    GAUGES = {"running": ("num_requests_running",), "waiting": ("num_requests_waiting",),
              "kv": ("kv_cache_usage_perc", "gpu_cache_usage_perc")}
    # prefix-cache counters (tokens queried / hit; vLLM V1's vllm:prefix_cache_*): a check
    # that runs sharing a launch did not hit each other's prefixes
    COUNTERS = {"preemptions": ("num_preemptions_total", "num_preemptions"),
                "prefix_queries": ("prefix_cache_queries_total", "prefix_cache_queries"),
                "prefix_hits": ("prefix_cache_hits_total", "prefix_cache_hits")}

    GPU_EVERY = 5  # nvidia-smi every 5th sample: it costs host CPU too

    def __init__(self, ep: Endpoint, every: float = 1.0) -> None:
        self.ep, self.every = ep, every
        self.peak: dict = {k: None for k in self.GAUGES}
        self.waits: list[bool] = []  # per sample read: a request waiting (the queue's share)
        self.first: dict = {}
        self.last: dict = {}
        self.cpu = HostCpu()
        self.gpu = GpuLog()
        self.n = 0
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._loop, daemon=True)

    @staticmethod
    def parse(text: str, names: tuple) -> float | None:
        """Sum of a metric over its label sets; first matching name wins."""
        for want in names:
            tot, seen = 0.0, False
            for line in text.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                name = line.split("{", 1)[0].split(" ", 1)[0]
                if name.split(":", 1)[-1] != want:
                    continue
                try:
                    tot += float(line.rsplit(" ", 1)[1])
                    seen = True
                except ValueError:
                    pass
            if seen:
                return tot
        return None

    def sample(self) -> None:
        self.cpu.sample()
        if self.n % self.GPU_EVERY == 0:
            self.gpu.sample()
        self.n += 1
        try:
            text = self.ep.get("/metrics", timeout=3.0)
        except Exception:  # noqa: BLE001 - metrics are optional
            return
        for k, names in self.GAUGES.items():
            v = self.parse(text, names)
            if v is not None:
                self.peak[k] = v if self.peak[k] is None else max(self.peak[k], v)
                if k == "waiting":
                    self.waits.append(v > 0)
        for k, names in self.COUNTERS.items():
            v = self.parse(text, names)
            if v is not None:
                self.first.setdefault(k, v)
                self.last[k] = v

    def _loop(self) -> None:
        while not self._stop.wait(self.every):
            self.sample()

    def __enter__(self):
        self.sample()
        self._th.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._th.join(5)
        self.n = 0  # the last sample reads the GPU too
        self.sample()

    def result(self) -> dict:
        res = {f"max_{k}": v for k, v in self.peak.items()}
        for k in self.COUNTERS:
            res[k] = self.last[k] - self.first[k] if k in self.last else None
        res["waiting_frac"] = sum(self.waits) / len(self.waits) if self.waits else None
        return res


def run_salt(arm: Arm, agents: int, rep: int, attempt: int = 0, variant: int = 0,
             same_prompts: bool = False, by_salt: bool = False,
             no_salt: bool = False) -> tuple[str, str]:
    """(prompt prefix, cache_salt) of one run. Every prompt starts with the run's prefix.
    It names the client workload, load and repeat but not the arm, so stock and plugin
    arms send the same prompts: sub-calls are natural-length greedy completions, and a
    different prefix can change their length. Runs on one launch never share a prefix
    (repeat, salt_variants, retry attempt): no prefix-cache hits across runs. Each launch
    starts with an empty prefix cache. same_prompts: the number of bad guesses is left
    out too. by_salt: arms that share a launch send the same text, and a variant > 0 sets
    vLLM's cache_salt instead (it enters the first block's hash: a prefix cache of its
    own); otherwise the variant is numbered in the prefix."""
    if no_salt:
        return "", ""
    label = arm.mode if same_prompts else f"{arm.mode} d{arm.decoys}"
    v = f" v{variant}" if variant and not by_salt else ""
    salt = f"[{label}{v} n{agents} r{rep}{f' a{attempt}' if attempt else ''}] "
    return salt, (f"sptc-v{variant}" if variant and by_salt else "")


def run_point(a, arm: Arm, agents: int, rep: int, attempt: int = 0, warm: str = "",
              variant: int = 0, same_prompts: bool = False, by_salt: bool = False) -> dict:
    """N agents x `turns` sessions of one arm, all agents released together. warm: the
    launch this is the throwaway warm-up pass of (its own prompt prefix). variant: see
    salt_variants; same_prompts, by_salt: see run_salt."""
    import multiprocessing as mp
    import queue

    wl = WORKLOADS[arm.workload]
    ns = dict(vars(a))
    ns.update(patterns=wl["patterns"], turns=a.turns or wl["turns"])
    ns = {k: v for k, v in ns.items() if isinstance(v, (str, int, float, bool, type(None)))}
    salt, cache_salt = run_salt(arm, agents, rep, attempt, variant, same_prompts, by_salt,
                                a.no_salt)
    if warm:
        salt, cache_salt = f"[warmup-pass {warm}] ", ""
    rec = {**asdict(arm), "arm": arm.name, "agents": agents, "rep": rep,
           "turns": ns["turns"], "patterns": wl["patterns"], "salt": salt,
           "cache_salt": cache_salt or None,
           "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "status": "ok", "errors": [], "sessions": []}
    del rec["name"]
    ctx = mp.get_context("spawn")
    q, go = ctx.Queue(), ctx.Event()
    gate = ProxyGate(arm.gate, ctx) if arm.gate else None
    procs = [ctx.Process(target=_sweep_agent,
                         args=(ns, i, asdict(arm), salt, q, go, gate, cache_salt), daemon=True)
             for i in range(agents)]
    for p in procs:
        p.start()
    ready, results = set(), {}
    deadline = time.perf_counter() + a.start_timeout
    while len(ready) + len(results) < agents and time.perf_counter() < deadline:
        try:
            kind, i, payload = q.get(timeout=1.0)
        except queue.Empty:
            if any(p.exitcode is not None for p in procs):
                break
            continue
        if kind == "ready":
            ready.add(i)
        else:
            results[i] = payload  # an import failure
    if len(ready) < agents:
        rec["status"] = "error"
        rec["errors"].append(f"only {len(ready)}/{agents} agents started")
    t0 = time.perf_counter()
    with MetricsPoller(client(a.base_url)) as mon:
        if rec["status"] == "ok":
            go.set()
            deadline = t0 + a.run_timeout
            while len(results) < agents:
                left = deadline - time.perf_counter()
                if left <= 0:
                    rec["status"] = "timeout"
                    break
                try:
                    kind, i, payload = q.get(timeout=min(5.0, left))
                    results[i] = payload
                except queue.Empty:
                    dead = [k for k, p in enumerate(procs)
                            if p.exitcode is not None and k not in results]
                    if dead:
                        rec["status"] = "error"
                        rec["errors"].append(f"agent processes {dead} died: exit codes "
                                             f"{[procs[k].exitcode for k in dead]}")
                        break
    rec["makespan_s"] = time.perf_counter() - t0
    if gate is not None:
        rec["proxy"] = gate.stats()
    rec["server_metrics"] = mon.result()
    rec.update(mon.cpu.result())
    rec["gpu"] = mon.gpu.result()
    for p in procs:
        p.join(5)
        if p.is_alive():
            p.terminate()
    cpu = 0.0
    for i in sorted(results):
        res = results[i]
        rec["sessions"] += res["sessions"]
        cpu += res["cpu_s"]
        if res.get("error"):
            rec["status"] = "error"
            rec["errors"].append(f"agent {i}: {res['error'][-1500:]}")
    # the agents' own CPU, as a share of the host, averaged over the run. It leaves out
    # vLLM's processes on the same box: host_cpu_util (above) is the validity check.
    rec["client_cpu_util"] = cpu / max(1e-9, rec["makespan_s"] * (os.cpu_count() or 1))
    if rec["status"] == "ok":
        if len(rec["sessions"]) != agents * ns["turns"]:
            rec["status"] = "invalid"
            rec["errors"].append(f"{len(rec['sessions'])} sessions, expected "
                                 f"{agents * ns['turns']}")
        bad = [s for s in rec["sessions"] if s["root_tokens"] == 0
               or any(f != "length" for f in s["root_finish"].split(","))]
        if bad:  # the silent failure of the first T4 load test: a root stream got nothing
            rec["status"] = "invalid"
            rec["errors"].append(f"{len(bad)} sessions with a failed root stream: "
                                 f"{sorted({s['root_finish'] for s in bad})}")
    return rec


# ----------------------------------------------------------------------------- servers
class ServerFailed(RuntimeError):
    """A server that did not come up (exited, timed out, or the port was taken)."""


FILLED: set = set()  # compile groups a launch of this process found or left in the cache


def compile_group(flags: list[str]) -> tuple:
    """Servers in one group compile to one torch.compile artifact: --additional-config is
    part of vLLM's compile hash, --scheduler-cls and --scheduling-policy are not
    (vllm/config/vllm.py ~549-557); --enforce-eager compiles nothing."""
    cfg = flags[flags.index("--additional-config") + 1] if "--additional-config" in flags else ""
    return (cfg, "--enforce-eager" in flags)


def fresh_compile(info: dict) -> bool | None:
    """Did this launch compile from scratch (an empty torch.compile cache)? None: the log
    says nothing either way (eager, the fake server). vLLM 0.32 prints 'Using cache
    directory' and 'saved AOT compiled function' on a fresh compile and only 'Directly
    load AOT compilation' on a cached one (results/kaggle_t4/sptc_out/vllm*.log)."""
    if info.get("enforce_eager") or info.get("aot_loaded"):
        return False
    if info.get("aot_saved") or info.get("cache_dir") or info.get("graph_compile_s"):
        return True
    return None


class ServerProc:
    """`vllm serve` (or --serve-cmd) with one SERVERS entry's flags, for --launch."""

    def __init__(self, a, name: str) -> None:
        self.a, self.name = a, name
        port = urllib.parse.urlsplit(a.base_url).port or 8000
        spec = SERVERS[name]
        self.cmd = shlex.split(a.serve_cmd.format(model=a.model, port=port)) + spec["flags"]
        self.group = compile_group(spec["flags"])
        self.env = dict(os.environ)
        for k, v in spec["env"].items():
            self.env[k] = v + (os.pathsep + self.env[k] if self.env.get(k) else "")
        self.log = Path(a.out) / "sweep" / f"server_{name}.log"
        self.p: subprocess.Popen | None = None
        self.launches = 0  # numbered across rounds and resumed sessions; failed ones not
        rec = self.log.parent / "launches.jsonl"
        if rec.exists():
            self.launches = sum(x.get("server") == name and x.get("status", "up") == "up"
                                for x in map(json.loads, filter(str.strip,
                                                                rec.read_text().splitlines())))

    def start(self) -> None:
        """Launch and wait until it serves. A launch that compiled fresh only fills the
        compile cache: it is stopped and launched again, so every measured launch loads
        the artifact (results/t4_run1_analysis/root_cause.md, protocol step 1). Once per compile group
        and process; --no-cache-fill measures on whatever launch comes up."""
        rec = self._launch()
        if rec["role"] == "cache_fill":
            print(f"[sweep] {rec['launch']} compiled fresh: relaunching to measure on the "
                  "cached artifact", flush=True)
            self.stop()
            rec = self._launch()
        if rec["fresh_compile"] and rec["role"] == "measure" and self.a.cache_fill:
            print(f"[sweep] WARNING {rec['launch']} compiled fresh again: measuring on it "
                  "(see launches.jsonl)", flush=True)

    def _launch(self) -> dict:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        if healthy(self.a.base_url):  # left over from a timed-out start, another cell...
            self._failed(f"a server already answers at {self.a.base_url}: stop it first "
                         "(pkill -f 'vllm serve'); not launching over it", None)
        print(f"[sweep] starting {self.name}: {shlex.join(self.cmd)}", flush=True)
        offset = self.log.stat().st_size if self.log.exists() else 0
        t0 = time.time()
        self.p = subprocess.Popen(self.cmd, stdout=open(self.log, "a"), stderr=subprocess.STDOUT,
                                  env=self.env)
        deadline = time.time() + self.a.server_timeout
        while time.time() < deadline:
            if self.p.poll() is not None:
                self.p = None
                self._failed("server exited:\n" + self.log.read_text()[-3000:], t0)
            if healthy(self.a.base_url):
                if self.p.poll() is not None:  # another process answered
                    self.p = None
                    self._failed("server exited:\n" + self.log.read_text()[-3000:], t0)
                self.launches += 1
                return self._record(offset, time.time() - t0)
            time.sleep(2)
        self.stop()  # do not leave it holding the port and the GPU
        self._failed(f"not up after {self.a.server_timeout} s", t0)

    def _failed(self, why: str, t0: float | None) -> None:
        rec = {"launch": f"{self.name}#failed", "server": self.name, "status": "failed",
               "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "startup_s": None if t0 is None else round(time.time() - t0, 1),
               "cmd": self.cmd, "error": why[-1500:]}
        with open(self.log.parent / "launches.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        raise ServerFailed(f"{self.name}: {why}")

    def _record(self, offset: int, startup_s: float) -> dict:
        """One line per launch in sweep/launches.jsonl: which compiled code it runs, and
        whether it only fills the compile cache (role cache_fill) or is measured."""
        with open(self.log, "rb") as f:
            f.seek(offset)
            text = f.read().decode(errors="replace")
        info = launch_info(text)
        fresh = fresh_compile(info)
        fill = bool(fresh) and self.a.cache_fill and self.group not in FILLED
        if fresh is not None:
            FILLED.add(self.group)
        rec = {"launch": f"{self.name}#{self.launches}", "server": self.name, "status": "up",
               "role": "cache_fill" if fill else "measure", "fresh_compile": fresh,
               "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "startup_s": round(startup_s, 1), "cmd": self.cmd, **info, "gpu": gpu_state()}
        with open(self.log.parent / "launches.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[sweep] launch {rec['launch']}: up in {rec['startup_s']} s, "
              f"fresh compile {fresh}, aot loaded {bool(rec['aot_loaded'])}, "
              f"sptc {rec['sptc_line']}", flush=True)
        return rec

    def alive(self) -> bool:
        return self.p is not None and self.p.poll() is None and healthy(self.a.base_url)

    def stop(self) -> None:
        if self.p is None:
            return
        self.p.terminate()
        try:
            self.p.wait(timeout=120)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait()
        self.p = None
        time.sleep(self.a.server_gap)  # let the GPU memory go


def healthy(base_url: str) -> bool:
    try:
        client(base_url).get("models", timeout=3.0)
        return True
    except Exception:  # noqa: BLE001
        return False


def warmup(a) -> None:
    cl = client(a.base_url)
    for i in range(3):
        stream(cl, a.model, f"[warmup {i}] " + COUNT, 32, {})
        stream(cl, a.model, f"[warmup {i}] Say hi.", 8, {}, natural=True)


def cache_salt_ok(a) -> bool:
    """Does the server take vLLM's per-request cache_salt (chat and completions requests,
    vllm/entrypoints/openai/*/protocol.py; it enters the first block's hash)? One 1-token
    chat request; a server that refuses the field answers HTTP 400."""
    o: dict = {}
    stream(client(a.base_url), a.model, "[cache_salt check] Say hi.", 1, o, natural=True,
           body={"cache_salt": "sptc-check"})
    return o.get("finish") in ("length", "stop")


def saturated(runs: list[dict], arm: str, agents: int, factor: float) -> str | None:
    """Why the ladder should stop for this arm after `agents`, or None. Past saturation:
    a run timed out, or session p50 exceeds `factor` x the arm's own 1-agent p50."""
    mine = [r for r in runs if r["arm"] == arm]
    here = [r for r in mine if r["agents"] == agents]
    if any(r["status"] == "timeout" for r in here):
        return "timeout"
    lo = min((r["agents"] for r in mine if r["status"] == "ok"), default=None)
    if lo is None or lo == agents:
        return None
    p_lo = pctl([s["wall_s"] for r in mine if r["agents"] == lo and r["status"] == "ok"
                 for s in r["sessions"]], 0.5)
    p_n = pctl([s["wall_s"] for r in here if r["status"] == "ok" for s in r["sessions"]], 0.5)
    if p_lo and p_n and p_n > factor * p_lo:
        return f"session p50 {p_n:.1f} s > {factor} x {p_lo:.1f} s at {lo} agent(s)"
    return None


def select(a) -> tuple[list[Arm], list[int], int]:
    pre = PRESETS[a.preset]
    arms = [ARM[n] for n in (a.arms or ",".join(pre["arms"])).split(",")]
    agents = [int(x) for x in (a.agents or pre["agents"]).split(",")]
    reps = a.reps if a.reps is not None else pre["reps"]
    if a.turns is None and "turns" in pre:
        a.turns = pre["turns"]
    return arms, agents, reps


def reps_for(a, n: int, reps: int) -> int:
    """Repeats at load n: the preset's reps_at overrides, unless --reps was given."""
    if a.reps is not None:
        return reps
    return PRESETS[a.preset].get("reps_at", {}).get(n, reps)


def runs_at(a, arm: Arm, n: int) -> bool:
    only = PRESETS[a.preset].get("only", {}).get(arm.name)
    return only is None or n in only


COMPILE_LINES = {  # vLLM 0.32 log lines that say which compiled code a launch runs
    "cache_dir": r"Using cache directory: (\S+)",
    "aot_loaded": r"Directly load AOT compilation from path (\S+)",
    "aot_saved": r"saved AOT compiled function to (\S+)",  # a fresh compile's artifact
    "graph_compile_s": r"Compiling a graph .* takes ([\d.]+) s",
    "torch_compile_s": r"torch\.compile took ([\d.]+) s",
    "sptc_line": r"(sptc scheduler \(.*)",
}


def launch_info(text: str) -> dict:
    """The compile state and the plugin's startup line from one launch's log text."""
    import re

    out = {}
    for k, pat in COMPILE_LINES.items():
        m = re.search(pat, text)
        out[k] = m.group(1) if m else None
    m = re.search(r"enforce_eager=(True|False)", text)
    out["enforce_eager"] = None if m is None else m.group(1) == "True"
    return out


def sweep(a) -> dict:
    arms, ladder, reps = select(a)
    pre = PRESETS[a.preset]
    rounds = max(1, a.rounds if a.rounds is not None else pre.get("rounds", 1))
    warm_pass = a.warm_pass or pre.get("warm_pass", False)
    out = Path(a.out)
    servers = list(dict.fromkeys(x.server for x in arms))
    if not a.launch:
        if a.server is None and len(servers) > 1:
            raise SystemExit("without --launch, say which server runs at --base-url (--server)")
        servers = [a.server or servers[0]]
    (out / "sweep").mkdir(parents=True, exist_ok=True)
    check_pressure(a, servers, out)
    (out / "sweep" / f"plan_{a.preset}.json").write_text(json.dumps(
        {"arms": [asdict(x) for x in arms], "agents": ladder, "reps": reps,
         "reps_at": pre.get("reps_at"), "only": pre.get("only"), "rounds": rounds,
         "warm_pass": warm_pass, "turns": a.turns,
         "servers": {s: SERVERS[s] for s in servers}, "workloads": WORKLOADS,
         "argv": sys.argv[1:]}, indent=1, default=str))
    stopped_all: dict[str, dict[str, str]] = {s: {} for s in servers}
    failed: list[str] = []
    for rnd in range(rounds):
        # ABBA: odd rounds launch the servers in reverse order, so no arm always runs
        # first (on a cold GPU) or last (on a warm one)
        for srv_name in (servers if rnd % 2 == 0 else servers[::-1]):
            sarms = [x for x in arms if x.server == srv_name]
            stopped = stopped_all[srv_name]
            same = bool(pre.get("same_prompts"))
            variant = salt_variants(sarms, same)

            todo = [(n, r, x) for n in ladder for r in range(reps_for(a, n, reps))
                    for x in sarms if r % rounds == rnd and runs_at(a, x, n)
                    and not _done(run_file(out, x.name, n, r))]
            if not todo:
                print(f"[sweep] {srv_name}: all runs already done"
                      + (f" (round {rnd})" if rounds > 1 else ""), flush=True)
                continue
            srv = ServerProc(a, srv_name) if a.launch else None
            if srv is None and not healthy(a.base_url):
                raise SystemExit(f"no server at {a.base_url}")

            def launch() -> str:  # a retry may have relaunched the server
                return f"{srv_name}#{srv.launches}" if srv is not None else f"{srv_name}@external"

            try:
                if srv is not None:
                    srv.start()
                warmup(a)
                # same prompts on one launch: kept apart by cache_salt if the server takes it,
                # else by a numbered prefix (recorded per run: salt, cache_salt)
                by_salt = same and any(variant.values()) and cache_salt_ok(a)
                if same and any(variant.values()) and not by_salt:
                    print(f"[sweep] WARNING {launch()} refused cache_salt: arms that share it "
                          "get numbered prompt prefixes instead", flush=True)
                if warm_pass:  # thrown away, kept for the record
                    w = run_point(a, sarms[0], 1, 0, warm=launch())
                    save_run(out / "sweep" / "warm" / (launch().replace("#", "__") + ".json"),
                             w)
                for n in ladder:
                    for r in range(reps_for(a, n, reps)):
                        if r % rounds != rnd:
                            continue
                        k = len(sarms)
                        for x in sarms[r % k:] + sarms[:r % k]:  # rotate arm order per repeat
                            path = run_file(out, x.name, n, r)
                            if x.name in stopped or not runs_at(a, x, n) or _done(path):
                                continue
                            rec = _run_with_retry(a, srv, x, n, r, variant[x.name], same,
                                                  by_salt)
                            rec.update(launch=launch(), round=rnd)
                            save_run(path, rec)
                            _print_run(rec)
                    runs = load_runs(out)
                    for x in sarms:
                        why = x.name not in stopped and saturated(runs, x.name, n, a.stop_factor)
                        if why:
                            stopped[x.name] = why
                            print(f"[sweep] {x.name}: stop after {n} agents ({why})", flush=True)
                    if len(stopped) == len(sarms):
                        break
            except ServerFailed as e:  # recorded in launches.jsonl; go on with the next server
                failed.append(f"{srv_name} (round {rnd})")
                print(f"[sweep] SERVER FAILED, skipping its runs in this round: {e}", flush=True)
            finally:
                if srv is not None:
                    srv.stop()
            (out / "sweep" / f"stopped_{srv_name}.json").write_text(json.dumps(stopped, indent=1))
    if failed:
        print(f"[sweep] servers that failed to start: {failed}; rerun to retry their runs",
              flush=True)
    return {**report(a), "failed_servers": failed}


def check_pressure(a, servers: list[str], out: Path) -> None:
    """Before a sweep with a pressure server: with --launch, --serve-cmd sets
    --max-model-len PRESSURE_MAX_LEN; and every run in one output directory uses one
    pressure config, which the first such sweep records in sweep/pressure.json."""
    if not any(s in PRESSURE_SERVERS for s in servers):
        return
    config = getattr(a, "pressure_config", "chosen")
    if a.launch:
        argv = shlex.split(a.serve_cmd)
        lens = [x.split("=", 1)[1] if "=" in x else (argv[i + 1:i + 2] or [None])[0]
                for i, x in enumerate(argv) if x.split("=", 1)[0] == "--max-model-len"]
        if not lens or lens[-1] != str(PRESSURE_MAX_LEN):
            raise SystemExit(f"the pressure servers need --max-model-len {PRESSURE_MAX_LEN} in "
                             f"--serve-cmd, e.g. {PRESSURE_SERVE_CMD!r}; got {a.serve_cmd!r}")
    f = out / "sweep" / "pressure.json"
    want = {"config": config, "flags": pressure_flags(config),
            "max_model_len": PRESSURE_MAX_LEN}
    if f.exists():
        have = json.loads(f.read_text()).get("config")
        if have != config:
            raise SystemExit(f"{out} has runs on the {have} pressure config, not {config}: "
                             "use another --out")
    else:
        f.write_text(json.dumps(want, indent=1))


def probe_verdict(out) -> dict:
    """The probe's rule (results/prereg_v4/predictions.md): the sweep runs on the fallback
    config if fcfs-p/spec+bad showed neither a preemption nor a request waiting in any
    1-second sample of the probe (preset probe, run into `out`); else on the chosen one.
    config None: no ok run of fcfs-p/spec+bad, or its /metrics were not read."""
    runs = {r["arm"]: r for r in load_runs(Path(out)) if r["status"] == "ok"}
    keys = ("preemptions", "max_waiting", "waiting_frac", "max_kv", "max_running")
    res: dict = {"arms": {}, "config": None, "pressure": None}
    for arm in PRESETS["probe"]["arms"]:
        m = (runs[arm].get("server_metrics") or {}) if arm in runs else None
        res["arms"][arm] = None if m is None else {k: m.get(k) for k in keys}
    bad = res["arms"][PRESSURE_REF]
    if bad is None or bad["preemptions"] is None or bad["max_waiting"] is None:
        res["why"] = f"no ok run of {PRESSURE_REF} with its /metrics read: rerun the probe"
        return res
    res["pressure"] = bad["preemptions"] > 0 or bad["max_waiting"] > 0
    res["config"] = "chosen" if res["pressure"] else "fallback"
    return res


def salt_variants(sarms: list[Arm], same_prompts: bool = False) -> dict[str, int]:
    """Arms of one server with the same client workload would send the same prompts (the
    prefix is not per arm, see run_point): all but the first get a variant number (a
    numbered prefix, or a cache_salt), so no run hits another's prefix cache on the same
    launch. same_prompts: the number of bad guesses is not part of the workload."""
    seen: Counter = Counter()
    out = {}
    for x in sarms:
        key = (x.mode, x.workload) if same_prompts else (x.mode, x.decoys, x.workload)
        out[x.name] = seen[key]
        seen[key] += 1
    return out


def _done(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return json.loads(path.read_text()).get("status") in ("ok", "timeout")
    except (OSError, json.JSONDecodeError):
        return False


def _run_with_retry(a, srv, arm: Arm, n: int, rep: int, variant: int = 0,
                    same_prompts: bool = False, by_salt: bool = False) -> dict:
    kw = {"variant": variant, "same_prompts": same_prompts, "by_salt": by_salt}
    rec = run_point(a, arm, n, rep, **kw)
    if rec["status"] in ("error", "invalid"):
        print(f"[sweep] {arm.name} n={n} r={rep}: {rec['status']}, retrying once: "
              f"{rec['errors'][:2]}", flush=True)
        if srv is not None and not srv.alive():
            srv.stop()
            srv.start()  # ServerFailed: sweep() records it and moves on
            warmup(a)
        rec2 = run_point(a, arm, n, rep, attempt=1, **kw)
        rec2["retry_of"] = {"status": rec["status"], "errors": rec["errors"]}
        rec = rec2
    return rec


def _print_run(rec: dict) -> None:
    w = [s["wall_s"] for s in rec["sessions"]]
    dec = Counter(d["outcome"] for s in rec["sessions"] for d in s["decoys"])
    print(json.dumps({"arm": rec["arm"], "agents": rec["agents"], "rep": rec["rep"],
                      "status": rec["status"], "session_p50": pctl(w, 0.5),
                      "makespan_s": round(rec["makespan_s"], 1), "decoys": dict(dec),
                      "client_cpu": round(rec["client_cpu_util"], 2),
                      "host_cpu": _fmt(rec.get("host_cpu_util")),
                      **rec["server_metrics"]}), flush=True)


def load(a) -> dict:
    """The original load test (one run per row, external server), now on run_point."""
    rows = []
    for n_agents in [int(x) for x in a.agents.split(",")]:
        for decoys in [int(x) for x in a.decoys.split(",")]:
            for mode in ("baseline", "spec"):
                if mode == "baseline" and decoys:
                    continue
                arm = Arm(f"load/{mode}/{decoys}", "external", mode, decoys,
                          "sptc" if a.tag_bets else "none",
                          workload="_cli")
                WORKLOADS["_cli"] = {"patterns": a.patterns, "turns": a.turns}
                rec = run_point(a, arm, n_agents, 0)
                results = rec["sessions"]
                walls = sorted(r["wall_s"] for r in results) or [math.nan]
                tp = sorted(r["root_tpot_ms"] for r in results if r["root_tpot_ms"])
                fins = Counter(f for r in results for f in r["sub_finish"])
                roots = Counter(r["root_finish"] for r in results)
                dec = Counter(d["outcome"] for r in results for d in r["decoys"])
                row = {"root_finish": dict(roots), "sub_finish": dict(fins.most_common(3)),
                       "sub_refused": sum(r["sub_refused"] for r in results),
                       "decoy_outcomes": dict(dec), "status": rec["status"],
                       "errors": rec["errors"][:3],
                       "agents": n_agents, "decoys": decoys, "mode": mode, "tagged": a.tag_bets,
                       "turns": len(results), "wall_p50": walls[len(walls) // 2],
                       "wall_p99": walls[min(len(walls) - 1, int(0.99 * len(walls)))],
                       "root_tpot_p50_ms": tp[len(tp) // 2] if tp else None,
                       "root_tpot_p99_ms": tp[min(len(tp) - 1, int(0.99 * len(tp)))] if tp else None}
                rows.append(row)
                print(json.dumps(row), flush=True)
    return {"load": rows}


# ----------------------------------------------------------------------------- analysis
def pctl(xs, q: float):
    """Nearest-rank percentile (as the original load rows): sorted[int(q * n)]."""
    xs = sorted(x for x in xs if x is not None and x == x)
    if not xs:
        return None
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def boot_ci(groups: list[list], stat, b: int = 1000, seed: int = 0, level: float = 0.95):
    """Two-level bootstrap: resample repeats, then sessions inside each resampled repeat.
    With one repeat it is a plain session bootstrap (the run-to-run spread is then unknown)."""
    groups = [g for g in groups if g]
    if not groups:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(b):
        pool = []
        for _ in groups:
            g = groups[rng.randrange(len(groups))]
            pool += [g[rng.randrange(len(g))] for _ in g]
        v = stat(pool)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    lo = vals[int((1 - level) / 2 * (len(vals) - 1))]
    hi = vals[int((1 + level) / 2 * (len(vals) - 1))]
    return [lo, hi]


def slo_refs(runs: list[dict], ref_arm: str = SLO_REF) -> dict:
    """Per pattern: median session wall and root TPOT of the reference arm at its lowest
    load (1 agent in every preset). The SLO is a multiple of these."""
    ok = [r for r in runs if r["arm"] == ref_arm and r["status"] == "ok"]
    if not ok:
        return {}
    lo = min(r["agents"] for r in ok)
    by: dict = {}
    for r in ok:
        if r["agents"] == lo:
            for s in r["sessions"]:
                by.setdefault(s["pattern"], []).append(s)
    return {p: {"wall_s": med([s["wall_s"] for s in ss]),
                "root_tpot_ms": med([s["root_tpot_ms"] for s in ss if s["root_tpot_ms"]])}
            for p, ss in by.items()}


def meets_parts(s: dict, refs: dict, k_session: float, k_tpot: float):
    """(wall ok, root TPOT ok) for one session, or None without a reference. Root TPOT is
    the session's mean (span / (tokens - 1)), not a token-level tail."""
    ref = refs.get(s["pattern"])
    if ref is None:
        return None
    t = s.get("root_tpot_ms")
    return (s["wall_s"] <= k_session * ref["wall_s"],
            t is not None and t <= k_tpot * ref["root_tpot_ms"])


def meets(s: dict, refs: dict, k_session: float, k_tpot: float) -> bool | None:
    m = meets_parts(s, refs, k_session, k_tpot)
    return None if m is None else m[0] and m[1]


def goodput(sessions: list[dict], refs: dict, k_session: float, k_tpot: float, part=None):
    """Fraction of sessions meeting the SLO; part 0 or 1: the wall or the TPOT half alone.
    The references are no-speculation sessions, so for speculative arms (about 2.4x
    shorter) the wall half rarely binds and goodput is mostly the TPOT half."""
    ok = [meets_parts(s, refs, k_session, k_tpot) for s in sessions]
    ok = [(x[0] and x[1]) if part is None else x[part] for x in ok if x is not None]
    return sum(ok) / len(ok) if ok else None


CURVE = [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0]
P99_MIN_N = 100  # below this many sessions the nearest-rank p99 is the sample maximum
HOST_CPU_MAX = 0.85  # validity: whole-host CPU averaged over a run
HOST_SAT_MAX = 0.10  # validity: share of 1-s intervals with the host >= HostCpu.SAT busy


def summarize(runs: list[dict], k_session: float = 2.0, k_tpot: float = 2.0,
              ref_arm: str = SLO_REF, boot: int = 1000) -> dict:
    """Per (arm, agents) over the repeats with status ok. Used for the measured runs
    (report) and, unchanged, for the simulator's predicted runs (experiments).

    p99s are nearest rank across sessions; with fewer than P99_MIN_N sessions they are the
    maximum (p99_is_max). They get no bootstrap CI: resampling a maximum, or a quantile
    with a handful of points above it, gives brackets far narrower than the truth."""
    refs = slo_refs(runs, ref_arm)
    cells: dict = {}
    for r in runs:
        cells.setdefault((r["arm"], r["agents"]), []).append(r)
    rows = []
    for (arm, n), rs in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        ok = [r for r in rs if r["status"] == "ok"]
        groups = [r["sessions"] for r in ok]
        ses = [s for g in groups for s in g]
        wall = lambda ss, q: pctl([s["wall_s"] for s in ss], q)  # noqa: E731
        tpot = lambda ss, q: pctl([s["root_tpot_ms"] for s in ss], q)  # noqa: E731
        good = lambda ss: goodput(ss, refs, k_session, k_tpot)  # noqa: E731
        dec = Counter(d["outcome"] for s in ses for d in s.get("decoys", []))
        calls = Counter(c["outcome"] for s in ses for c in s.get("calls", [])
                        if c.get("kind") in ("early", "call"))
        thr = [len(r["sessions"]) / r["makespan_s"] * 60 for r in ok if r.get("makespan_s")]
        sm = [r.get("server_metrics") or {} for r in ok]
        row = {"arm": arm, "server": rs[0]["server"], "agents": n, "reps_ok": len(ok),
               "reps_other": Counter(r["status"] for r in rs if r["status"] != "ok"),
               "sessions": len(ses),
               "session_p50": wall(ses, 0.5), "session_p99": wall(ses, 0.99),
               "root_tpot_p50": tpot(ses, 0.5), "root_tpot_p99": tpot(ses, 0.99),
               "root_itl_p99": pctl([s.get("root_itl_p99_ms") for s in ses], 0.5),
               "sessions_per_min": statistics.mean(thr) if thr else None,
               "p99_is_max": len(ses) < P99_MIN_N,
               "goodput": good(ses),
               "goodput_wall": goodput(ses, refs, k_session, k_tpot, part=0),
               "goodput_tpot": goodput(ses, refs, k_session, k_tpot, part=1),
               "goodput_curve": {str(m): goodput(ses, refs, m, m) for m in CURVE},
               "decoy_outcomes": dict(dec), "spec_call_outcomes": dict(calls),
               "refused_calls": sum(s.get("sub_refused", 0) for s in ses),
               # spec_kind bet: the speculative calls sent as bets, the distinct calls they
               # were for (the simulator sends one bet per call), the refused ones re-run at
               # their claim, sessions whose shadow stopped at a refused bet it forced
               "real_bet_outcomes": dict(Counter(b["outcome"] for s in ses
                                                 for b in s.get("real_bets", []))),
               "real_bet_calls": sum(s.get("real_bet_calls", len(s.get("real_bets", [])))
                                     for s in ses),
               "reissued": sum(s.get("reissued", 0) for s in ses),
               "shadow_stops": sum(bool(s.get("shadow_stopped")) for s in ses),
               "preemptions": _sum([m.get("preemptions") for m in sm]),
               "max_waiting": _max([m.get("max_waiting") for m in sm]),
               "waiting_frac": (statistics.mean(v) if (v := [m["waiting_frac"] for m in sm
                                if m.get("waiting_frac") is not None]) else None),
               "max_kv": _max([m.get("max_kv") for m in sm]),
               "client_cpu_util": _max([r.get("client_cpu_util") for r in ok]),
               "host_cpu_util": _max([r.get("host_cpu_util") for r in ok]),
               "host_cpu_sat_frac": _max([r.get("host_cpu_sat_frac") for r in ok]),
               "sub_tokens_per_session": (statistics.mean(sub_tokens(s) for s in ses)
                                          if ses else None),
               "proxy_peak_in_flight": _max([(r.get("proxy") or {}).get("peak_in_flight")
                                             for r in ok]),
               "prefix_hit_frac": _ratio(_sum([m.get("prefix_hits") for m in sm]),
                                         _sum([m.get("prefix_queries") for m in sm])),
               **gpu_of(ok)}
        # validity (scoring rule 5): None where the host was not measured (simulator, macOS)
        if ok and all(r.get("host_cpu_util") is not None for r in ok):
            row["cpu_ok"] = all(r["host_cpu_util"] < HOST_CPU_MAX
                                and (r.get("host_cpu_sat_frac") or 0.0) < HOST_SAT_MAX
                                for r in ok)
        else:
            row["cpu_ok"] = None
        if boot and ses:
            row["ci"] = {"session_p50": boot_ci(groups, lambda p: wall(p, 0.5), boot),
                         "root_tpot_p50": boot_ci(groups, lambda p: tpot(p, 0.5), boot),
                         "goodput": boot_ci(groups, good, boot) if refs else None}
        rows.append(row)
    return {"slo": {"ref_arm": ref_arm, "k_session": k_session, "k_tpot": k_tpot,
                    "refs": refs},
            "rows": rows, "derived": derived(rows), "by_launch": by_launch(runs)}


def by_launch(runs: list[dict]) -> list[dict]:
    """Per (arm, agents, server launch): the launch-to-launch spread of one arm (stock vs
    stock across launches is the noise floor of the A/B). Runs without a launch are skipped."""
    cells: dict = {}
    for r in runs:
        if r["status"] == "ok" and r.get("launch"):
            cells.setdefault((r["arm"], r["agents"], r["launch"]), []).append(r)
    out = []
    for (a, n, la), rs in sorted(cells.items()):
        ss = [s for r in rs for s in r["sessions"]]
        out.append({"arm": a, "agents": n, "launch": la, "round": rs[0].get("round"),
                    "sessions": len(ss), "session_p50": pctl([s["wall_s"] for s in ss], 0.5),
                    "root_tpot_p50": pctl([s["root_tpot_ms"] for s in ss], 0.5),
                    "started_utc": min(r.get("started_utc", "") for r in rs), **gpu_of(rs)})
    return out


def _sum(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) if xs else None


def sub_tokens(s: dict) -> int:
    """Completion tokens of one session's sub-calls (decoys apart): the workload's size.
    Sub-calls are natural-length, so arms meant to run the same workload can still differ
    here; compare it next to any ratio."""
    n = 0
    for c in s.get("calls", []):
        u = (c.get("usage") or {}).get("completion")  # stream()'s usage
        n += u if u is not None else (c.get("tokens") or 0)
    return n


def gpu_of(runs: list[dict]) -> dict:
    """GPU clocks and temperature over runs (gpu_state samples; None without nvidia-smi)."""
    g = [r["gpu"] for r in runs if r.get("gpu")]
    return {"gpu_sm_mhz_min": _min([x.get("sm_mhz_min") for x in g]),
            "gpu_sm_mhz_mean": statistics.mean(v) if (v := [x["sm_mhz_mean"] for x in g
                                                           if x.get("sm_mhz_mean")]) else None,
            "gpu_temp_c_max": _max([x.get("temp_c_max") for x in g]),
            "gpu_reasons": sorted({y for x in g for y in x.get("reasons", [])})}


def _min(xs):
    xs = [x for x in xs if x is not None]
    return min(xs) if xs else None


def _max(xs):
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def stock_of(arm: str) -> str:
    """The stock FCFS arm with the same client mode and launch kind: fcfs/spec for
    plugin/spec, fcfs-eager/spec for plugin-off-eager/spec."""
    label, mode = arm.split("/", 1)
    return ("fcfs-eager/" if label.endswith("-eager") else "fcfs/") + mode


def _ratio(x, y):
    return float(x / y) if x is not None and y else None


def derived(rows: list[dict]) -> dict:
    """The pre-registered questions, computed the same way for predicted and measured:
    knee     smallest load whose session p50 is >= 2x the arm's own lowest-load p50
    growth   per load, session p50 / the arm's own lowest-load p50 (how close each knee is)
    knee_ref smallest load whose session p50 is >= 2x the lowest-load p50 of stock FCFS
             with the same client mode (fcfs/spec for plugin/spec, ...; fcfs-eager/ for
             eager arms): one absolute threshold per mode, so a slower light-load point does
             not move the knee
    good50   smallest load whose goodput is < 0.5 (good50_wall, good50_tpot: each half of
             the SLO alone)
    thr_peak load with the most sessions per minute (the ladder's top: not saturated yet)
    net_loss smallest load where spec+bad is no faster (session p50) than nospec on the
             same server: speculation with bad guesses has become a net loss
    prio_vs_fcfs / plugin_vs_fcfs  per load, session p50 and root TPOT p99 of spec+bad
             relative to stock FCFS spec+bad (< 1: better)
    vs_stock per arm and load: session p50, root TPOT p50 and p99 relative to stock_of(arm)
             (the regression A/B: > 1 means slower than stock)
    baselines_vs_fcfs  per B4 arm and load: session p50, root TPOT p50 / p99 and sub-call
             tokens per session relative to BASELINE_REF (stock FCFS with bad guesses,
             launched with the proxy arms)
    baselines_vs_nobets  the same relative to BASELINE_NOBETS (stock FCFS without bad
             guesses: what refusing every bet achieves, as every B4 bet is a decoy)
    pressure_vs_ref  per PRESSURE_GROUPS arm and load: session p50 / p99 and root TPOT p50 /
             p99 relative to its group's reference (fcfs-p/spec+bad, fcfs-d/spec+bad)
    d1       the decision rule on these values (pressure_d1)."""
    by: dict = {}
    for r in rows:
        if r["reps_ok"]:
            by.setdefault(r["arm"], {})[r["agents"]] = r
    out: dict = {"knee": {}, "growth": {}, "knee_ref": {}, "good50": {}, "good50_wall": {},
                 "good50_tpot": {}, "thr_peak": {}, "net_loss": {}, "prio_vs_fcfs": {},
                 "plugin_vs_fcfs": {}, "vs_stock": {}, "baselines_vs_fcfs": {},
                 "baselines_vs_nobets": {}, "pressure_vs_ref": {}}
    for arm, pts in by.items():
        loads = sorted(pts)
        base = pts[loads[0]]["session_p50"]
        out["knee"][arm] = next((n for n in loads
                                 if base and pts[n]["session_p50"] >= 2 * base), None)
        out["growth"][arm] = {n: pts[n]["session_p50"] / base for n in loads} if base else {}
        ref = by.get(stock_of(arm))
        rbase = ref[min(ref)]["session_p50"] if ref else None
        out["knee_ref"][arm] = next((n for n in loads
                                     if rbase and pts[n]["session_p50"] >= 2 * rbase), None)
        for key, g in (("good50", "goodput"), ("good50_wall", "goodput_wall"),
                       ("good50_tpot", "goodput_tpot")):
            out[key][arm] = next((n for n in loads if pts[n].get(g) is not None
                                  and pts[n][g] < 0.5), None)
        thr = [n for n in loads if pts[n].get("sessions_per_min") is not None]
        out["thr_peak"][arm] = max(thr, key=lambda n: pts[n]["sessions_per_min"]) if thr else None
    for srv in ("fcfs", "prio", "plugin"):
        bad, nos = by.get(f"{srv}/spec+bad", {}), by.get(f"{srv}/nospec", {})
        both = sorted(set(bad) & set(nos))
        out["net_loss"][srv] = next((n for n in both
                                     if bad[n]["session_p50"] >= nos[n]["session_p50"]), None)
    for arm, pts in by.items():  # the A/B: every non-stock arm against stock, same mode
        ref = by.get(stock_of(arm))
        if ref is None or stock_of(arm) == arm:
            continue
        out["vs_stock"][arm] = {n: {k: _ratio(pts[n].get(k), ref[n].get(k))
                                    for k in ("session_p50", "root_tpot_p50", "root_tpot_p99",
                                              "sub_tokens_per_session")}
                                for n in sorted(set(pts) & set(ref))}
    for key, ref_arm in (("baselines_vs_fcfs", BASELINE_REF),
                         ("baselines_vs_nobets", BASELINE_NOBETS)):
        ref = by.get(ref_arm, {})
        for arm in B4_ARMS:
            pts = by.get(arm, {})
            if arm == ref_arm or not pts:
                continue
            out[key][arm] = {
                n: {k: _ratio(pts[n].get(k), ref[n].get(k))
                    for k in ("session_p50", "root_tpot_p50", "root_tpot_p99",
                              "sub_tokens_per_session")}
                for n in sorted(set(pts) & set(ref))}
    fc = by.get("fcfs/spec+bad", {})
    for key, arm in (("prio_vs_fcfs", "prio/spec+bad"), ("plugin_vs_fcfs", "plugin/spec+bad")):
        other = by.get(arm, {})
        for n in sorted(set(fc) & set(other)):
            f, o = fc[n], other[n]
            out[key][n] = {
                "session_p50": (float(o["session_p50"] / f["session_p50"])
                                if f["session_p50"] else None),
                "root_tpot_p99": (float(o["root_tpot_p99"] / f["root_tpot_p99"])
                                  if f["root_tpot_p99"] and o["root_tpot_p99"] else None)}
    for ref_arm, arms in PRESSURE_GROUPS.items():
        ref = by.get(ref_arm, {})
        for arm in arms:
            pts = by.get(arm, {})
            if pts and ref:
                out["pressure_vs_ref"][arm] = {
                    n: {k: _ratio(pts[n].get(k), ref[n].get(k))
                        for k in ("session_p50", "session_p99", "root_tpot_p50",
                                  "root_tpot_p99")}
                    for n in sorted(set(pts) & set(ref))}
    out["d1"] = pressure_d1(by)
    return out


def pressure_d1(by: dict) -> dict:
    """The decision rule on measured (or predicted) rows, {arm: {agents: row}}. Per
    D1_ARMS workload at D1_AGENTS: plugin vs cap and plugin vs priority, session p50. The
    plugin wins if plugin vs cap <= 1 - D1_MARGIN in a D1_RULE workload and the pressure
    check passed: fcfs-p/spec+bad preempts or queues clearly (per run: PRESSURE_CLEAR's
    preemptions, or a request waiting in that share of 1-second samples) and fcfs-p/spec
    barely does (PRESSURE_QUIET). None where a row is missing or not measured."""
    n = D1_AGENTS
    row = lambda arm: by.get(arm, {}).get(n)  # noqa: E731
    p50 = lambda arm: (row(arm) or {}).get("session_p50")  # noqa: E731
    wl = {k: {"plugin_vs_cap": _ratio(p50(pl), p50(cp)),
              "plugin_vs_prio": _ratio(p50(pl), p50(pr))}
          for k, (pl, cp, pr) in D1_ARMS.items()}

    def per_run(arm):
        r = row(arm)
        if r is None or r.get("preemptions") is None or r.get("waiting_frac") is None:
            return None
        return {"preemptions": r["preemptions"] / r["reps_ok"],
                "queue_frac": r["waiting_frac"]}

    bad, spec = per_run(PRESSURE_REF), per_run("fcfs-p/spec")
    check = None if bad is None or spec is None else (
        any(bad[k] >= PRESSURE_CLEAR[k] for k in PRESSURE_CLEAR)
        and all(spec[k] <= PRESSURE_QUIET[k] for k in PRESSURE_QUIET))
    ratios = [wl[k]["plugin_vs_cap"] for k in D1_RULE]
    won = [k for k in D1_RULE if ratios[D1_RULE.index(k)] is not None
           and ratios[D1_RULE.index(k)] <= 1 - D1_MARGIN]
    wins = (False if check is False else None if check is None else True if won
            else None if None in ratios else False)
    return {"agents": n, "by_workload": wl, "pressure": {PRESSURE_REF: bad, "fcfs-p/spec": spec},
            "pressure_check": check, "won_in": won, "plugin_wins": wins}


def _fmt(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


def _ci(row, k, nd=2):
    ci = (row.get("ci") or {}).get(k)
    return f" [{_fmt(ci[0], nd)}, {_fmt(ci[1], nd)}]" if ci else ""


def _shares(outcomes: dict | None) -> str:
    """'rejected / dropped' shares of a bet-outcome count; '-' with no bets."""
    n = sum((outcomes or {}).values())
    if not n:
        return "-"
    return f"{outcomes.get('rejected', 0) / n:.2f} / {outcomes.get('dropped', 0) / n:.2f}"


def pressure_md(s: dict) -> list[str]:
    """summary_md's Pressure section; [] without its arms."""
    d, f = s["derived"], _fmt
    vr = d.get("pressure_vs_ref") or {}
    if not vr:
        return []
    rowd = {(r["arm"], r["agents"]): r for r in s["rows"] if r["reps_ok"]}
    L = ["", "## Pressure: each arm against its reference, same load", "",
         f"References: `{PRESSURE_REF}` on the pressure servers (one T4 KV config, "
         f"sweep/pressure.json), `{BOTH_DEFAULT_REF}` on the default servers. Ratios < 1 are "
         f"faster; under {P99_MIN_N} sessions a p99 is the slowest session. Decoys and real "
         "bets (speculative calls sent as bets, workload `both`): share logged rejected "
         "(refused, or dropped before its first token: the client cannot tell them apart) / "
         "dropped (after one). Bets per call: real bets over the distinct calls they were "
         "for; spec-ptc bets again on a call whose bet failed (a re-peek, then its "
         "statement), the simulator does not (1.0). Re-runs: calls run for real at their "
         "claim after their bets were refused. Shadow stops: sessions whose spec-ptc shadow "
         "stopped at a refused bet it forced. Preempt: vLLM's counter, per run (a bet the "
         "plugin drops is not in it). Max wait: most requests waiting in a 1-s sample. "
         "Queue: share of 1-s samples with one waiting, mean over runs. KV peak: vLLM's KV "
         "usage, highest sample.", "",
         "| arm | agents | session p50 | p99 | root TPOT p50 | p99 | decoys rejected / "
         "dropped | real bets rejected / dropped | bets per call | re-runs | shadow stops | "
         "preempt | max wait | queue | KV peak |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arms in PRESSURE_GROUPS.values():
        for arm in arms:
            for n, v in (vr.get(arm) or {}).items():
                r = rowd[(arm, n)]
                pre = None if r.get("preemptions") is None else r["preemptions"] / r["reps_ok"]
                q = r.get("waiting_frac")
                per = _ratio(sum((r.get("real_bet_outcomes") or {}).values()),
                             r.get("real_bet_calls"))
                L.append(f"| {arm} | {n} | " + " | ".join(
                    f(v[k], 3) for k in ("session_p50", "session_p99", "root_tpot_p50",
                                         "root_tpot_p99"))
                    + f" | {_shares(r.get('decoy_outcomes'))} | "
                    f"{_shares(r.get('real_bet_outcomes'))} | {f(per)} | "
                    f"{r.get('reissued', 0)} | "
                    f"{r.get('shadow_stops', 0)}/{r['sessions']} | {f(pre, 1)} | "
                    f"{f(r.get('max_waiting'), 0)} | {'-' if q is None else f'{q:.0%}'} | "
                    f"{f(r.get('max_kv'))} |")
    x = d["d1"]
    L += ["", f"Decision rule on these values: the plugin wins if its session p50 "
          f"is at most {1 - D1_MARGIN:.2f}x the cap's at {x['agents']} agents in "
          + " or ".join(f"`{k}`" for k in D1_RULE) + " on the pressure servers, with the "
          "pressure check passed.", ""]
    for wl, v in x["by_workload"].items():
        pl, cp, pr = D1_ARMS[wl]
        L.append(f"- {wl}: {pl} / {cp} {f(v['plugin_vs_cap'], 3)}, / {pr} "
                 f"{f(v['plugin_vs_prio'], 3)}"
                 + ("" if wl in D1_RULE else " (no pressure: reported, not part of the rule)"))
    pb, ps = x["pressure"][PRESSURE_REF], x["pressure"]["fcfs-p/spec"]
    show = lambda p: ("-" if p is None else  # noqa: E731
                      f"{p['preemptions']:.1f} preemptions, queue {p['queue_frac']:.0%}")
    verdict = {True: "yes", False: "no", None: "unknown (rows missing)"}
    L += [f"- pressure check (per run; queue: share of 1-s samples, the simulator's is a "
          f"share of time): {PRESSURE_REF} {show(pb)} (clearly: >= "
          f"{PRESSURE_CLEAR['preemptions']} preemptions or a queue >= "
          f"{PRESSURE_CLEAR['queue_frac']:.0%}); fcfs-p/spec {show(ps)} (barely: <= "
          f"{PRESSURE_QUIET['preemptions']} and <= {PRESSURE_QUIET['queue_frac']:.0%}). "
          f"Passed: {verdict[x['pressure_check']]}",
          f"- **plugin wins: {verdict[x['plugin_wins']]}**"
          + (f" (in {', '.join(x['won_in'])})" if x["plugin_wins"] else "")]
    return L


def summary_md(s: dict, title: str = "Sweep summary") -> str:
    slo = s["slo"]
    lines = [f"# {title}", "",
             f"SLO per session: wall <= {slo['k_session']}x and root TPOT <= {slo['k_tpot']}x "
             f"the `{slo['ref_arm']}` arm at 1 agent, same pattern. Goodput = fraction of "
             "sessions meeting it; wall / TPOT = each half alone. Root TPOT is each session's "
             "mean; p50 and p99 are across sessions. Brackets: 95% bootstrap CI (repeats, "
             f"then sessions); none for p99s. 'max': under {P99_MIN_N} sessions, so the p99 "
             "is the slowest session. host CPU: whole host, mean over the run (max over "
             f"repeats); cpu ok: every run below {HOST_CPU_MAX} with under "
             f"{HOST_SAT_MAX:.0%} of seconds saturated.", "",
             "| arm | agents | reps | session p50 s | session p99 s | root TPOT p50 ms | "
             "root TPOT p99 ms | sessions/min | goodput | wall / TPOT | decoys | preempt | "
             "max wait | client CPU | host CPU | cpu ok |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in s["rows"]:
        dec = ",".join(f"{k}:{v}" for k, v in sorted(r["decoy_outcomes"].items())) or "-"
        mx = " (max)" if r.get("p99_is_max") else ""
        ok = r.get("cpu_ok")
        lines.append(
            f"| {r['arm']} | {r['agents']} | {r['reps_ok']} | {_fmt(r['session_p50'])}"
            f"{_ci(r, 'session_p50')} | {_fmt(r['session_p99'])}{mx} | "
            f"{_fmt(r['root_tpot_p50'], 1)}{_ci(r, 'root_tpot_p50', 1)} | "
            f"{_fmt(r['root_tpot_p99'], 1)}{mx} | "
            f"{_fmt(r['sessions_per_min'], 1)} | {_fmt(r['goodput'])}{_ci(r, 'goodput')} | "
            f"{_fmt(r.get('goodput_wall'))} / {_fmt(r.get('goodput_tpot'))} | "
            f"{dec} | {_fmt(r['preemptions'], 0)} | {_fmt(r['max_waiting'], 0)} | "
            f"{_fmt(r['client_cpu_util'])} | {_fmt(r.get('host_cpu_util'))} | "
            f"{'-' if ok is None else 'yes' if ok else 'NO'} |")
    d = s["derived"]
    lines += ["", "## Derived", "",
              f"- knee (session p50 >= 2x own 1-agent): {d['knee']}",
              f"- knee against stock FCFS's 1-agent p50, same mode: {d.get('knee_ref')}",
              f"- goodput < 0.5 first at: {d['good50']}",
              f"- wall half alone < 0.5 first at: {d.get('good50_wall')}",
              f"- root TPOT half alone < 0.5 first at: {d.get('good50_tpot')}",
              f"- most sessions per minute at: {d['thr_peak']}",
              f"- spec+bad no faster than nospec first at: {d['net_loss']}",
              f"- prio/spec+bad vs fcfs/spec+bad (ratio, < 1 better): {d['prio_vs_fcfs']}",
              f"- plugin/spec+bad vs fcfs/spec+bad: {d['plugin_vs_fcfs']}"]
    lines += pressure_md(s)
    lines += ["", f"## Baselines (B4) against `{BASELINE_REF}` (session p50 / root TPOT p50 / "
              "p99; < 1 better)", "",
              "Sub-call tokens: sub-call completion tokens per session, same ratio; away "
              "from 1, the arms did not run the same amount of work (sub-calls stop at "
              f"EOS). vs no bets: session p50 against `{BASELINE_NOBETS}`, stock FCFS "
              "without bad guesses. Every B4 bet is a worthless decoy, so refusing every "
              "bet is the best a gate can do here: an arm near 1.0 in that column has "
              "refused (nearly) all bets, and B4 cannot show a cost of refusing too many. "
              "Decoys refused: share of decoys logged rejected. Prefix hits: the server's "
              "prefix-cache hit share over the arm's runs ('-': no counter).", "",
              "| arm | agents | session p50 | root TPOT p50 | root TPOT p99 | sub-call tokens "
              "| vs no bets | decoys refused | prefix hits |",
              "|---|---|---|---|---|---|---|---|---|"]
    rowd = {(r["arm"], r["agents"]): r for r in s["rows"] if r["reps_ok"]}
    vf, vn = d.get("baselines_vs_fcfs", {}), d.get("baselines_vs_nobets", {})
    for arm in B4_ARMS:  # the reference rows too, for their decoys and prefix hits
        for n in sorted(n for (x, n) in rowd if x == arm):
            one = {k: 1.0 for k in ("session_p50", "root_tpot_p50", "root_tpot_p99",
                                    "sub_tokens_per_session")}
            v = one if arm == BASELINE_REF else (vf.get(arm) or {}).get(n, {})
            nb = 1.0 if arm == BASELINE_NOBETS else (vn.get(arm) or {}).get(n, {}).get(
                "session_p50")
            dec = rowd[(arm, n)].get("decoy_outcomes") or {}
            rej = dec.get("rejected", 0) / sum(dec.values()) if sum(dec.values()) else None
            lines.append(f"| {arm} | {n} | {_fmt(v.get('session_p50'), 3)} | "
                         f"{_fmt(v.get('root_tpot_p50'), 3)} | "
                         f"{_fmt(v.get('root_tpot_p99'), 3)} | "
                         f"{_fmt(v.get('sub_tokens_per_session'), 3)} | {_fmt(nb, 3)} | "
                         f"{_fmt(rej)} | {_fmt(rowd[(arm, n)].get('prefix_hit_frac'))} |")
    lines += ["",
              "## Against stock FCFS, same mode (session p50 / root TPOT p50 / p99; > 1 slower)",
              "", "Last column: sub-call completion tokens per session, same ratio. Both "
              "arms send the same prompts, but sub-calls stop at EOS: a ratio away from 1 "
              "means the arms did not run the same amount of work.", "",
              "| arm | agents | session p50 | root TPOT p50 | root TPOT p99 | sub-call tokens |",
              "|---|---|---|---|---|---|"]
    for arm, pts in d.get("vs_stock", {}).items():
        for n, v in pts.items():
            lines.append(f"| {arm} | {n} | {_fmt(v['session_p50'], 3)} | "
                         f"{_fmt(v['root_tpot_p50'], 3)} | {_fmt(v['root_tpot_p99'], 3)} | "
                         f"{_fmt(v.get('sub_tokens_per_session'), 3)} |")
    lines += ["",
              "## Goodput curve (both thresholds = multiplier)", "",
              "| arm | agents | " + " | ".join(f"{m}x" for m in CURVE) + " |",
              "|---|---|" + "---|" * len(CURVE)]
    for r in s["rows"]:
        lines.append(f"| {r['arm']} | {r['agents']} | " + " | ".join(
            _fmt(r["goodput_curve"][str(m)]) for m in CURVE) + " |")
    if s.get("by_launch"):
        lines += ["", "## Per server launch (GPU: lowest SM clock MHz and peak temperature C "
                  "over the launch's runs; '-' without nvidia-smi)", "",
                  "| arm | agents | launch | first run (UTC) | sessions | session p50 s | "
                  "root TPOT p50 ms | GPU SM min | GPU temp max |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in s["by_launch"]:
            lines.append(f"| {r['arm']} | {r['agents']} | {r['launch']} | "
                         f"{r.get('started_utc') or '-'} | {r['sessions']} | "
                         f"{_fmt(r['session_p50'])} | {_fmt(r['root_tpot_p50'], 1)} | "
                         f"{_fmt(r.get('gpu_sm_mhz_min'), 0)} | "
                         f"{_fmt(r.get('gpu_temp_c_max'), 0)} |")
    return "\n".join(lines) + "\n"


def report(a) -> dict:
    out = Path(a.out)
    runs = load_runs(out)
    s = summarize(runs, a.slo_session, a.slo_tpot, a.slo_ref, a.boot)
    (out / "sweep" / "summary.json").write_text(json.dumps(s, indent=1, default=str))
    (out / "sweep" / "summary.md").write_text(summary_md(s))
    print(summary_md(s)[:4000])
    return {"summary": str(out / "sweep" / "summary.md"), "runs": len(runs)}


# ----------------------------------------------------------------------------- plan
RUN_OVERHEAD_S = 20.0  # spawn N agent processes, import spec-ptc, settle (estimate)
SERVER_START_S = 240.0  # vllm serve on a T4: load, profile, CUDA graphs (~2-3 min seen)
EAGER_SLOWDOWN = 1.5  # --enforce-eager vs CUDA graphs at small batches (a guess, not measured)
TAIL = 1.3  # a run lasts `turns` sessions of its slowest agent, not of the median one


def plan(a) -> dict:
    """Runs of a preset and their estimated GPU minutes. Session times come from the
    simulator's predictions (--predictions) where present, else from a crude rule (the
    T4's 8-agent spec+bad session, 6.6 s, scaled linearly with load beyond 8). Eager
    arms are not predicted: their compiled twin's time x EAGER_SLOWDOWN."""
    arms, ladder, reps = select(a)
    pre = PRESETS[a.preset]
    rounds = max(1, a.rounds if getattr(a, "rounds", None) is not None else pre.get("rounds", 1))
    warm = getattr(a, "warm_pass", False) or pre.get("warm_pass", False)
    pred = {}
    if a.predictions and Path(a.predictions).exists():
        for r in json.loads(Path(a.predictions).read_text())["summary"]["rows"]:
            pred[(r["arm"], r["agents"])] = r["session_p50"]

    def session(x: Arm, n: int) -> float:
        if pred.get((x.name, n)):
            return pred[(x.name, n)]
        name, k = x.name.replace("-adj/", "/").replace("-b4/", "/"), 1.0
        if "-eager/" in name:
            name, k = name.replace("-eager/", "/"), EAGER_SLOWDOWN
        return k * (pred.get((name, n)) or 6.6 * max(1.0, n / 8))

    rows, total = [], 0.0
    for srv in dict.fromkeys(x.server for x in arms):
        sarms = [y for y in arms if y.server == srv]
        total += rounds * SERVER_START_S
        if warm:
            turns = a.turns or WORKLOADS[sarms[0].workload]["turns"]
            total += rounds * (turns * session(sarms[0], 1) * TAIL + RUN_OVERHEAD_S)
        for x in sarms:
            turns = a.turns or WORKLOADS[x.workload]["turns"]
            for n in ladder:
                if not runs_at(a, x, n):
                    continue
                k = reps_for(a, n, reps)
                t = k * (turns * session(x, n) * TAIL + RUN_OVERHEAD_S)
                total += t
                rows.append({"arm": x.name, "agents": n, "reps": k, "est_s": round(t)})
    # a fresh session compiles each compile group once, on a launch that is not measured
    fills = len({compile_group(SERVERS[s]["flags"]) for s in dict.fromkeys(x.server for x in arms)
                 if "--enforce-eager" not in SERVERS[s]["flags"]})
    total += fills * SERVER_START_S
    res = {"preset": a.preset, "runs": sum(r["reps"] for r in rows),
           "launches": rounds * len(dict.fromkeys(x.server for x in arms)),
           "cache_fill_launches_max": fills,
           "est_minutes": round(total / 60),
           "source": "simulator predictions" if pred else "rule of thumb", "rows": rows}
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}))
    return res


# ----------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["calib", "predict", "concur", "suite", "load", "sweep",
                                    "report", "plan"])
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--model", default="Qwen/Qwen3-1.7B")
    ap.add_argument("--out", default="kaggle_out")
    ap.add_argument("--gpu", default="T4")
    ap.add_argument("--spec-ptc", default="spec-ptc")
    ap.add_argument("--patterns", default="map16,map8_slow,two_stage,side_branch_chain,"
                                          "multiblock,syntax_gauntlet,mutating_loop,map_reduce")
    ap.add_argument("--reps", type=int, default=None, help="suite: 3; sweep: from the preset")
    ap.add_argument("--agents", default=None, help="load: 1,4,8; sweep: from the preset")
    ap.add_argument("--decoys", default="0,1")
    ap.add_argument("--turns", type=int, default=None, help="load: 4; sweep: the workload's")
    ap.add_argument("--tag-bets", action="store_true")
    ap.add_argument("--scout", action="store_true",
                    help="suite: also run spec with spec-ptc's scout pass (the sptc-hints fork)")
    ap.add_argument("--engine", choices=sorted(TAG_FIELDS), default="vllm")
    # sweep
    ap.add_argument("--preset", choices=sorted(PRESETS), default="core")
    ap.add_argument("--quick", action="store_true", help="same as --preset quick")
    ap.add_argument("--arms", default=None, help="comma list of ARMS names (default: preset)")
    ap.add_argument("--launch", action="store_true", help="start/stop one server per setup")
    ap.add_argument("--server", choices=sorted(SERVERS), default=None,
                    help="without --launch: the setup of the server at --base-url")
    ap.add_argument("--serve-cmd", default="vllm serve {model} --dtype half --max-model-len 8192 "
                                           "--gpu-memory-utilization 0.90 --port {port}")
    ap.add_argument("--server-timeout", type=float, default=900.0)
    ap.add_argument("--server-gap", type=float, default=10.0)
    ap.add_argument("--start-timeout", type=float, default=300.0)
    ap.add_argument("--run-timeout", type=float, default=900.0)
    ap.add_argument("--stop-factor", type=float, default=4.0)
    ap.add_argument("--rounds", type=int, default=None, help="launches per server (preset's)")
    ap.add_argument("--warm-pass", action="store_true", help="throwaway 1-agent run per launch")
    ap.add_argument("--no-salt", action="store_true", help="allow prefix-cache hits across runs")
    ap.add_argument("--no-cache-fill", dest="cache_fill", action="store_false",
                    help="measure on a launch that compiled fresh (default: relaunch first)")
    ap.add_argument("--pressure-config", choices=sorted(PRESSURE_CONFIGS), default="chosen",
                    help="the KV config of the pressure servers (fcfs_p, priority_p, "
                         "plugin_p): the simulated study's choice, or its fallback after the probe")
    # report
    ap.add_argument("--slo-session", type=float, default=2.0)
    ap.add_argument("--slo-tpot", type=float, default=2.0)
    ap.add_argument("--slo-ref", default=SLO_REF)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--predictions",
                    default=str(SIM_ROOT / "results" / "prereg_v3" / "predictions.json"))
    a = ap.parse_args()
    if a.quick:
        a.preset = "quick"
    if a.cmd == "suite" and a.reps is None:
        a.reps = 3
    if a.cmd == "load":
        a.agents, a.turns = a.agents or "1,4,8", a.turns or 4
    global TAG_FIELD
    TAG_FIELD = TAG_FIELDS[a.engine]
    SERVERS.update(pressure_servers(a.pressure_config))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fn = {"calib": calib, "predict": predict, "concur": concur, "suite": suite, "load": load,
          "sweep": sweep, "report": report, "plan": plan}[a.cmd]
    res = fn(a)
    name = a.cmd + ("_tagged" if a.cmd == "load" and a.tag_bets else "")
    if a.cmd == "plan":  # one file per preset, not the last one only
        name = f"plan_{a.preset}"
    (out / f"{name}.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()
