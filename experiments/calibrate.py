"""Validation layer 2: reproduce spec-ptc's 22 measured medians (runs.csv).

See sptc_sim/calib.py for the method. Writes results/calibration.json and
results/calibration.md.

  .venv/bin/python experiments/calibrate.py
"""

from __future__ import annotations

import itertools
import json
import math
import statistics
from pathlib import Path

from sptc_sim import calib, suite
from sptc_sim.hardware import Overheads

OUT = Path(__file__).resolve().parents[1] / "results"
# t_per_seq = 0 is a physical floor; the other axes extend past the optimum
GRID_T_FIXED = [0.010, 0.012, 0.014]
GRID_T_SEQ = [0.0, 0.00002, 0.0001, 0.00025]
GRID_ADMIT = [0.002, 0.004, 0.006, 0.008]
GRID_CLIENT = [0.001, 0.002, 0.004, 0.008]


def pooled_sigma(df) -> float:
    """Per-call output-length noise from rep-to-rep spread of BASELINE exec
    time: CV(sum of n iid calls) = CV(call)/sqrt(n). Median across patterns."""
    pats = suite.patterns()
    vals = []
    for name, g in df[df["mode"] == "baseline"].groupby("pattern"):
        n = pats[name].n_expected_calls or 1
        x = g["exec_s"]
        if x.mean() > 0:
            vals.append(x.std() / x.mean() * math.sqrt(n))
    return statistics.median(vals)


