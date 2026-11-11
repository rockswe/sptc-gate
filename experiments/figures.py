"""Figures and markdown tables for docs/report.md from the results/ CSVs.

  .venv/bin/python experiments/figures.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sptc_sim import plots

RES = Path(__file__).resolve().parents[1] / "results"
MAIN = ["baseline", "literal", "shadow", "dataflow"]
WASTE = ["baseline", "shadow", "shadow+waste0.5", "shadow+waste1"]
SCHEDS = ["fcfs", "agent-naive", "agent-naive-open", "agent"]
METRICS = (("lat_p50", "p50 session latency (s)", 1, "{:.1f}"),
           ("lat_p99", "p99 session latency (s)", 1, "{:.1f}"),
           ("root_tpot_p99", "root TPOT p99 (ms)", 1000, "{:.1f}"),
           ("root_ttft_p99", "root TTFT p99 (s)", 1, "{:.2f}"),
           ("sub_ttft_p99", "sub-call TTFT p99, claimed calls (s)", 1, "{:.2f}"),
           ("wasted_frac", "wasted share of model tokens", 1, "{:.3f}"),
           ("reissued", "suppressed bets re-issued because they were needed", 1, "{:.0f}"),
           ("busy", "GPU busy fraction (not spare capacity)", 1, "{:.2f}"),
           ("drift", "drift: mean latency of last third / first third of sessions "
            "(>1.2: not a steady state)", 1, "{:.2f}"))


def base_of(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df.policy == "baseline") & (df.sched == "fcfs")]


def table(df: pd.DataFrame, metric: str, sched: str, policies, scale=1.0, fmt="{:.1f}") -> str:
    rates = sorted(df.rate.unique())
    lines = ["| rate (sessions/s) | " + " | ".join(policies) + " |",
             "|" + "---|" * (len(policies) + 1)]
    for r in rates:
        cells = []
        for p in policies:
            src = "fcfs" if p == "baseline" else sched
            g = df[(df.rate == r) & (df.policy == p) & (df.sched == src)][metric]
            cells.append(fmt.format(g.median() * scale) if len(g) else "-")
        lines.append(f"| {r:g} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def paired(df: pd.DataFrame, base: pd.DataFrame, metric: str, policy: str, sched: str) -> str:
    """Per-seed ratio policy / no-speculation FCFS (same arrivals and outputs)."""
    out = [f"| rate | {policy} ({sched}) / no-speculation FCFS, {metric}: median [min-max] "
           "over seeds | drift |", "|---|---|---|"]
    for r in sorted(df.rate.unique()):
        b = base[base.rate == r].set_index("seed")[metric]
        g = df[(df.rate == r) & (df.policy == policy) & (df.sched == sched)].set_index("seed")
        x = (g[metric] / b).dropna()
        if len(x):
            out.append(f"| {r:g} | {x.median():.2f} [{x.min():.2f}-{x.max():.2f}] | "
                       f"{g['drift'].median():.2f} |")
    return "\n".join(out)


def section(md: list, name: str, label: str, base_from: str | None = None) -> None:
    path = RES / f"{name}.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    base = base_of(df)
    if base.empty and base_from and (RES / f"{base_from}.csv").exists():
        other = pd.read_csv(RES / f"{base_from}.csv")
        base = base_of(other)
        df = pd.concat([df, base, other[other.policy.isin(["shadow", "shadow+waste1"])]])
    pols = [p for p in dict.fromkeys(MAIN + WASTE + sorted(set(df.policy)))
            if p in set(df.policy)]
    scheds = [s for s in SCHEDS if s in set(df.sched)]
    md.append(f"## {label} (`results/{name}.csv`)\n")
    for metric, title, sc, fmt in METRICS:
        for sched in scheds:
            md.append(f"### {title}, {sched}\n")
            md.append(table(df, metric, sched, pols, sc, fmt) + "\n")
    for pol in [p for p in pols if p != "baseline"]:
        for sched in scheds:
            for m in ("lat_p50", "lat_p99"):
                md.append(f"### paired {m}: {pol}, {sched}\n")
                md.append(paired(df, base, m, pol, sched) + "\n")


def main() -> None:
    md = []
    for f in (plots.calibration, plots.stepcost, plots.marginal, plots.sweep):
        f(RES)
    for name in ("clog_eager", "clog_graphs", "clog_moe"):
        if not (RES / f"{name}.csv").exists():
            continue
        df = pd.read_csv(RES / f"{name}.csv")
        have = set(df.policy)
        scheds = tuple(s for s in ("fcfs", "agent-naive", "agent") if s in set(df.sched))
        plots.load_sweep(RES, f"{name}.csv", "lat_p99", "p99 session latency (s)",
                         "p99 session latency", f"fig_{name}_p99.png",
                         [p for p in MAIN if p in have], scheds=("fcfs",))
        plots.load_sweep(RES, f"{name}.csv", "lat_p50", "p50 session latency (s)",
                         "Wasted speculation", f"fig_{name}_waste.png",
                         [p for p in WASTE if p in have], scheds=scheds)
        plots.load_sweep(RES, f"{name}.csv", "root_tpot_p99", "root-model TPOT p99 (ms)",
                         "Root TPOT p99", f"fig_{name}_tpot.png",
                         [p for p in WASTE if p in have], scale=1000, scheds=scheds)
    section(md, "clog_eager", "H100, Qwen3-4B, eager (calibrated)")
    section(md, "clog_eager_noise", "Confidence-aware scheduler with mislabeled bets",
            base_from="clog_eager")
    section(md, "clog_eager_hiseq", "Sensitivity: per-sequence overhead 0.25 ms")
    section(md, "clog_eager_batched", "Programs that already batch their fan-out")
    section(md, "clog_graphs", "H100, Qwen3-4B, CUDA graphs")
    section(md, "clog_moe", "H100, Qwen3-30B-A3B, CUDA graphs")
    kv = RES / "kv_rtx4090.csv"
    if kv.exists():
        df = pd.read_csv(kv)
        md.append("## RTX 4090, Qwen3-4B: KV retention across tool gaps "
                  "(`results/kv_rtx4090.csv`)\n")
        for metric, name, fmt in (("lat_p50", "p50 session latency (s)", "{:.1f}"),
                                  ("lat_p99", "p99 session latency (s)", "{:.1f}"),
                                  ("root_cache_hit", "root prefix-cache hit rate", "{:.2f}"),
                                  ("root_ttft_p99", "root TTFT p99 (s)", "{:.2f}"),
                                  ("preemptions", "preemptions", "{:.0f}"),
                                  ("drift", "drift", "{:.2f}")):
            md.append(f"### {name}\n")
            rows = ["| rate | policy | lru | pin (5 s TTL) | none |", "|---|---|---|---|---|"]
            for r in sorted(df.rate.unique()):
                for p in ("baseline", "shadow", "shadow+waste1"):
                    cells = [fmt.format(df[(df.rate == r) & (df.policy == p) & (df.kv == k)]
                                        [metric].median()) for k in ("lru", "pin", "none")]
                    rows.append(f"| {r:g} | {p} | " + " | ".join(cells) + " |")
            md.append("\n".join(rows) + "\n")
    (RES / "tables.md").write_text("\n".join(md))
    print(f"wrote {RES / 'tables.md'}")


if __name__ == "__main__":
    main()
