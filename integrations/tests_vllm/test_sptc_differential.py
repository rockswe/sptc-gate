"""Requirement 4: with no bets, the sptc scheduler behaves exactly like vanilla vLLM FCFS.

A seeded random stream of requests (with enough KV pressure to force preemption) is driven
through a stock (Async)Scheduler and an sptc scheduler by the same engine loop; every
step's full SchedulerOutput, the scheduler's queues and KV usage, and every client output
must be identical.

The engine loop mirrors vLLM 0.32's EngineCore.step_with_batch_queue (vllm/v1/engine/
core.py): with a batch queue of 2 (async scheduling on a real server) the next step is
scheduled while the previous one is still in flight, so requests are scheduled with output
placeholders, finish on in-flight tokens and are preempted with stale output (audit #11).
A queue of 1 is the lockstep loop. Sampled tokens are fixed when a step is scheduled, as on
the GPU; some are EOS. Two configurations (audit #13): the narrow one (no prefix caching,
distinct prompts, a 256-token step) and a default-like one (prefix caching on, prompts
sharing per-agent prefixes, vLLM's default step budget and max_num_seqs, a small KV cache).
"""

import dataclasses
import enum
import random
import re
import zlib
from collections import deque

import pytest

pytest.importorskip("vllm")

from _helpers import EOS_TOKEN_ID, TOKEN, build, make_sched, req  # noqa: E402
from vllm.v1.outputs import ModelRunnerOutput  # noqa: E402

NARROW = dict(max_num_seqs=8, max_num_batched_tokens=256, num_blocks=40)
# vLLM 0.32 defaults (SchedulerConfig: 2048 tokens, 128 sequences; prefix caching on for
# generative models), with a KV cache small enough (47 usable blocks) to preempt
DEFAULT_LIKE = dict(max_num_seqs=128, max_num_batched_tokens=2048, num_blocks=48,
                    enable_prefix_caching=True)


def narrow_workload(seed: int, n: int = 60, steps: int = 200):
    rng = random.Random(seed)
    return sorted(
        (rng.randrange(steps), f"r{i}", None, rng.randint(1, 300), rng.randint(1, 40))
        for i in range(n)
    )


def default_like_workload(seed: int, n: int = 40, steps: int = 30, agents: int = 4):
    """Each request is one of `agents` agents' calls: that agent's prefix (32-96 tokens,
    shared) plus its own suffix, so the prefix cache hits across requests."""
    rng = random.Random(seed)
    prefixes = [
        [1 + (97 * a + k) % 30000 for k in range(rng.randint(32, 96))] for a in range(agents)
    ]
    out = []
    for i in range(n):
        base = 1 + zlib.crc32(f"r{i}|{seed}".encode()) % 20000
        suffix = [(base + k) % 30000 + 1 for k in range(rng.randint(1, 150))]
        prompt = prefixes[rng.randrange(agents)] + suffix
        out.append((rng.randrange(steps), f"r{i}", prompt, len(prompt), rng.randint(20, 120)))
    return sorted(out, key=lambda x: (x[0], x[1]))


_ADDR = re.compile(r" at 0x[0-9a-fA-F]+")


