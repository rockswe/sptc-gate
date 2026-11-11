"""rlms 0.1.3 loses prompts of every batch after a session's first; batch_fix answers them.

The first test is the defect itself, on stock rlms: if it stops failing, rlms or its HTTP
stack has changed and the fix may no longer be needed."""

from __future__ import annotations

import gc
import threading
import time

import batch_fix
import pytest
from fake_rlm_server import FakeRLMServer
from rlm.clients.openai import OpenAIClient
from rlm.core.lm_handler import LMHandler
from rlm.environments.local_repl import LocalREPL

LOST = "Error: llm() call failed - Event loop is closed"


@pytest.fixture
def fixed():
    batch_fix.apply()
    batch_fix.stats(reset=True)
    try:
        yield
    finally:
        batch_fix.revert()


def max_in_flight(recs: list[dict]) -> int:
    marks = sorted([(r["t_start"], 1) for r in recs] + [(r["t_end"], -1) for r in recs])
    cur = top = 0
    for _, d in marks:
        cur += d
        top = max(top, cur)
    return top


def test_stock_rlms_loses_prompts_of_every_batch_after_the_first():
    assert not batch_fix.applied()
    with FakeRLMServer(["x"], sub_s=0.02) as srv:
        p = batch_fix.probe(srv.base_url, srv.model, gaps=(0.0,))
    assert p["fixed"] is False and p["prompts"] == 80
    # 16 connections stay open after a batch of 20; the next batch's first 16 prompts get
    # them and fail; the 4 that succeed leave 4 connections for the batch after that
    assert [b["errors"] for b in p["batches"]] == [0, 16, 4, 16]
    assert p["errors"] == p["loop_errors"] == 36
    assert p["batches"][1]["first_error"] == LOST


def test_with_the_fix_every_prompt_is_answered_once_at_rlms_own_width(fixed):
    with FakeRLMServer(["x"], sub_s=0.02) as srv:
        p = batch_fix.probe(srv.base_url, srv.model, gaps=(0.0,))
        subs = [r for r in srv.log if r["kind"] == "sub"]
    assert p["fixed"] is True
    assert [b["errors"] for b in p["batches"]] == [0, 0, 0, 0] and p["errors"] == 0
    assert len(subs) == 80  # every prompt sent, none twice
    assert max_in_flight(subs) == 16  # LMHandler.batch_max_concurrent, untouched
    # the connections the first batch opened serve the other three
    assert len({r["port"] for r in subs}) == 16
    assert batch_fix.stats() == {"calls": 80, "failed": {}}


def test_a_program_gets_the_answers_single_calls_give_in_its_prompts_order(fixed):
    code = (
        "ps = ['Q' + str(i) for i in range(45)]\n"
        "out = []\n"
        "for i in range(0, 45, 15):\n"  # three batches: stock rlms loses the second whole
        "    out += llm_query_batched(ps[i:i+15])\n"
        "print(out == [llm_query(p) for p in ps], sum(o.startswith('Error') for o in out))\n")
    with FakeRLMServer(["x"], sub_s=0.01) as srv:
        client = OpenAIClient(api_key="EMPTY", model_name=srv.model, base_url=srv.base_url)
        with LMHandler(client) as h:
            repl = LocalREPL(lm_handler_address=h.address, context_payload="ctx")
            r = repl.execute_code(code)
            repl.cleanup()
        usage = client.get_usage_summary().model_usage_summaries[srv.model]
    assert r.stdout.strip() == "True 0", r.stdout + r.stderr
    # every answer is in the trajectory (a lost prompt leaves no record) and in the usage
    assert len(r.rlm_calls) == 90 and usage.total_calls == 90


def test_the_same_program_on_stock_rlms_counts_error_strings():
    code = ("out = []\n"
            "for i in range(0, 45, 15):\n"
            "    out += llm_query_batched(['Q' + str(j) for j in range(i, i + 15)])\n"
            "print(sum(o.startswith('Error') for o in out), len(out))\n")
    with FakeRLMServer(["x"], sub_s=0.01) as srv:
        client = OpenAIClient(api_key="EMPTY", model_name=srv.model, base_url=srv.base_url)
        with LMHandler(client) as h:
            repl = LocalREPL(lm_handler_address=h.address, context_payload="ctx")
            r = repl.execute_code(code)
            repl.cleanup()
    # The second batch is handed the first one's 15 connections and fails whole. A failed
    # connection is dropped, so the third batch opens its own and is answered.
    assert r.stdout.strip() == "15 45", r.stdout + r.stderr
    assert len(r.rlm_calls) == 30  # a lost prompt leaves no record


def test_a_server_that_closes_idle_connections_costs_no_prompt(fixed):
    """uvicorn closes a kept connection after 5 s without a request. A batch that comes
    later finds the connections of the batch before it closed by the server."""
    with FakeRLMServer(["x"], sub_s=0.01, idle_close_s=0.2) as srv:
        p = batch_fix.probe(srv.base_url, srv.model, batches=3, gaps=(0.7, 0.0))
        ports = {r["port"] for r in srv.log if r["kind"] == "sub"}
    assert [b["errors"] for b in p["batches"]] == [0, 0, 0]
    assert len(ports) > 16  # the second batch had to open its own connections


def test_a_real_failure_comes_back_as_an_error_string_and_is_counted(fixed):
    """The fix removes one cause of failed prompts. Any other still reaches the program as
    rlms would report it, and is counted."""
    with FakeRLMServer(["x"], sub_s=0.01) as srv:
        client = OpenAIClient(api_key="EMPTY", model_name=srv.model, base_url=srv.base_url,
                              max_retries=0)
        with LMHandler(client) as h:
            repl = LocalREPL(lm_handler_address=h.address, context_payload="ctx")
            assert repl._llm_query_batched(["a"]) == [repl._llm_query("a")]
            srv._httpd.shutdown()  # the engine stops taking connections
            srv._httpd.server_close()
            res = repl._llm_query_batched(["b", "c", "d"])
            repl.cleanup()
    # the one connection the client kept is still served; the other two prompts find no engine
    assert res[0] == "label: no" and res[1:] == ["Error: llm() call failed - Connection error."] * 2
    assert batch_fix.stats() == {"calls": 4, "failed": {"APIConnectionError": 2}}


def test_a_clients_loop_ends_when_the_client_does(fixed):
    def loops():
        return {t for t in threading.enumerate() if t.name == "rlms-batch-http"}

    before = loops()
    with FakeRLMServer(["x"], sub_s=0.01) as srv:
        client = OpenAIClient(api_key="EMPTY", model_name=srv.model, base_url=srv.base_url)
        with LMHandler(client) as h:
            repl = LocalREPL(lm_handler_address=h.address, context_payload="ctx")
            for _ in range(3):
                assert len(repl._llm_query_batched(["a", "b"])) == 2
            repl.cleanup()
        assert len(loops() - before) == 1  # one loop per client, whatever the number of batches
        del client, h, repl
        gc.collect()
        deadline = time.time() + 5
        while loops() - before and time.time() < deadline:
            time.sleep(0.05)
        assert loops() - before == set()


def test_apply_and_revert():
    assert OpenAIClient.acompletion is batch_fix.STOCK and not batch_fix.applied()
    batch_fix.apply()
    try:
        assert batch_fix.applied() and OpenAIClient.acompletion is batch_fix.acompletion
    finally:
        batch_fix.revert()
    assert OpenAIClient.acompletion is batch_fix.STOCK
