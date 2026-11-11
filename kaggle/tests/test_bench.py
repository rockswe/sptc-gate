"""Fast tests of kaggle/vllm_bench.py: the HTTP client against the fake server (priority
field, scheduler tags, rejected / dropped / cancelled streams), outcome classification,
statistics, goodput and the resume bookkeeping. About 5 s, no GPU."""

from __future__ import annotations

import json
import sys
import threading
import time
import types

import pytest
import vllm_bench as vb


def _log(url: str) -> list[dict]:
    return json.loads(vb.client(url).get("/fake/log"))


# ----------------------------------------------------------------------------- client
def test_raw_stream_counts_tokens_and_usage(fake):
    url = fake()
    o = {}
    vb.stream(vb.client(url), "fake-model", "hello " * 20, 25, o)
    assert len(o["times"]) == 25
    assert o["finish"] == "length" and o["usage"] == {"prompt": 30, "completion": 25}
    assert vb.outcome(o) == "completed"
    rec = _log(url)[0]
    assert rec["ignore_eos"] and rec["path"] == "completions"


def test_chat_stream_natural_length_ignores_role_chunk(fake):
    url = fake()
    o = {}
    vb.stream(vb.client(url), "fake-model", "a question", 200, o, natural=True)
    assert o["finish"] == "stop"
    assert len(o["times"]) == o["usage"]["completion"]  # the role-only chunk is not a token


def test_tags_reach_the_server(fake):
    url = fake()
    cl = vb.client(url)
    for scheme, kind in (("priority", "early"), ("priority", "bet"), ("priority", "call"),
                         ("sptc", "early"), ("sptc", "bet"), ("none", "bet"),
                         ("priority", "root")):
        vb.stream(cl, "fake-model", f"{scheme} {kind}", 2, {}, body=vb.tag_body(scheme, kind))
    got = [(r["priority"], r["vllm_xargs"]) for r in _log(url)]
    assert got == [(1, None), (1, None), (None, None), (None, {"sptc_class": "early"}),
                   (None, {"sptc_class": "bet"}), (None, None), (None, None)]


def test_sglang_tag_field(fake, monkeypatch):
    url = fake()
    monkeypatch.setattr(vb, "TAG_FIELD", vb.TAG_FIELDS["sglang"])
    vb.stream(vb.client(url), "fake-model", "x", 2, {}, body=vb.tag_body("sptc", "bet"))
    assert _log(url)[0]["custom_params"] == {"sptc_class": "bet"}


def _busy(url: str, n: int, tokens: int = 300) -> list[threading.Thread]:
    ths = [threading.Thread(target=vb.stream, args=(vb.client(url), "fake-model", f"bg {i}",
                                                    tokens, {})) for i in range(n)]
    for t in ths:
        t.start()
    time.sleep(0.15)
    return ths


@pytest.mark.parametrize("natural", [False, True])
def test_rejected_bet_streams_nothing(fake, natural):
    url = fake("--scheduler-cls", "sptc_vllm.scheduler.SptcScheduler",
               "--additional-config", json.dumps({"sptc": {"free_window": 2}}))
    ths = _busy(url, 2)
    o = {}
    vb.stream(vb.client(url), "fake-model", "bet", 20, o, natural=natural,
              body=vb.tag_body("sptc", "bet"))
    for t in ths:
        t.join()
    assert o["finish"] is None and o["times"] == [] and o["done_marker"]
    assert vb.outcome(o) == "rejected"


def test_dropped_bet(fake):
    # KV holds 300 tokens: a running bet is dropped once normal streams grow past that
    url = fake("--scheduler-cls", "sptc_vllm.scheduler.SptcScheduler", "--kv-tokens", "300")
    o = {}
    t = threading.Thread(target=vb.stream, args=(vb.client(url), "fake-model", "bet", 400, o),
                         kwargs={"body": vb.tag_body("sptc", "bet")})
    t.start()
    time.sleep(0.1)
    for t2 in _busy(url, 2, 200):
        t2.join()
    t.join()
    assert o["finish"] == "abort" and o["stop"] == "sptc_bet_dropped" and o["times"]
    assert vb.outcome(o) == "dropped"


def test_cancel_running_and_waiting(fake):
    url = fake("--max-running", "1")
    cl = vb.client(url)
    run, wait = {}, {}
    t1 = threading.Thread(target=vb.stream, args=(cl, "fake-model", "long", 2000, run))
    t1.start()
    time.sleep(0.2)
    t2 = threading.Thread(target=vb.stream, args=(cl, "fake-model", "queued", 20, wait))
    t2.start()
    time.sleep(0.2)
    vb.cancel(wait)  # still queued: no token yet
    vb.cancel(run)
    t1.join(5)
    t2.join(5)
    assert not t1.is_alive() and not t2.is_alive()
    assert vb.outcome(run) == "cancelled" and 0 < len(run["times"]) < 2000
    assert vb.outcome(wait) == "cancelled" and wait["times"] == []
    time.sleep(0.1)
    assert [r["outcome"] for r in _log(url)] == ["client_abort", "client_abort"]


def test_cancel_before_connect_and_after_done():
    o = {}
    vb.cancel(o)  # before the stream even started
    assert o["cancelled"]
    done = {"done": True}
    vb.cancel(done)
    assert "cancelled" not in done


def test_should_stop_closes_the_stream(fake):
    url = fake()
    o = {}
    vb.stream(vb.client(url), "fake-model", "x", 1000, o,
              should_stop=lambda: len(o["times"]) >= 5)
    assert vb.outcome(o) == "cancelled" and len(o["times"]) == 5


def test_priority_server_orders_waiting(fake):
    url = fake("--scheduling-policy", "priority", "--max-running", "2")
    ths = _busy(url, 2, 100)
    lo, hi = {}, {}
    tl = threading.Thread(target=vb.stream, args=(vb.client(url), "fake-model", "low", 20, lo),
                          kwargs={"body": vb.tag_body("priority", "bet")})
    tl.start()
    time.sleep(0.05)
    vb.stream(vb.client(url), "fake-model", "high", 20, hi)
    tl.join()
    for t in ths:
        t.join()
    assert hi["t0"] + hi["times"][0] < lo["t0"] + lo["times"][0]


def test_http_error_is_an_outcome(fake):
    url = fake()
    o = {}
    vb.stream(vb.client(url), "fake-model", "x", 5, o, body={"priority": "high"})
    assert vb.outcome(o) == "error" and "HTTP 400" in o["finish"]