def norm(v):
    """A comparable, immutable copy of any SchedulerOutput field (taken right after
    schedule(), before the scheduler mutates lists it shares with the output)."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, enum.Enum):
        return f"{type(v).__name__}.{v.name}"
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return (type(v).__name__,) + tuple(
            (f.name, norm(getattr(v, f.name))) for f in dataclasses.fields(v)
        )
    if isinstance(v, dict):
        return ("dict",) + tuple(sorted((repr(k), norm(x)) for k, x in v.items()))
    if isinstance(v, (set, frozenset)):
        return ("set",) + tuple(sorted(repr(norm(x)) for x in v))
    if isinstance(v, (list, tuple, deque)):
        return tuple(norm(x) for x in v)
    return (type(v).__name__, _ADDR.sub("", repr(v)))


def state(s):
    return (
        [r.request_id for r in s.running],
        [r.request_id for r in s.waiting],
        [r.request_id for r in s.kv_holding_waiting],
        sorted(r.request_id for r in s.deferred_waiting),
        s.kv_cache_manager.usage,
        s.prefill_capacity_bound,
    )


def client_view(outs):
    return sorted(
        (o.request_id, tuple(o.new_token_ids), o.finish_reason, o.stop_reason)
        for eco in outs.values()
        for o in eco.outputs
    )


def model_output(s, out, t) -> ModelRunnerOutput:
    """The model runner's result for `out`, fixed when the step is scheduled: one token per
    request that finished its prefill (EOS on a hash of request and loop index, about 1 in
    61 tokens, so outputs stay long enough for KV pressure), none for a partial prefill
    chunk."""
    ids = list(out.num_scheduled_tokens)

    def token(rid):
        return EOS_TOKEN_ID if zlib.crc32(f"{rid}:{t}".encode()) % 61 == 0 else TOKEN

    return ModelRunnerOutput(
        req_ids=ids,
        req_id_to_index={r: k for k, r in enumerate(ids)},
        sampled_token_ids=[[] if s.requests[i].is_prefill_chunk else [token(i)] for i in ids],
        logprobs=None,
        prompt_logprobs_dict={},
        pooler_output=[],
    )


def drive(make, tag, arrivals, queue_size, seed, max_steps=4000):
    s = make()
    log, k, preemptions, queue = [], 0, 0, deque()
    for t in range(max_steps):
        while k < len(arrivals) and arrivals[k][0] <= t:
            _, rid, prompt, n, m = arrivals[k]
            s.add_request(req(rid, n, tag, max_tokens=m, seed=seed, prompt=prompt))
            k += 1
        if k == len(arrivals) and not s.requests and not queue:
            break
        # EngineCore.step_with_batch_queue
        if s.has_requests():
            out = s.schedule()
            preemptions += len(out.preempted_req_ids or ())
            log.append(("schedule", t, norm(out), state(s)))
            queue.appendleft((out, model_output(s, out, t)))
            if len(queue) < queue_size and (
                out.total_num_scheduled_tokens > 0 or s.has_requests()
            ):
                continue  # do not wait for the step in flight
        elif not queue:
            continue
        out, mo = queue.pop()
        outs = s.update_from_output(out, mo)
        log.append(("update", t, client_view(outs), state(s)))
    assert k == len(arrivals) and not s.requests and not queue, "workload did not drain"
    return log, preemptions


def max_chunk(log) -> int:
    """The most tokens scheduled for one request in one step (no spec decode here, so more
    than 1 is a prefill chunk)."""
    most = 0
    for e in log:
        if e[0] == "schedule":
            per_req = dict(e[2][1:])["num_scheduled_tokens"][1:]  # norm: ("dict", (k, v)...)
            most = max([most] + [n for _, n in per_req])
    return most


def check_binds(ref, tag, sptc):
    """A small budget on untagged traffic must be one the stock run exceeds, or the case
    cannot catch untagged prefill going through the cap (audit #13)."""
    budget = sptc.get("spec_prefill_budget")
    if tag is None and budget is not None and 0 < budget < 10**6:
        assert max_chunk(ref) > budget, "the budget never binds: the case checks nothing"


def compare(ref, got):
    assert len(got) == len(ref), (len(ref), len(got))
    for i, (a, b) in enumerate(zip(ref, got, strict=True)):
        assert a == b, f"entry {i} differs:\nvanilla {a}\nsptc    {b}"


MODES = pytest.mark.parametrize(
    "async_scheduling,queue_size",
    [(False, 1), (True, 1), (True, 2)],
    ids=["sync", "async-lockstep", "async-overlap"],
)
TAGS = pytest.mark.parametrize(
    "tag,sptc",
    [
        (None, {}),  # untagged traffic, default knobs
        # untagged, with a budget the workload exceeds: the 512 default never binds on
        # NARROW's 256-token steps, so (None, {}) alone misses untagged prefill being capped
        (None, {"spec_prefill_budget": 16}),
        ("early", {"spec_prefill_budget": 0}),  # early with the allowance off
        ("early", {"spec_prefill_budget": 10**6}),  # early, allowance never binds
        (None, {"prefill_allowance": "adaptive"}),
        (None, {"prefill_allowance": "off"}),
        ("early", {"prefill_allowance": "off"}),
        # all traffic tagged early: no untagged decoder, so adaptive never limits
        ("early", {"prefill_allowance": "adaptive", "spec_prefill_budget": 16}),
    ],
    ids=["normal", "normal-tiny-budget", "early-unlimited", "early-huge-budget", "normal-adaptive", "normal-off",
         "early-off", "early-adaptive"],
)


@MODES
@pytest.mark.parametrize("v2", [False, True], ids=["mrv1", "mrv2"])
@pytest.mark.parametrize("long_prefill", [0, 64])
@TAGS
def test_identical_to_vanilla(async_scheduling, queue_size, v2, long_prefill, tag, sptc):
    kw = dict(NARROW, async_scheduling=async_scheduling, use_v2_model_runner=v2,
              long_prefill_token_threshold=long_prefill)
    arrivals = narrow_workload(1234)
    ref, n_pre = drive(lambda: build(**kw), tag, arrivals, queue_size, seed=1234)
    got, _ = drive(lambda: make_sched(sptc, **kw), tag, arrivals, queue_size, seed=1234)
    assert n_pre > 0, "workload must exercise preemption"
    check_binds(ref, tag, sptc)
    compare(ref, got)


@MODES
@pytest.mark.parametrize("v2", [False, True], ids=["mrv1", "mrv2"])
@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize(
    "tag,sptc",
    # the 512 default does not bind on this workload either (on the stand-in, capping
    # untagged prefill passes "normal"), so the tiny budget is what checks it is never capped
    [(None, {}), (None, {"spec_prefill_budget": 16}), (None, {"prefill_allowance": "adaptive"}),
     ("early", {"prefill_allowance": "off"}), ("early", {"spec_prefill_budget": 10**6})],
    ids=["normal", "normal-tiny-budget", "normal-adaptive", "early-off", "early-huge-budget"],
)
def test_identical_to_vanilla_default_like(async_scheduling, queue_size, v2, seed, tag, sptc):
    kw = dict(DEFAULT_LIKE, async_scheduling=async_scheduling, use_v2_model_runner=v2)
    arrivals = default_like_workload(seed)
    ref, n_pre = drive(lambda: build(**kw), tag, arrivals, queue_size, seed=seed)
    got, _ = drive(lambda: make_sched(sptc, **kw), tag, arrivals, queue_size, seed=seed)
    peak = max(e[-1][4] for e in ref)  # KV usage
    print(f"default-like seed {seed}: {len(ref)} log entries, {n_pre} preemptions, "
          f"peak KV usage {peak:.2f}")
    # Preemption is not asserted here: prefix sharing makes it workload-dependent (the
    # narrow test asserts it). On the stand-in scheduler without a prefix cache this
    # workload preempts 8-9 times per seed.
    assert peak > 0.9, "workload must put the KV cache under pressure"
    check_binds(ref, tag, sptc)
    compare(ref, got)


def test_overlap_driver_keeps_steps_in_flight():
    """The async-overlap loop really schedules with a step in flight: output placeholders
    are seen at schedule time, and the workload preempts."""
    kw = dict(NARROW, async_scheduling=True)
    s = build(**kw)
    seen = {"placeholders": 0}
    orig = s.schedule

    def spy(*a, **k):
        seen["placeholders"] += sum(r.num_output_placeholders > 0 for r in s.running)
        return orig(*a, **k)

    s.schedule = spy
    arrivals = narrow_workload(1234)
    _, n_pre = drive(lambda: s, None, arrivals, 2, seed=1234)
    assert n_pre > 0 and seen["placeholders"] > 0
