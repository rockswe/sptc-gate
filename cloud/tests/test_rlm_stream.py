"""cloud/rlm_stream.py against a scripted fake server: the three campaign arms."""

from __future__ import annotations

import pytest
import rlm.environments as rlm_envs
from fake_rlm_server import FakeRLMServer
from rlm import RLM
from rlm.logger.rlm_logger import RLMLogger
from spec_ptc.contracts.events import EventBus

import rlm_stream
from rlm_stream import SpeculativeLocalREPL, StreamingRLM, StreamingSpecREPL

STOCK = rlm_envs.LocalREPL

ITER0 = (
    "I will label each part.\n"
    "```repl\n"
    "parts = [context[i:i+20] for i in range(0, 80, 20)]\n"
    "labels = []\n"
    "for p in parts:\n"
    "    labels.append(llm_query('Label this: ' + p))\n"
    "print(labels)\n"
    "```\n"
    "Then one more check on the start of the context.\n"
    "```repl\n"
    "extra = llm_query('Summarize: ' + context[:30])\n"
    "print(extra)\n"
    "```\n"
    + "Waiting for the results now. " * 15
)
ITER1 = (
    "```repl\n"
    "answer['content'] = 'done: ' + str(len(labels)) + ' ' + extra\n"
    "answer['ready'] = True\n"
    "```\n"
)
CONTEXT = "abcdefghij" * 10
N_SUB = 5  # 4 loop calls + 1 in the second block


class PerBlockTurnREPL(StreamingSpecREPL):
    """The naive integration: stream-fed, but spec-ptc's turn ends after every block."""

    def execute_code(self, code: str):  # type: ignore[override]
        return SpeculativeLocalREPL.execute_code(self, code)


@pytest.fixture
def repl_class():
    def use(cls):
        rlm_envs.LocalREPL = cls
        rlm_envs.local_repl.LocalREPL = cls

    yield use
    use(STOCK)


class Sink:
    def __init__(self) -> None:
        self.recs: list[dict] = []

    def log(self, kind: str, **data) -> None:
        self.recs.append({"kind": kind, **data})


def run(srv: FakeRLMServer, rlm_cls=StreamingRLM, spec_bus=None):
    env_kwargs = {"spec_bus": spec_bus} if spec_bus is not None else {}
    logger = RLMLogger(log_dir=None)
    r = rlm_cls(
        backend="openai",
        backend_kwargs={"model_name": srv.model, "base_url": srv.base_url, "api_key": "EMPTY"},
        environment="local",
        environment_kwargs=env_kwargs,
        max_iterations=4,
        sub_sampling_args={"max_tokens": 64},
        logger=logger,
        verbose=False,
    )
    sink = Sink()
    rlm_stream.bind_task("t1", sink)
    try:
        out = r.completion(prompt=CONTEXT, root_prompt="Question: label the parts")
    finally:
        rlm_stream.unbind_task()
    return out, logger.get_trajectory(), sink.recs


def subs(srv):
    return [r for r in srv.log if r["kind"] == "sub"]


def first_root_end(srv):
    return min(r["t_end"] for r in srv.log if r["kind"] == "root")


def counts(bus: EventBus) -> dict:
    out: dict = {}
    for e in bus.history:
        out[e.kind] = out.get(e.kind, 0) + 1
    return out


def test_nospec_runs_calls_one_at_a_time_after_the_stream(repl_class):
    repl_class(STOCK)
    with FakeRLMServer([ITER0, ITER1], token_s=0.015, sub_s=0.2) as srv:
        out, _, recs = run(srv)
    assert out.response.startswith("done: 4 label:")
    s = sorted(subs(srv), key=lambda r: r["t_start"])
    assert len(s) == N_SUB
    assert all(r["t_start"] >= first_root_end(srv) for r in s)
    assert all(b["t_start"] >= a["t_end"] - 0.02 for a, b in zip(s, s[1:]))  # no overlap
    roots = [r for r in recs if r["kind"] == "root_stream"]
    assert len(roots) == 2 and not any(r["fed"] for r in roots)
    assert roots[0]["tokens"] > 50 and roots[0]["tpot_ms"] > 0 and roots[0]["ttft_s"] >= 0
    # every delta's arrival time and the characters received by then
    arr = roots[0]["arrivals"]
    assert len(arr) == roots[0]["n_deltas"] and arr[-1][1] == len(ITER0)
    assert all(a[0] <= b[0] and a[1] < b[1] for a, b in zip(arr, arr[1:]))
    assert abs(arr[0][0] - 1000 * roots[0]["ttft_s"]) < 1
    assert arr[-1][0] <= 1000 * roots[0]["stream_s"] + 1
    # nothing overlaps the stream here, so the calls' time is all in the real run
    assert roots[0]["shadow_wait_s"] == 0 and roots[0]["exec_s"] > N_SUB * 0.2 * 0.9