def test_no_server():
    o = {}
    vb.stream(vb.client("http://127.0.0.1:9/v1"), "m", "x", 5, o)
    assert vb.outcome(o) == "error"


# ----------------------------------------------------------------------------- outcome
@pytest.mark.parametrize("o,want", [
    ({"finish": "length", "times": [1]}, "completed"),
    ({"finish": "stop", "times": [1]}, "completed"),
    ({"finish": "abort", "stop": "sptc_bet_rejected", "times": []}, "rejected"),
    ({"finish": None, "times": [], "done_marker": True}, "rejected"),
    ({"finish": "abort", "stop": "sptc_bet_dropped", "times": [1, 2]}, "dropped"),
    ({"finish": "client_abort", "cancelled": True, "times": [1]}, "cancelled"),
    ({"finish": "length", "cancelled": True, "times": [1]}, "completed"),
    ({"finish": "abort", "stop": None, "times": [1]}, "aborted"),
    ({"finish": "error: X", "times": []}, "error"),
    ({"finish": None, "times": []}, "unknown"),
])
def test_outcome(o, want):
    assert vb.outcome(o) == want


# ----------------------------------------------------------------------------- analysis
def test_pctl_nearest_rank():
    xs = list(range(1, 101))
    assert vb.pctl(xs, 0.5) == 51 and vb.pctl(xs, 0.99) == 100
    assert vb.pctl([None, float("nan")], 0.5) is None
    assert vb.pctl([3.0], 0.99) == 3.0


def test_boot_ci_brackets_and_is_deterministic():
    groups = [[1.0, 2.0, 3.0], [2.0, 3.0, 4.0], [10.0, 11.0, 12.0]]
    stat = lambda p: vb.pctl(p, 0.5)  # noqa: E731
    ci = vb.boot_ci(groups, stat, b=300)
    assert ci == vb.boot_ci(groups, stat, b=300)
    assert ci[0] <= vb.pctl([x for g in groups for x in g], 0.5) <= ci[1]
    assert vb.boot_ci([[5.0, 5.0]], stat, b=50) == [5.0, 5.0]
    assert vb.boot_ci([], stat) is None


def _ses(pattern, wall, tpot, decoys=()):
    return {"pattern": pattern, "wall_s": wall, "root_tpot_ms": tpot, "root_itl_p99_ms": tpot,
            "sub_refused": 0, "calls": [], "decoys": [{"outcome": d} for d in decoys]}


def _run(arm, n, rep, sessions, status="ok", makespan=10.0):
    return {"arm": arm, "server": arm.split("/")[0], "agents": n, "rep": rep, "status": status,
            "sessions": sessions, "makespan_s": makespan, "client_cpu_util": 0.1,
            "server_metrics": {"preemptions": 2.0, "max_waiting": 3.0, "max_kv": 0.5}}


def test_goodput_and_summary():
    runs = [_run("fcfs/nospec", 1, r, [_ses("a", 2.0, 10.0), _ses("b", 4.0, 10.0)])
            for r in range(3)]
    runs += [_run("fcfs/spec+bad", 4, 0, [_ses("a", 3.9, 19.0, ["completed", "cancelled"]),
                                          _ses("b", 9.0, 15.0, ["cancelled"])]),
             _run("fcfs/spec+bad", 4, 1, [_ses("a", 1.0, 25.0)], status="timeout")]
    s = vb.summarize(runs, boot=50)
    assert s["slo"]["refs"] == {"a": {"wall_s": 2.0, "root_tpot_ms": 10.0},
                                "b": {"wall_s": 4.0, "root_tpot_ms": 10.0}}
    row = next(r for r in s["rows"] if r["arm"] == "fcfs/spec+bad")
    # a: 3.9 <= 4 and 19 <= 20 -> good; b: 9 > 8 -> not; the timeout run is excluded
    assert row["goodput"] == 0.5 and row["reps_ok"] == 1 and row["reps_other"] == {"timeout": 1}
    assert row["decoy_outcomes"] == {"completed": 1, "cancelled": 2}
    assert row["goodput_curve"]["5.0"] == 1.0 and row["goodput_curve"]["1.0"] == 0.0
    assert row["sessions_per_min"] == pytest.approx(12.0)
    # each half alone: walls 3.9 ok, 9.0 not; TPOTs 19 and 15 both ok
    assert row["goodput_wall"] == 0.5 and row["goodput_tpot"] == 1.0
    # 2 sessions: the p99 is the maximum, and no p99 gets a bootstrap CI
    assert row["p99_is_max"] and row["session_p99"] == 9.0
    assert set(row["ci"]) == {"session_p50", "root_tpot_p50", "goodput"}
    assert row["cpu_ok"] is None  # host CPU not measured in these records
    md = vb.summary_md(s)
    assert "fcfs/spec+bad" in md and "9.00 (max)" in md


def test_host_cpu_validity():
    runs = [_run("fcfs/nospec", 1, 0, [_ses("a", 2.0, 10.0)]) | {"host_cpu_util": 0.5,
                                                                  "host_cpu_sat_frac": 0.0},
            _run("fcfs/spec", 8, 0, [_ses("a", 2.0, 10.0)]) | {"host_cpu_util": 0.5,
                                                               "host_cpu_sat_frac": 0.0},
            _run("fcfs/spec", 8, 1, [_ses("a", 2.0, 10.0)]) | {"host_cpu_util": 0.9,
                                                               "host_cpu_sat_frac": 0.0},
            _run("prio/spec", 8, 0, [_ses("a", 2.0, 10.0)]) | {"host_cpu_util": 0.6,
                                                               "host_cpu_sat_frac": 0.2}]
    ok = {(r["arm"], r["agents"]): r["cpu_ok"] for r in vb.summarize(runs, boot=0)["rows"]}
    assert ok == {("fcfs/nospec", 1): True, ("fcfs/spec", 8): False, ("prio/spec", 8): False}


def test_host_cpu_sampler(tmp_path):
    stat = tmp_path / "stat"
    assert vb.cpu_times("cpu  1 2 3 4 5 6 7 8 9 10\ncpu0 1 1 1 1 1 1 1 1\n") == (27.0, 36.0)
    h = vb.HostCpu(str(stat))
    for busy, idle in ((100, 300), (180, 320), (280, 320)):  # 0.8 busy, then 1.0
        stat.write_text(f"cpu  {busy} 0 0 {idle} 0 0 0 0 0 0\n")
        h.sample()
    r = h.result()
    assert r["host_cpu_util"] == pytest.approx(180 / 200) and r["host_cpu_peak"] == 1.0
    assert r["host_cpu_sat_frac"] == 0.5
    none = vb.HostCpu(str(tmp_path / "missing"))
    none.sample()
    assert none.result()["host_cpu_util"] is None