def render(names, loo, best, sigma, insample) -> str:
    lines = [
        "| pattern | baseline meas (s) | baseline sim | spec meas (s) [min-max of 5] | "
        "spec sim (LOO) | err | in range | speedup meas | speedup sim |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    errs, inside = [], 0
    for n in names:
        r = loo[n]
        e = (r["spec_wall_sim"] - r["spec_wall_meas"]) / r["spec_wall_meas"]
        errs.append(abs(e))
        ok = 0.99 * r["spec_wall_min"] <= r["spec_wall_sim"] <= 1.01 * r["spec_wall_max"]
        inside += ok
        lines.append(
            f"| {n} | {r['base_wall_meas']:.2f} | {r['base_wall_sim']:.2f} | "
            f"{r['spec_wall_meas']:.2f} [{r['spec_wall_min']:.2f}-{r['spec_wall_max']:.2f}] | "
            f"{r['spec_wall_sim']:.2f} | {100 * e:+.1f}% | {'yes' if ok else 'no'} | "
            f"{r['base_wall_meas'] / r['spec_wall_meas']:.2f}x | "
            f"{r['base_wall_sim'] / r['spec_wall_sim']:.2f}x |"
        )
    ins = [abs(insample[n]["spec_wall_sim"] / insample[n]["spec_wall_meas"] - 1) for n in names]
    # patterns whose speculative wall is pinned to the scripted stream test little of
    # the server; score the rest separately
    srv = [n for n in names if loo[n]["spec_wall_meas"] > 1.10 * loo[n]["stream_meas"]]
    srv_err = [abs(loo[n]["spec_wall_sim"] / loo[n]["spec_wall_meas"] - 1) for n in srv]
    summary = (
        f"\nSpeculative wall time, leave-one-pattern-out: median |error| "
        f"{100 * statistics.median(errs):.1f}%, mean {100 * statistics.mean(errs):.1f}%, "
        f"max {100 * max(errs):.1f}%; {sum(e <= 0.055 for e in errs)}/22 within 5.5%; "
        f"{inside}/22 inside the measured min-max of 5 reps (1% tolerance).\n"
        f"Server-sensitive subset ({len(srv)} patterns whose speculative wall exceeds the "
        f"stream by >10%): LOO median |error| {100 * statistics.median(srv_err):.1f}%, "
        f"mean {100 * statistics.mean(srv_err):.1f}%; "
        f"{sum(e <= 0.055 for e in srv_err)}/{len(srv)} within 5.5%.\n"
        f"In-sample (one set of overheads for all 22): median |error| "
        f"{100 * statistics.median(ins):.1f}%, mean {100 * statistics.mean(ins):.1f}%; "
        f"{sum(e <= 0.055 for e in ins)}/22 within 5.5%.\n"
        f"Best global overheads: t_fixed={best[0]}, t_per_seq={best[1]}, "
        f"t_admit={best[2]}, client_s={best[3]}; per-call output sigma={sigma:.3f} "
        f"(from baseline spread).\n"
    )
    return "\n".join(lines) + "\n" + summary


def main() -> None:
    import sys

    if "--render" in sys.argv:
        cal = json.loads((OUT / "calibration.json").read_text())
        names = sorted(cal["loo"])
        md = render(names, cal["loo"], cal["best_params"], cal["sigma"], cal["best"])
        (OUT / "calibration.md").write_text(md)
        print(md)
        return
    df = suite.runs()
    meas = suite.measured_medians()
    names = sorted(meas.pattern.unique())
    sigma = pooled_sigma(df)
    print(f"pooled per-call sigma from baseline spread: {sigma:.3f}", flush=True)
    get = lambda n, m, col: float(meas[(meas.pattern == n) & (meas["mode"] == m)][col].iloc[0])

    table = {}  # (tf, ts, cl) -> {name: row}
    for tf, ts, ta, cl in itertools.product(GRID_T_FIXED, GRID_T_SEQ, GRID_ADMIT, GRID_CLIENT):
        cost = calib.default_cost(Overheads(t_fixed=tf, t_per_seq=ts, t_admit=ta, client_s=cl))
        rows = {}
        for n in names:
            stream_m = get(n, "baseline", "stream_med")
            scale, got = calib.fit_scale(n, cost, sigma, get(n, "baseline", "exec_med"))
            base = calib.simulate(n, "baseline", cost, scale, sigma)
            spec = calib.simulate(n, "shadow", cost, scale, sigma)
            rows[n] = {
                "scale": scale,
                "base_wall_sim": calib.med(base, "wall"),
                "base_wall_meas": get(n, "baseline", "wall_med"),
                "spec_wall_sim": calib.med(spec, "wall"),
                "spec_wall_meas": get(n, "spec", "wall_med"),
                "spec_call_sim": calib.med(spec, "call_med"),
                "spec_call_meas": get(n, "spec", "call_med"),
                "stream_meas": stream_m,
                "spec_wall_min": float(df[(df.pattern == n) & (df["mode"] == "spec")].wall_s.min()),
                "spec_wall_max": float(df[(df.pattern == n) & (df["mode"] == "spec")].wall_s.max()),
            }
        err = statistics.mean(
            abs(math.log(r["spec_wall_sim"] / r["spec_wall_meas"])) for r in rows.values()
        )
        print(f"t_fixed={tf:.3f} t_seq={ts:.5f} t_admit={ta:.3f} client={cl:.3f}  "
              f"mean|log err| spec={err:.4f}", flush=True)
        table[(tf, ts, ta, cl)] = rows

    # leave-one-pattern-out choice of the global overheads
    loo = {}
    for n in names:
        def score(k):
            return statistics.mean(
                abs(math.log(r["spec_wall_sim"] / r["spec_wall_meas"]))
                for m, r in table[k].items() if m != n
            )
        k = min(table, key=score)
        loo[n] = {"params": k, **table[k][n]}
    best = min(table, key=lambda k: statistics.mean(
        abs(math.log(r["spec_wall_sim"] / r["spec_wall_meas"])) for r in table[k].values()))

    OUT.mkdir(exist_ok=True)
    json.dump({
        "sigma": sigma,
        "best_params": best,
        "best": table[best],
        "loo": {n: {**v, "params": list(v["params"])} for n, v in loo.items()},
        "grid": {str(k): v for k, v in table.items()},
    }, open(OUT / "calibration.json", "w"), indent=1)

    md = render(names, loo, best, sigma, table[best])
    (OUT / "calibration.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