def test_fanout_runs_the_loop_in_parallel_but_only_after_the_stream(repl_class):
    repl_class(SpeculativeLocalREPL)
    bus = EventBus()
    with FakeRLMServer([ITER0, ITER1], token_s=0.015, sub_s=0.2) as srv:
        out, _, _ = run(srv, spec_bus=bus)
    assert out.response.startswith("done: 4 label:")
    s = subs(srv)
    assert len(s) == N_SUB
    assert all(r["t_start"] >= first_root_end(srv) for r in s)
    loop = sorted(r["t_start"] for r in s if r["head"].startswith("Label this"))
    assert loop[-1] - loop[0] < 0.2  # the four loop calls overlap
    assert counts(bus).get("claim_hit", 0) >= 4


def test_stream_sends_calls_while_the_root_writes_and_claims_them_all(repl_class):
    repl_class(StreamingSpecREPL)
    bus = EventBus()
    with FakeRLMServer([ITER0, ITER1], token_s=0.015, sub_s=0.2) as srv:
        out, traj, recs = run(srv, spec_bus=bus)
    assert out.response.startswith("done: 4 label:")
    s = subs(srv)
    assert len(s) == N_SUB  # every call ran once: nothing evicted and re-run
    before = [r for r in s if r["t_start"] < first_root_end(srv)]
    assert len(before) >= 4
    c = counts(bus)
    assert c.get("claim_hit", 0) == N_SUB and c.get("claim_miss", 0) == 0
    roots = [r for r in recs if r["kind"] == "root_stream"]
    assert roots[0]["fed"] and roots[0]["n_blocks"] == 2


def test_ending_the_turn_per_block_loses_the_second_blocks_speculation(repl_class):
    """Why StreamingSpecREPL keeps the turn open until the reply's last block."""
    repl_class(PerBlockTurnREPL)
    bus = EventBus()
    with FakeRLMServer([ITER0, ITER1], token_s=0.015, sub_s=0.2) as srv:
        out, _, _ = run(srv, spec_bus=bus)
    assert out.response.startswith("done: 4 label:")
    c = counts(bus)
    assert c.get("claim_miss", 0) >= 1
    assert len(subs(srv)) > N_SUB  # the evicted call ran a second time


def test_streamed_root_matches_the_stock_turn(repl_class):
    """Same replies, same code blocks and outputs as rlms' own non-streamed turn."""
    repl_class(STOCK)
    with FakeRLMServer([ITER0, ITER1], token_s=0.002, sub_s=0.01) as srv:
        out_s, traj_s, _ = run(srv, StreamingRLM)
    with FakeRLMServer([ITER0, ITER1], token_s=0.002, sub_s=0.01) as srv:
        out_r, traj_r, _ = run(srv, RLM)
    assert out_s.response == out_r.response

    def shape(traj):
        return [
            (it["response"], [(b["code"], b["result"]["stdout"]) for b in it["code_blocks"]])
            for it in traj["iterations"]
        ]

    assert shape(traj_s) == shape(traj_r)


def test_a_runaway_root_reply_is_cut_and_the_task_goes_on(repl_class, monkeypatch):
    """rlms sets no max_tokens on the root. A reply past ROOT_MAX_DELTAS is cut there, the
    turn is recorded as truncated, and the next turn runs."""
    monkeypatch.setattr(rlm_stream, "ROOT_MAX_DELTAS", 40)
    repl_class(STOCK)
    runaway = "I keep thinking about this. " * 60  # no code block: about 360 tokens
    with FakeRLMServer([runaway, ITER1], token_s=0.002, sub_s=0.01) as srv:
        out, traj, recs = run(srv)
    roots = [r for r in recs if r["kind"] == "root_stream"]
    assert roots[0]["truncated"] and roots[0]["n_deltas"] == 40 and roots[0]["tokens"] == 40
    assert len(traj["iterations"][0]["response"]) < len(runaway) / 4
    assert not roots[1]["truncated"]  # the second turn ran in full