def test_derived_questions():
    def rows(arm, p50s):
        return [{"arm": arm, "agents": n, "reps_ok": 1, "session_p50": v, "goodput": g,
                 "root_tpot_p99": 10.0 * v} for n, (v, g) in p50s.items()]
    rs = (rows("fcfs/nospec", {1: (6.0, 1.0), 8: (8.0, 0.9), 16: (10.0, 0.6)})
          + rows("fcfs/spec+bad", {1: (3.0, 1.0), 8: (7.0, 0.7), 16: (12.0, 0.3)})
          + rows("prio/spec+bad", {1: (3.0, 1.0), 8: (6.3, 0.8), 16: (11.0, 0.4)})
          + rows("plugin/spec+bad", {1: (4.0, 1.0), 8: (7.0, 1.0), 16: (8.5, 1.0)}))
    d = vb.derived(rs)
    assert d["knee"]["fcfs/spec+bad"] == 8 and d["knee"]["fcfs/nospec"] is None
    # slower at 1 agent: its own knee is later, against stock FCFS's 1-agent p50 it is not
    assert d["knee"]["plugin/spec+bad"] == 16 and d["knee_ref"]["plugin/spec+bad"] == 8
    assert d["knee_ref"]["fcfs/spec+bad"] == 8
    assert d["growth"]["plugin/spec+bad"][16] == pytest.approx(8.5 / 4.0)
    assert d["good50"]["fcfs/spec+bad"] == 16
    assert d["net_loss"]["fcfs"] == 16 and d["net_loss"]["prio"] is None
    assert d["prio_vs_fcfs"][8]["session_p50"] == pytest.approx(0.9)


def test_saturation_rule():
    runs = [_run("x/spec", 1, 0, [_ses("a", 2.0, 10.0)]),
            _run("x/spec", 8, 0, [_ses("a", 7.0, 10.0)]),
            _run("x/spec", 16, 0, [_ses("a", 9.0, 10.0)]),
            _run("x/spec", 24, 0, [], status="timeout")]
    assert vb.saturated(runs, "x/spec", 1, 4.0) is None
    assert vb.saturated(runs, "x/spec", 8, 4.0) is None
    assert "session p50" in vb.saturated(runs, "x/spec", 16, 4.0)
    assert vb.saturated(runs, "x/spec", 24, 4.0) == "timeout"


def test_metrics_parse():
    text = ('# HELP x\nvllm:num_requests_running{model_name="m",engine="0"} 3.0\n'
            'vllm:num_requests_running{model_name="m",engine="1"} 2.0\n'
            "vllm:num_preemptions_total 7.0\nvllm:num_preemptions_created 1.7e9\n")
    assert vb.MetricsPoller.parse(text, ("num_requests_running",)) == 5.0
    assert vb.MetricsPoller.parse(text, ("num_preemptions_total", "num_preemptions")) == 7.0
    assert vb.MetricsPoller.parse(text, ("kv_cache_usage_perc",)) is None


def test_run_files_and_resume_bookkeeping(tmp_path):
    p = vb.run_file(tmp_path, "plugin/spec+bad", 8, 2)
    assert p.name == "plugin__spec_plus_bad__n8__r2.json"
    assert not vb._done(p)
    vb.save_run(p, {"status": "error"})
    assert not vb._done(p)  # failed runs are redone on resume
    vb.save_run(p, {"status": "ok", "arm": "plugin/spec+bad"})
    assert vb._done(p) and vb.load_runs(tmp_path)[0]["arm"] == "plugin/spec+bad"
    p.with_name("broken.json").write_text("{")  # a half-written file is skipped
    assert len(vb.load_runs(tmp_path)) == 1


def test_arms_are_consistent():
    for x in vb.ARMS:
        assert x.server in vb.SERVERS and x.workload in vb.WORKLOADS
        assert x.tags in vb.TAG_SCHEMES and x.spec_kind in vb.SPEC_KINDS
        if x.gate:  # a client-side cap, in front of stock FCFS
            g = vb.ProxyGate(x.gate)
            flags = vb.SERVERS[x.server]["flags"]
            assert g.cap == vb.PLUGIN_CFG["sptc"]["free_window"] and x.server.startswith("fcfs")
            assert "--scheduler-cls" not in flags and "--scheduling-policy" not in flags
        assert (x.decoys == 0) or x.mode == "spec"
        assert x.spec_kind == "early" or (x.mode == "spec" and x.decoys == 1)
    for name, pre in vb.PRESETS.items():
        assert all(n in vb.ARM for n in pre["arms"])
        assert all(n in pre["arms"] for n in pre.get("only", {}))
        if name in ("quick", "core", "full", "ab"):  # presets that report goodput
            assert vb.SLO_REF in pre["arms"]

    def cfg(server):
        flags = vb.SERVERS[server]["flags"]
        return json.loads(flags[flags.index("--additional-config") + 1])

    assert cfg("plugin") == vb.PLUGIN_CFG and vb.PLUGIN_CFG["sptc"]["prefill_allowance"] == "fixed"
    # stock and priority share the plugin-fixed arm's compile hash (same additional_config)
    assert cfg("fcfs") == cfg("priority") == cfg("plugin") == cfg("plugin_eager")
    assert vb.SERVERS["priority"]["flags"][:2] == ["--scheduling-policy", "priority"]
    for mode in ("adaptive", "off"):
        assert cfg(f"plugin_{mode}")["sptc"]["prefill_allowance"] == mode
        assert vb.ALLOWANCE[f"plugin_{mode}_eager"] == mode
    for server, spec in vb.SERVERS.items():
        assert ("--enforce-eager" in spec["flags"]) == server.endswith("_eager")
        assert ("--scheduler-cls" in spec["flags"]) == server.startswith("plugin")
    assert vb.ALLOWANCE["fcfs"] is None and vb.ALLOWANCE["plugin"] == "fixed"


