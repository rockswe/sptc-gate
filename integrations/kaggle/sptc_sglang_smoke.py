"""End-to-end smoke test of sptc_sglang through SGLang's OpenAI API (run on Kaggle).

Server for S1-S3 (the plugin is an installed entry point, switched on by the env var):
  SPTC_SGLANG_CONFIG='{"free_window": 2}' python -m sglang.launch_server \
    --model-path Qwen/Qwen2.5-0.5B-Instruct --dtype half --port 8000 --context-length 4096
  python sptc_sglang_smoke.py --cases s1,s2,s3
Restart for S4 (small KV so a running bet must be retracted, i.e. dropped):
  SPTC_SGLANG_CONFIG='{}' python -m sglang.launch_server ... --max-total-tokens 3200 \
    --context-length 2560
  python sptc_sglang_smoke.py --cases s4

Prints one JSON line per check and exits 1 if any check failed. Also grep the server log for
"Traceback" and for "sptc scheduler on" afterwards. S3 also compares a concurrent stream's
longest stall with and without the prefill allowance; that check is a measurement and can
fail on its own (for example if the server's chunk size is no larger than
spec_prefill_budget).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time

from openai import OpenAI

FAILED: list[str] = []


def report(name: str, ok: bool, **info) -> None:
    print(json.dumps({"check": name, "ok": ok, **info}), flush=True)
    if not ok:
        FAILED.append(name)


def chat(c, model, prompt, *, cls=None, stream=False, max_tokens=16, ignore_eos=False):
    body: dict = {}
    if cls:
        body["custom_params"] = {"sptc_class": cls}
    if ignore_eos:
        body["ignore_eos"] = True
    return c.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=stream,
        max_tokens=max_tokens,
        temperature=0.0,
        extra_body=body or None,
    )


def consume(resp, out: dict) -> dict:
    """Drain a stream: text, finish_reason/matched_stop of the last choice, token times."""
    out.update(text="", finish=None, stop=None, times=[])
    for ch in resp:
        if not ch.choices:
            continue
        c = ch.choices[0]
        if c.delta and c.delta.content:
            out["text"] += c.delta.content
            out["times"].append(time.perf_counter())
        if c.finish_reason:
            out["finish"], out["stop"] = c.finish_reason, getattr(c, "matched_stop", None)
    out["done"] = True
    return out


def background_stream(c, model, prompt, max_tokens, cls=None) -> tuple[threading.Thread, dict]:
    out: dict = {"done": False}
    t = threading.Thread(
        target=lambda: consume(
            chat(c, model, prompt, cls=cls, stream=True, max_tokens=max_tokens, ignore_eos=True),
            out,
        ),
        daemon=True,
    )
    t.start()
    return t, out


def wait_tokens(out: dict, n: int = 3, timeout: float = 120.0) -> None:
    t0 = time.time()
    while len(out.get("times", [])) < n and time.time() - t0 < timeout:
        time.sleep(0.05)


def s1(c, model):
    r = chat(c, model, "Count from 1 to 50.", cls="bet", max_tokens=8, ignore_eos=True)
    ch = r.choices[0]
    report("S1 idle bet completes", ch.finish_reason == "length", finish=ch.finish_reason)


def s2(c, model):
    bg = [background_stream(c, model, f"Write a long story #{i}.", 512) for i in range(2)]
    for _, o in bg:
        wait_tokens(o)
    r = chat(c, model, "Say hi.", cls="bet", max_tokens=16)
    ch = r.choices[0]
    stop = getattr(ch, "matched_stop", None)
    report(
        "S2 non-streaming bet rejected",
        ch.finish_reason == "abort" and stop == "sptc_bet_rejected",
        finish=ch.finish_reason, stop=stop, text=ch.message.content,
    )
    o = consume(chat(c, model, "Say hi.", cls="bet", stream=True, max_tokens=16), {})
    report(
        "S2 streaming bet rejected",
        o["finish"] == "abort" and o["stop"] == "sptc_bet_rejected" and o["text"] == "",
        finish=o["finish"], stop=o["stop"], text=o["text"],
    )
    for t, _ in bg:
        t.join()


def s3(c, model, repeats: int = 3):
    """The prefill allowance seen from a concurrent stream, as in sptc_vllm_smoke.py. A
    ~3000-token call arrives while a normal stream decodes, untagged (no allowance) or
    tagged `early` (at most spec_prefill_budget prefill tokens per step, with decode steps
    forced in between). Each pass uses its own prompt, so the prefix cache cannot serve it
    (audit #41: both passes used to send the same prompt). The stream's largest gap and its
    gaps above 3x its median gap are taken while the call runs; passes alternate, `repeats`
    of each; the check compares the medians of the largest gaps."""
    res: dict = {"untagged": [], "tagged": []}
    finishes = []
    for k in range(repeats):
        for tagged in (False, True):
            name = "tagged" if tagged else "untagged"
            t, o = background_stream(c, model, f"Write a long story ({name} {k}).", 400)
            wait_tokens(o, 20)
            prompt = f"Pass {name} {k}. " + "word " * 3000 + "\nSummarize."
            t0 = time.perf_counter()
            r = chat(c, model, prompt, cls="early" if tagged else None, max_tokens=16)
            t1 = time.perf_counter()
            t.join()
            finishes.append(r.choices[0].finish_reason)
            times = o["times"]
            gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
            during = [b - a for a, b in zip(times, times[1:], strict=False) if a < t1 and b > t0]
            med = statistics.median(gaps) if gaps else 0.0
            res[name].append({
                "max_gap_ms": round(max(during, default=0.0) * 1e3, 2),
                "gaps_over_3x_median": sum(g > 3 * med for g in during),
                "median_gap_ms": round(med * 1e3, 2),
            })
    report("S3 early call completes", all(f in ("length", "stop") for f in finishes),
           finishes=finishes)
    med_max = {n: statistics.median(x["max_gap_ms"] for x in v) for n, v in res.items()}
    report(
        "S3 allowance shortens the concurrent stream's longest stall",
        med_max["tagged"] < med_max["untagged"],
        median_max_gap_ms=med_max, passes=res,
    )


def s4(c, model):
    tb, ob = background_stream(c, model, "Write an extremely long essay.", 1500, cls="bet")
    wait_tokens(ob, 20)
    fill = [background_stream(c, model, "word " * 600 + "\nContinue.", 1500) for _ in range(3)]
    tb.join(timeout=600)
    report(
        "S4 running bet dropped under KV pressure",
        ob.get("finish") == "abort" and ob.get("stop") == "sptc_bet_dropped" and ob["text"] != "",
        finish=ob.get("finish"), stop=ob.get("stop"), bet_chars=len(ob.get("text", "")),
    )
    for t, o in fill:
        t.join(timeout=600)
    report(
        "S4 normal requests finish (retracted, not dropped)",
        all(o.get("finish") == "length" for _, o in fill),
        finishes=[o.get("finish") for _, o in fill],
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--cases", default="s1,s2,s3")
    ap.add_argument("--s3-repeats", type=int, default=3)
    a = ap.parse_args()
    c = OpenAI(base_url=a.base_url, api_key="EMPTY", timeout=600, max_retries=0)
    cases = {"s1": s1, "s2": s2, "s3": lambda c, m: s3(c, m, a.s3_repeats), "s4": s4}
    for name in a.cases.split(","):
        cases[name.strip()](c, a.model)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
