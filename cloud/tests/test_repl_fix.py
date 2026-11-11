"""rlms 0.1.3's LocalREPL races when several run as threads of one process (as in spec-ptc's
campaign runner), and cloud/repl_fix.py removes both races."""

from __future__ import annotations

import os
import sys
import threading
import time

import pytest
from rlm.environments.local_repl import LocalREPL

import repl_fix

A = "import time\nprint('A1')\ntime.sleep(0.4)\nprint('A2')"
B = "import time\nprint('B1')\ntime.sleep(0.6)\nprint('B2')"


@pytest.fixture
def stock_then_restore():
    cwd, out, err = os.getcwd(), sys.stdout, sys.stderr
    repl_fix.revert()
    yield
    repl_fix.revert()
    os.chdir(cwd)
    sys.stdout, sys.stderr = out, err


def two_at_once(code_a: str, code_b: str, cleanup_a: bool = False):
    """REPL A runs code_a; 0.2 s later REPL B runs code_b; A cleans up when done.
    Returns (stdout A, stdout B, errors): errors from either thread, then from a fresh
    LocalREPL() (its __init__ calls os.getcwd())."""
    ra, rb = LocalREPL(), LocalREPL()
    res: dict = {}
    errors: list[BaseException] = []

    def guard(fn):
        def run():
            try:
                fn()
            except BaseException as e:  # noqa: BLE001 - the race is what we record
                errors.append(e)
        return run

    def run_a():
        res["a"] = ra.execute_code(code_a)
        if cleanup_a:
            ra.cleanup()

    def run_b():
        time.sleep(0.2)
        res["b"] = rb.execute_code(code_b)

    ts = [threading.Thread(target=guard(run_a)), threading.Thread(target=guard(run_b))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    rb.cleanup()
    if not cleanup_a:
        ra.cleanup()
    try:
        LocalREPL().cleanup()
    except BaseException as e:  # noqa: BLE001
        errors.append(e)
    out = [res[k].stdout if k in res else None for k in ("a", "b")]
    return out[0], out[1], errors


def test_stock_rlms_misroutes_printed_output_between_concurrent_repls(stock_then_restore):
    out_a, out_b, _ = two_at_once(A, B)
    assert (out_a, out_b) != ("A1\nA2\n", "B1\nB2\n")
    assert "A2" in out_b or "A2" not in out_a  # A's second line went to B's buffer (or got lost)


def test_stock_rlms_strands_a_repl_in_a_removed_temp_dir(stock_then_restore):
    _, _, errors = two_at_once("import time\ntime.sleep(0.4)", "import time\ntime.sleep(0.6)",
                               cleanup_a=True)
    assert any(isinstance(e, FileNotFoundError) for e in errors)


def test_fixed_repls_keep_their_own_output_and_working_directory(stock_then_restore):
    cwd = os.getcwd()
    repl_fix.apply()
    assert repl_fix.applied()
    out_a, out_b, errors = two_at_once(A, B, cleanup_a=True)
    assert (out_a, out_b) == ("A1\nA2\n", "B1\nB2\n")
    assert not errors
    assert os.getcwd() == cwd