def test_ab_preset_plan(tmp_path):
    """ab: 1-agent rows 5 times, the rest 3; two launches per server; nospec and untagged
    only at 1 agent; vs_stock pairs every arm with stock FCFS of the same launch kind."""
    import argparse

    a = argparse.Namespace(preset="ab", arms=None, agents=None, reps=None, turns=None,
                           rounds=None, warm_pass=False, predictions=None)
    p = vb.plan(a)
    runs = {(r["arm"], r["agents"]): r["reps"] for r in p["rows"]}
    assert runs[("fcfs/spec", 1)] == 5 and runs[("fcfs/spec", 8)] == 3
    assert ("fcfs/nospec", 4) not in runs and ("plugin-untagged/spec", 8) not in runs
    assert p["launches"] == 8
    assert vb.stock_of("plugin-off-eager/spec") == "fcfs-eager/spec"
    assert vb.stock_of("plugin-adaptive/spec+bad") == "fcfs/spec+bad"


def test_launch_info():
    text = ("INFO Using cache directory: /root/.cache/vllm/torch_compile_cache/ab12/rank_0_0 "
            "for vLLM's torch.compile\nINFO Compiling a graph for compile range (1, 2048) "
            "takes 19.42 s\nINFO torch.compile took 32.04 s in total\n"
            "INFO sptc scheduler (SptcAsyncScheduler): free window 8, prefill allowance 512 "
            "(fixed)\n")
    info = vb.launch_info(text)
    assert info["cache_dir"].endswith("ab12/rank_0_0") and info["aot_loaded"] is None
    assert info["graph_compile_s"] == "19.42" and info["torch_compile_s"] == "32.04"
    assert info["sptc_line"].endswith("(fixed)") and info["enforce_eager"] is None
    # results/kaggle_t4/sptc_out/vllm.log: a cached launch names its artifact here instead
    aot = vb.launch_info("with config: model='Qwen/Qwen3-1.7B', enforce_eager=False, x\n"
                         "[backbone] Directly load AOT compilation from path /root/.cache/vllm/"
                         "torch_compile_cache/torch_aot_compile/18dd/rank_0_0/model\n")
    assert aot["aot_loaded"].endswith("18dd/rank_0_0/model") and aot["enforce_eager"] is False


def test_compile_state_and_cache_fill_rule():
    """vLLM 0.32's two startup kinds (results/kaggle_t4/sptc_out/vllm_plugin.log: fresh;
    vllm.log: AOT load). Only a fresh compile is relaunched before measuring."""
    fresh = vb.launch_info(
        "with config: model='Qwen/Qwen3-1.7B', enforce_eager=False, x\n"
        "INFO Using cache directory: /root/.cache/vllm/torch_compile_cache/f1a9f0de5e/rank_0_0/"
        "backbone for vLLM's torch.compile\n"
        "[decorators.py:743] [backbone] saved AOT compiled function to /root/.cache/vllm/"
        "torch_compile_cache/torch_aot_compile/3f9a27/rank_0_0/model\n"
        "INFO torch.compile took 32.04 s in total\n")
    assert fresh["aot_saved"].endswith("3f9a27/rank_0_0/model")
    assert vb.fresh_compile(fresh) is True
    aot = vb.launch_info("enforce_eager=False\n[backbone] Directly load AOT compilation from "
                         "path /root/.cache/vllm/torch_compile_cache/torch_aot_compile/3f9a27/"
                         "rank_0_0/model\nINFO torch.compile took 0.26 s in total\n")
    assert vb.fresh_compile(aot) is False and aot["aot_loaded"] == fresh["aot_saved"]
    assert vb.fresh_compile(vb.launch_info("enforce_eager=True\n")) is False
    assert vb.fresh_compile(vb.launch_info("fake server on :8000\n")) is None
    # stock, priority and plugin-fixed share one artifact; adaptive and off do not
    g = {k: vb.compile_group(v["flags"]) for k, v in vb.SERVERS.items()}
    assert g["fcfs"] == g["priority"] == g["plugin"] != g["plugin_adaptive"] != g["plugin_off"]
    assert g["fcfs"] != g["fcfs_eager"]


def test_b4_arms_send_the_same_prompts():
    """Preset `baselines` (same_prompts): every arm's prefix is the same text; arms that
    share a launch are kept apart by cache_salt, or, if the server refuses it, by a
    numbered prefix."""
    pre = vb.PRESETS["baselines"]
    fc = [vb.ARM[x] for x in pre["arms"] if vb.ARM[x].server == "fcfs"]
    var = vb.salt_variants(fc, same_prompts=True)
    assert sorted(var.values()) == [0, 1, 2, 3] and var[vb.BASELINE_REF] == 0
    for x in pre["arms"]:
        arm = vb.ARM[x]
        v = var.get(x, 0)
        salt, cs = vb.run_salt(arm, 8, 2, 0, v, True, True)
        assert salt == "[spec n8 r2] " and cs == (f"sptc-v{v}" if v else "")
        salt, cs = vb.run_salt(arm, 8, 2, 1, v, True, False)  # fallback, retry attempt
        assert salt == (f"[spec v{v} n8 r2 a1] " if v else "[spec n8 r2 a1] ") and cs == ""
    # the other presets keep their prefixes
    assert vb.run_salt(vb.ARM["fcfs/spec+bad"], 4, 0) == ("[spec d1 n4 r0] ", "")
    assert vb.run_salt(vb.ARM["plugin-untagged/spec"], 1, 0, 0, 1) == ("[spec d0 v1 n1 r0] ", "")
    assert vb.run_salt(vb.ARM["fcfs/spec"], 1, 0, no_salt=True) == ("", "")


def test_cache_salt_check(fake):
    import argparse

    url = fake()
    assert vb.cache_salt_ok(argparse.Namespace(base_url=url, model="m"))
    assert _log(url)[-1]["cache_salt"] == "sptc-check"
    url = fake("--refuse-cache-salt")  # a server without the field: HTTP 400
    assert not vb.cache_salt_ok(argparse.Namespace(base_url=url, model="m"))


def test_salt_names_the_workload_not_the_arm():
    sarms = [vb.ARM[x] for x in ("plugin/spec", "plugin/spec+bad", "plugin-untagged/spec")]
    assert vb.salt_variants(sarms) == {"plugin/spec": 0, "plugin/spec+bad": 0,
                                       "plugin-untagged/spec": 1}
    core = [vb.ARM[x] for x in vb.PRESETS["full"]["arms"]]
    for srv in {x.server for x in core}:  # one server's arms: no clash in the sweep presets
        assert set(vb.salt_variants([x for x in core if x.server == srv]).values()) == {0}


def test_ab_presets_have_two_launches_and_adjacent_stock():
    for name in ("ab", "ab_eager", "prio8"):
        assert vb.PRESETS[name]["rounds"] == 2
    servers = {vb.ARM[x].server for x in vb.PRESETS["prio8"]["arms"]}
    assert servers == {"priority", "fcfs"}
    assert vb.stock_of("fcfs-adj/spec+bad") == "fcfs/spec+bad"


