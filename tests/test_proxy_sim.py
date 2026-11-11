"""experiments/sweep_predict.ProxySim: the client-side cap on bets (vllm_bench.ProxyGate) as
the simulator predicts it (results/prereg_v3, section B4)."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import sweep_predict as w2  # noqa: E402

from sptc_sim.des import Sim  # noqa: E402


def _h(sim, rid, done=False):
    ev = sim.event()
    if done:
        ev.succeed(None)
    return SimpleNamespace(done=ev, info=SimpleNamespace(rid=rid))


def test_window_counts_calls_in_flight_and_roots_at_the_server():
    sim = Sim()
    srv = SimpleNamespace(running=[SimpleNamespace(kind="root")] * 2,
                          waiting=[SimpleNamespace(kind="sub")])
    p = w2.ProxySim(srv, "window:4")
    p.live = [_h(sim, "a"), _h(sim, "b", done=True)]
    assert p.admit_bet()  # 1 call + 2 roots + 1 <= 4 (the waiting sub is a live call already)
    p.live.append(_h(sim, "c~decoy"))
    assert not p.admit_bet()  # 2 calls + 2 roots + 1 > 4
    assert (p.sent, p.refused) == (1, 1)


def test_semaphore_counts_decoys_in_flight_only():
    sim = Sim()
    srv = SimpleNamespace(running=[SimpleNamespace(kind="root")] * 8, waiting=[])
    p = w2.ProxySim(srv, "bets:2")
    p.live = [_h(sim, "x~decoy"), _h(sim, "y"), _h(sim, "z~decoy", done=True)]
    assert p.admit_bet()
    p.live.append(_h(sim, "w~decoy"))
    assert not p.admit_bet()