def _proc(tmp_path, serve_cmd: str, url: str, timeout: float = 30.0):
    import argparse

    a = argparse.Namespace(base_url=url, model="m", serve_cmd=serve_cmd, out=str(tmp_path),
                           server_timeout=timeout, server_gap=0.0, cache_fill=True)
    return vb.ServerProc(a, "fcfs")


def test_server_refuses_a_taken_port_and_records_it(fake, tmp_path):
    url = fake()  # a server left over on the port
    srv = _proc(tmp_path, "true", url)
    with pytest.raises(vb.ServerFailed, match="already answers"):
        srv.start()
    assert srv.p is None
    rec = json.loads((tmp_path / "sweep" / "launches.jsonl").read_text())
    assert rec["status"] == "failed" and rec["launch"] == "fcfs#failed"
    assert _proc(tmp_path, "true", url).launches == 0  # failed launches are not numbered


def test_server_start_timeout_terminates_it(tmp_path):
    import shlex
    import sys

    from conftest import free_port

    url = f"http://127.0.0.1:{free_port()}/v1"
    cmd = f"{shlex.quote(sys.executable)} -c 'import time; time.sleep(60)'"
    srv = _proc(tmp_path, cmd, url, timeout=1.0)
    with pytest.raises(vb.ServerFailed, match="not up after"):
        srv.start()
    assert srv.p is None  # terminated: no process left holding the port
    srv2 = _proc(tmp_path, f"{shlex.quote(sys.executable)} -c 'raise SystemExit(3)'", url)
    with pytest.raises(vb.ServerFailed, match="exited"):
        srv2.start()


def test_gpu_state_from_nvidia_smi(tmp_path, monkeypatch):
    smi = tmp_path / "nvidia-smi"
    smi.write_text("#!/bin/sh\ncase \"$3\" in\n"
                   "  *clocks.sm*) echo '1590, 5000, 61, 70.12' ;;\n"
                   "  *clocks_event_reasons*) echo 'Field not valid' >&2; exit 2 ;;\n"
                   "  *) echo '0x0000000000000004' ;;\nesac\n")
    smi.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    monkeypatch.setattr(vb, "GPU_REASONS", list(vb.GPU_REASONS))
    g = vb.gpu_state()
    assert g == {"sm_mhz": 1590.0, "mem_mhz": 5000.0, "temp_c": 61.0, "power_w": 70.12,
                 "reasons": "0x0000000000000004"}
    log = vb.GpuLog()
    log.sample()
    log.sample()
    assert log.result()["sm_mhz_min"] == 1590.0 and log.result()["temp_c_max"] == 61.0
    monkeypatch.setenv("PATH", str(tmp_path / "none"))
    assert vb.gpu_state() is None


# ---- fairer baselines (preset `baselines`, notebook section B4)
def test_bets_only_priority_tags_only_bets():
    assert vb.tag_body("priority_bets", "bet") == {"priority": vb.SPEC_PRIORITY}
    for kind in ("early", "root", "call", "fallback"):
        assert vb.tag_body("priority_bets", kind) == {}
    assert vb.tag_body("priority", "early") == {"priority": vb.SPEC_PRIORITY}


@pytest.mark.parametrize("mode", ["window", "bets"])
def test_proxy_gate_caps_bets(mode):
    g = vb.ProxyGate(f"{mode}:3")
    assert g.enter("root") and g.enter("early")  # certain work is never refused
    assert g.enter("bet")  # window: 2 in flight + 1 <= 3; bets: 0 + 1 <= 3
    if mode == "window":
        assert not g.enter("bet")  # 3 in flight
        g.exit("early")
        assert g.enter("bet")
    else:
        assert g.enter("bet") and g.enter("bet") and not g.enter("bet")
        assert g.enter("call")  # non-bets still pass
    st = g.stats()
    assert st["bets_refused"] == 1 and st["peak_in_flight"] >= 3
    with pytest.raises(ValueError):
        vb.ProxyGate("queue:3")


def test_proxy_refused_bet_is_never_sent(fake):
    url = fake()
    g = vb.ProxyGate("bets:0")
    o = {}
    vb.gated_stream(g, "bet", vb.client(url), "m", "x", 4, o)
    assert vb.outcome(o) == "rejected" and o["stop"] == "proxy_rejected" and not o["times"]
    r = {}
    vb.gated_stream(g, "early", vb.client(url), "m", "y", 4, r)
    assert vb.outcome(r) == "completed" and g.stats()["in_flight_end"] == 0


def test_baselines_preset_plan():
    import argparse

    pre = vb.PRESETS["baselines"]
    assert pre["arms"] == [*vb.BASELINE_ARMS, vb.BASELINE_NOBETS] and pre["same_prompts"]
    assert vb.BASELINE_REF in pre["arms"]
    servers = list(dict.fromkeys(vb.ARM[x].server for x in pre["arms"]))
    assert servers == ["fcfs", "priority", "plugin"] and pre["rounds"] == 2
    assert {vb.ARM[x].decoys for x in vb.BASELINE_ARMS} == {1}
    assert vb.ARM[vb.BASELINE_NOBETS].decoys == 0 and vb.ARM[vb.BASELINE_NOBETS].server == "fcfs"
    a = argparse.Namespace(preset="baselines", arms=None, agents="8", reps=None, turns=None,
                           rounds=None, warm_pass=False, predictions=None)
    p = vb.plan(a)
    assert p["launches"] == 6 and p["runs"] == 18
    assert vb.stock_of("proxy/spec+bad") == "fcfs/spec+bad"


def test_baselines_derived_ratios():
    rows = [{"arm": a, "agents": 8, "reps_ok": 1, "session_p50": v, "root_tpot_p50": 10.0,
             "root_tpot_p99": t} for a, v, t in (("fcfs-b4/spec+bad", 10.0, 20.0),
                                                 ("proxy/spec+bad", 8.0, 15.0),
                                                 ("plugin-b4/spec+bad", 7.0, None))]
    for r in rows:
        r["sub_tokens_per_session"] = 100.0
    rows[1]["sub_tokens_per_session"] = 110.0  # proxy: other completions, more work
    rows.append({"arm": "fcfs-b4/spec", "agents": 8, "reps_ok": 1, "session_p50": 6.4,
                 "root_tpot_p50": 10.0, "root_tpot_p99": 10.0, "sub_tokens_per_session": 100.0})
    dd = vb.derived(rows)
    d = dd["baselines_vs_fcfs"]
    assert d["proxy/spec+bad"][8]["session_p50"] == 0.8
    assert d["proxy/spec+bad"][8]["root_tpot_p99"] == 0.75
    assert d["proxy/spec+bad"][8]["sub_tokens_per_session"] == pytest.approx(1.1)
    assert d["plugin-b4/spec+bad"][8]["root_tpot_p99"] is None
    assert d["fcfs-b4/spec"][8]["session_p50"] == pytest.approx(0.64)
    assert "fcfs-b4/spec+bad" not in d
    nb = dd["baselines_vs_nobets"]
    assert nb["proxy/spec+bad"][8]["session_p50"] == pytest.approx(1.25)
    assert nb["fcfs-b4/spec+bad"][8]["session_p50"] == pytest.approx(10 / 6.4)
    assert "fcfs-b4/spec" not in nb
    for r in rows:
        r.update(decoy_outcomes={"rejected": 3, "completed": 1} if "proxy" in r["arm"] else {},
                 server="fcfs", reps_other={}, sessions=1, session_p99=1.0,
                 sessions_per_min=1.0, goodput=None, preemptions=None, max_waiting=None,
                 client_cpu_util=None, goodput_curve={str(m): None for m in vb.CURVE},
                 prefix_hit_frac=0.25)
    md = vb.summary_md({"slo": {"ref_arm": "x", "k_session": 2, "k_tpot": 2}, "rows": rows,
                        "derived": dd})
    b4 = md.split("## Baselines (B4)")[1].split("##")[0]
    assert "| proxy/spec+bad | 8 | 0.800 | 1.000 | 0.750 | 1.100 | 1.250 | 0.75 | 0.25 |" in b4
    assert "| fcfs-b4/spec+bad | 8 | 1.000 |" in b4 and "| fcfs-b4/spec | 8 | 0.640 |" in b4


# ---- KV pressure and bets that are sometimes needed (preset `pressure`)
def _prereg(name: str) -> dict:
    return json.loads((vb.SIM_ROOT / "results" / name / "predictions.json").read_text())


def test_sptc_bets_tags_only_bets():
    assert vb.tag_body("sptc_bets", "bet") == {vb.TAG_FIELD: {"sptc_class": "bet"}}
    for kind in ("early", "root", "call", "fallback"):
        assert vb.tag_body("sptc_bets", kind) == {}
    assert vb.tag_body("sptc", "early") == {vb.TAG_FIELD: {"sptc_class": "early"}}


def test_pressure_servers_are_the_preregistered_configs():
    """KV blocks and sequence slots as server flags, --max-model-len in
    PRESSURE_SERVE_CMD: together the flags of results/prereg_v4 (chosen) and
    prereg_v4_fallback. The pressure servers share fcfs's compiled artifact."""
    for config, name in (("chosen", "prereg_v4"), ("fallback", "prereg_v4_fallback")):
        p = _prereg(name)["config"]
        assert p["role"] == config
        assert vb.pressure_flags(config) + ["--max-model-len", str(vb.PRESSURE_MAX_LEN)] \
            == p["flags"].split()
        servers = vb.pressure_servers(config)
        assert tuple(servers) == vb.PRESSURE_SERVERS
        for name, spec in servers.items():
            base = vb.SERVERS[name.removesuffix("_p")]
            assert spec == {"flags": base["flags"] + vb.pressure_flags(config),
                            "env": base["env"]}
            assert vb.compile_group(spec["flags"]) == vb.compile_group(base["flags"])
    assert f"--max-model-len {vb.PRESSURE_MAX_LEN} " in vb.PRESSURE_SERVE_CMD
    assert {k: vb.SERVERS[k] for k in vb.PRESSURE_SERVERS} == vb.pressure_servers("chosen")
    assert vb.ALLOWANCE["plugin_p"] == "fixed" and vb.ALLOWANCE["fcfs_p"] is None


def test_pressure_arms_are_the_preregistered_ones():
    """The pressure preset runs prereg_v4's arms as it lists them; the speculative calls
    are bets in workload both only. Step 5 (both_default) runs the same arms on the
    default servers."""
    arms = _prereg("prereg_v4")["arms"]
    assert vb.PRESETS["pressure"]["arms"] == vb.PRESSURE_ARMS == list(arms)
    for name, want in arms.items():
        x = vb.ARM[name]
        assert (x.server, x.mode, x.decoys, x.tags, x.gate or None) == (
            want["server"], want["mode"], want["decoys"], want["tags"], want["gate"])
        assert x.spec_kind == ("bet" if want["workload"] == "both" else "early")
    pre = vb.PRESETS["pressure"]
    assert (pre["agents"], pre["reps"], pre["rounds"], pre["warm_pass"],
            pre["same_prompts"]) == ("4", 3, 2, True, True)
    assert vb.PRESETS["probe"]["arms"] == ["fcfs-p/spec", vb.PRESSURE_REF]
    assert vb.PRESETS["both_default"]["arms"] == vb.BOTH_DEFAULT_ARMS
    for name in vb.BOTH_DEFAULT_ARMS:
        x, y = vb.ARM[name], vb.ARM[name.replace("-d/", "-p/")]
        assert x.server == y.server.removesuffix("_p")
        assert (x.mode, x.decoys, x.tags, x.gate, x.spec_kind) == (
            y.mode, y.decoys, y.tags, y.gate, y.spec_kind)
    assert {a for wl in vb.D1_ARMS.values() for a in wl} <= set(vb.ARM)


def test_pressure_preset_plan():
    import argparse

    def plan(preset, pred):
        a = argparse.Namespace(preset=preset, arms=None, agents=None, reps=None, turns=None,
                               rounds=None, warm_pass=False, predictions=pred)
        return vb.plan(a)

    p = plan("pressure", str(vb.SIM_ROOT / "results" / "prereg_v4" / "predictions.json"))
    assert (p["runs"], p["launches"], p["cache_fill_launches_max"]) == (27, 6, 1)
    assert p["source"] == "simulator predictions" and 45 <= p["est_minutes"] <= 65
    assert plan("probe", None)["launches"] == 1
    assert plan("both_default", None)["runs"] == 18


@pytest.fixture
def rejected(monkeypatch):
    """spec-ptc's SpeculationRejected; a stand-in where the installed spec-ptc has no
    sptc-hints patch (these tests need no spec-ptc)."""
    try:
        from spec_ptc.contracts.hints import SpeculationRejected
        return SpeculationRejected
    except ImportError:
        pass

    class SpeculationRejected(RuntimeError):
        def __init__(self, reason=None):
            super().__init__(reason)
            self.reason = reason

    mod = types.ModuleType("spec_ptc.contracts.hints")
    mod.SpeculationRejected = SpeculationRejected
    monkeypatch.setitem(sys.modules, "spec_ptc.contracts.hints", mod)
    return SpeculationRejected


def _engine(url: str, spec_kind: str, tags: str = "sptc_bets", decoys: int = 1):
    """LoggedEngine on a stand-in SuiteEngine: returns (the tool's call, engine, log)."""
    log: list = []
    base = types.SimpleNamespace(sub_max_tokens=12)
    eng = vb.LoggedEngine(base, vb.client(url), "m", False, decoys, tags, log, natural=True,
                          spec_kind=spec_kind)
    return base._call, eng, log


def test_refused_bet_reruns_once_at_its_claim(fake, rejected):
    """spec_kind bet: a refused speculative call raises SpeculationRejected (no run for
    real inside the speculation); the program's next call of that prompt, its claim, runs
    it untagged and is logged as fallback at_claim; a later one is a normal call."""
    url = fake("--scheduler-cls", "sptc_vllm.scheduler.SptcScheduler",
               "--additional-config", json.dumps({"sptc": {"free_window": 0}}))
    call, eng, log = _engine(url, "bet")
    with pytest.raises(rejected):
        call("q1", types.SimpleNamespace(state="running"))
    assert [(c["kind"], c["outcome"], c.get("refused")) for c in log] == [
        ("bet", "rejected", True)]
    assert call("q1").startswith("x")
    call("q1")
    assert [(c["kind"], c.get("at_claim"), c["outcome"]) for c in log[1:]] == [
        ("fallback", True, "completed"), ("call", None, "completed")]
    assert [d["outcome"] for d in eng.end_turn()] == ["rejected"]  # its decoy, a bet too
    reqs = sorted((r["prompt_head"], r["rid"], r["vllm_xargs"], r["outcome"])
                  for r in _log(url))
    assert [(p, x, o) for p, _, x, o in reqs] == [
        ("q1", {"sptc_class": "bet"}, "sptc_bet_rejected"), ("q1", None, "stop"),
        ("q1", None, "stop"), ("q1 [alt 0]", {"sptc_class": "bet"}, "sptc_bet_rejected")]
    assert len({c["prompt_id"] for c in log}) == 1


def test_a_call_bet_on_twice_reruns_once_or_not_at_all(fake, rejected):
    """spec-ptc bets again on a call whose bet failed (a re-peek): still one run for real
    at its claim; and none if its last bet completed (the claim takes that one)."""
    url = fake("--scheduler-cls", "sptc_vllm.scheduler.SptcScheduler",
               "--additional-config", json.dumps({"sptc": {"free_window": 1}}))
    call, eng, log = _engine(url, "bet", decoys=0)
    spec = types.SimpleNamespace(state="running")
    ths = _busy(url, 1)  # the window of 1 is full: every bet is refused
    for _ in range(2):
        with pytest.raises(rejected):
            call("q3", spec)
    with pytest.raises(rejected):
        call("q4", spec)
    for t in ths:
        t.join()
    assert call("q4", spec).startswith("x")  # the window is free again: admitted
    call("q3")
    call("q3")
    call("q4")
    assert [(c["kind"], c["outcome"], c.get("at_claim")) for c in log] == [
        ("bet", "rejected", None), ("bet", "rejected", None), ("bet", "rejected", None),
        ("bet", "completed", None), ("fallback", "completed", True), ("call", "completed", None),
        ("call", "completed", None)]
    assert not eng.refused_bets


def test_early_refusal_keeps_the_immediate_fallback(fake):
    """spec_kind early (every arm before the pressure run): a speculative call that fails is run
    for real at once, inside the speculation, which returns its result; no spec-ptc
    hints needed."""
    url = fake("--fail-once", "q2")  # no tokens, no finish: logged as rejected
    call, eng, log = _engine(url, "early", tags="sptc", decoys=0)
    assert eng.rejected is None
    assert call("q2", types.SimpleNamespace(state="running")).startswith("x")
    assert [(c["kind"], c["outcome"], c.get("refused"), c.get("at_claim")) for c in log] == [
        ("early", "rejected", True, None), ("fallback", "completed", None, None)]
    assert not eng.refused_bets and [r["vllm_xargs"] for r in _log(url)] == [
        {"sptc_class": "early"}, None]
    with pytest.raises(ValueError):
        _engine(url, "late")


def test_metrics_poller_queue_share():
    texts = iter(["vllm:num_requests_waiting 0\n", "vllm:num_requests_waiting 2\n", "x 1\n",
                  "vllm:num_requests_waiting 0\n"])
    m = vb.MetricsPoller(types.SimpleNamespace(get=lambda path, timeout=3.0: next(texts)))
    for _ in range(4):
        m.sample()
    r = m.result()
    assert r["max_waiting"] == 2.0 and r["waiting_frac"] == pytest.approx(1 / 3)


def test_check_pressure_serve_cmd_and_one_config_per_out(tmp_path):
    import argparse

    def ns(serve_cmd=vb.PRESSURE_SERVE_CMD, config="chosen", launch=True):
        return argparse.Namespace(launch=launch, serve_cmd=serve_cmd, pressure_config=config)

    (tmp_path / "sweep").mkdir()
    vb.check_pressure(ns("vllm serve {model}"), ["fcfs", "priority"], tmp_path)
    assert not (tmp_path / "sweep" / "pressure.json").exists()  # no pressure server
    for bad in ("vllm serve {model} --port {port}",
                "vllm serve {model} --max-model-len 512 --max-model-len 8192"):
        with pytest.raises(SystemExit, match="need --max-model-len 512"):
            vb.check_pressure(ns(bad), ["fcfs_p"], tmp_path)
    vb.check_pressure(ns("vllm serve {model} --max-model-len=512"), ["fcfs_p"], tmp_path)
    rec = json.loads((tmp_path / "sweep" / "pressure.json").read_text())
    assert rec == {"config": "chosen", "flags": vb.pressure_flags("chosen"),
                   "max_model_len": 512}
    vb.check_pressure(ns(), ["plugin_p"], tmp_path)  # the same config again
    with pytest.raises(SystemExit, match="chosen pressure config, not fallback"):
        vb.check_pressure(ns("", "fallback", launch=False), ["fcfs_p"], tmp_path)


def test_probe_verdict(tmp_path):
    def run(arm, pre, wait, status="ok"):
        vb.save_run(vb.run_file(tmp_path, arm, 4, 0), {
            "arm": arm, "agents": 4, "status": status, "sessions": [],
            "server_metrics": {"preemptions": pre, "max_waiting": wait, "max_kv": 0.6,
                               "waiting_frac": 0.0, "max_running": 9.0}})

    assert vb.probe_verdict(tmp_path)["config"] is None  # nothing ran
    run("fcfs-p/spec", 0.0, 0.0)
    run("fcfs-p/spec+bad", 0.0, 0.0)
    v = vb.probe_verdict(tmp_path)
    assert (v["pressure"], v["config"]) == (False, "fallback")
    assert v["arms"]["fcfs-p/spec"]["max_kv"] == 0.6
    run("fcfs-p/spec+bad", 0.0, 3.0)  # a queue alone is pressure
    assert vb.probe_verdict(tmp_path)["config"] == "chosen"
    run("fcfs-p/spec+bad", 5.0, 0.0)
    assert vb.probe_verdict(tmp_path)["config"] == "chosen"
    run("fcfs-p/spec+bad", None, None)  # /metrics not read
    assert vb.probe_verdict(tmp_path)["config"] is None
    run("fcfs-p/spec+bad", 5.0, 1.0, status="error")
    assert vb.probe_verdict(tmp_path)["config"] is None


def _pses(wall, real=(), reissued=0, stopped=False, decoys=(), bet_calls=None):
    s = {**_ses("a", wall, 20.0, decoys), "real_bets": [{"outcome": o} for o in real],
         "reissued": reissued, "shadow_stopped": stopped}
    return s if bet_calls is None else {**s, "real_bet_calls": bet_calls}


def _prun(arm, wall, pre=0.0, queue=0.0, **kw):
    r = _run(arm, 4, 0, [_pses(wall, **kw)])
    r["server_metrics"] = {"preemptions": pre, "max_waiting": 3.0 if queue else 0.0,
                           "max_kv": 0.9, "waiting_frac": queue}
    return r


def test_pressure_table_and_decision_rule():
    runs = [_prun("fcfs-p/spec+bad", 5.0, pre=40.0, queue=0.3, decoys=["completed"]),
            _prun("fcfs-p/spec", 3.5),
            _prun("cap-p/spec+bad", 3.7, decoys=["rejected"]),
            _prun("plugin-p/spec+bad", 3.6, decoys=["rejected"]),
            _prun("prio-p/spec+bad", 4.9, decoys=["completed"]),
            _prun("cap-p/both", 7.0, real=["rejected", "completed"], reissued=1, stopped=True,
                  decoys=["rejected", "completed"], bet_calls=1),
            _prun("plugin-p/both", 6.0, real=["rejected", "dropped"], reissued=2,
                  stopped=True, decoys=["rejected", "rejected"]),
            _prun("prio-p/both", 4.9, real=["completed"], decoys=["completed"])]
    s = vb.summarize(runs, boot=0)
    row = {r["arm"]: r for r in s["rows"]}
    assert row["plugin-p/both"]["real_bet_outcomes"] == {"rejected": 1, "dropped": 1}
    assert (row["plugin-p/both"]["reissued"], row["plugin-p/both"]["shadow_stops"]) == (2, 1)
    assert (row["plugin-p/both"]["real_bet_calls"], row["cap-p/both"]["real_bet_calls"]) == (2, 1)
    assert row["fcfs-p/spec+bad"]["waiting_frac"] == 0.3
    d = s["derived"]
    assert d["pressure_vs_ref"]["cap-p/both"][4]["session_p50"] == pytest.approx(1.4)
    assert "fcfs-d/spec+bad" not in d["pressure_vs_ref"]  # not run
    x = d["d1"]
    assert x["by_workload"]["decoys"]["plugin_vs_cap"] == pytest.approx(3.6 / 3.7)  # 0.973
    assert x["by_workload"]["both"]["plugin_vs_cap"] == pytest.approx(6 / 7)  # 0.857: <= 0.95
    assert x["by_workload"]["both, default servers"]["plugin_vs_cap"] is None
    assert x["pressure"]["fcfs-p/spec+bad"] == {"preemptions": 40.0, "queue_frac": 0.3}
    assert (x["pressure_check"], x["won_in"], x["plugin_wins"]) == (True, ["both"], True)
    md = vb.summary_md(s)
    table = md.split("## Pressure")[1].split("## Baselines")[0]
    assert ("| plugin-p/both | 4 | 1.200 | 1.200 | 1.000 | 1.000 | 1.00 / 0.00 | 0.50 / 0.50 "
            "| 1.00 | 2 | 1/1 | 0.0 | 0 | 0% | 0.90 |") in table
    assert "| cap-p/both | 4 | 1.400 | 1.400 | 1.000 | 1.000 | 0.50 / 0.00 | 0.50 / 0.00 | 2.00 |" \
        in table
    assert ("| fcfs-p/spec+bad | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 | - | - | 0 | "
            "0/1 | 40.0 | 3 | 30% | 0.90 |") in table
    assert "**plugin wins: yes** (in both)" in table
    # the pressure check: fcfs-p/spec queues too, or fcfs-p/spec+bad barely does
    runs[1] = _prun("fcfs-p/spec", 3.5, queue=0.1)
    assert vb.summarize(runs, boot=0)["derived"]["d1"]["plugin_wins"] is False
    runs[1] = _prun("fcfs-p/spec", 3.5)
    runs[0] = _prun("fcfs-p/spec+bad", 5.0, pre=8.0, queue=0.2)
    x = vb.summarize(runs, boot=0)["derived"]["d1"]
    assert x["pressure_check"] is False and x["plugin_wins"] is False
    # no verdict while a workload's rows are missing, unless the other shows the win
    runs[0] = _prun("fcfs-p/spec+bad", 5.0, pre=40.0, queue=0.3)
    x = vb.summarize(runs[:5], boot=0)["derived"]["d1"]
    assert x["pressure_check"] is True and x["by_workload"]["both"]["plugin_vs_cap"] is None
    assert x["plugin_wins"] is None
    runs[3] = _prun("plugin-p/spec+bad", 3.0)  # 0.81 of the cap in decoys
    x = vb.summarize(runs[:5], boot=0)["derived"]["d1"]
    assert (x["won_in"], x["plugin_wins"]) == (["decoys"], True)
    assert vb.pressure_md({"rows": [], "derived": vb.derived([])}) == []
