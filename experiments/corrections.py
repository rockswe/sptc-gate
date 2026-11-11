"""Re-run the report headline cells under the corrected KV model, one fix at a time.

The fixes (from the audit; ServerConfig / run_session options, sptc_sim/server.py):
  full_isl     #32  vLLM 0.32 admits a waiting request only if its whole sequence fits
  resume       #17  a preempted request finds its own blocks in the prefix cache again
  lru_queue    #18  freed full blocks of every request join one LRU queue
  shared_sys   #44  sessions of one program share their system prompt's cached blocks
  gate_sched   #45  (agent cells) bets gated in the waiting loop, not at submit

Variants: legacy (the simulator every number in the report came from), legacy plus one fix,
all fixes, all minus one fix, and all with one system prompt for every session
(sensitivity). Every cell is paired: same arrivals, programs and outputs.
all-shared_sys is the corrected model on the report's own workload (vLLM 0.32 KV semantics,
a private system prompt per session) and is clog.py's default; "all" also lets sessions of
one program share their system prompt, which is a workload assumption.

  PYTHONHASHSEED=0 python experiments/corrections.py run --group rtx4090 --procs 2
  python experiments/corrections.py report        # results/corrections/tables.md
  python experiments/corrections.py check-legacy  # legacy reproduces committed cells

Rows go to results/corrections/runs.csv (resumable: cells already there are skipped).
Runs are independent of PYTHONHASHSEED since trace.py forces reads in sorted order (before,
some agent-policy cells moved by up to 1.4% between processes).
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import statistics
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clog  # noqa: E402

from sptc_sim.server import LEGACY_KV  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "corrections"
RUNS = OUT / "runs.csv"

FIX_KV = {"full_isl": "full_isl", "resume": "resume_from_cache", "lru_queue": "cache_freed_blocks"}
FIXES = ["full_isl", "resume", "lru_queue", "shared_sys"]


def variant(on: set[str], sys_all: bool = False) -> dict:
    kv = {v: k in on for k, v in FIX_KV.items()}
    share = "all" if sys_all else ("program" if "shared_sys" in on else "session")
    return {"kv": kv, "sys_share": share}


VARIANTS = {"legacy": variant(set()), "all": variant(set(FIXES)),
            "all+sys_all": variant(set(FIXES), sys_all=True)}
VARIANTS["all+gate_sched"] = {"kv": {**VARIANTS["all"]["kv"], "bet_gate": "schedule"},
                              "sys_share": "program"}
for f in FIXES:
    VARIANTS[f"+{f}"] = variant({f})
    VARIANTS[f"all-{f}"] = variant(set(FIXES) - {f})
assert VARIANTS["legacy"] == {"kv": LEGACY_KV, "sys_share": "session"} == clog.LEGACY

# (config, policy, sched, rate, mix, kv)
CELLS = {
    "rtx4090": [("rtx4090", p, "fcfs", 0.14, "serial", kv)
                for p in ("baseline", "shadow", "shadow+waste1") for kv in ("lru", "pin", "none")],
    # the 4090 load ladder for the cells report §4.5 states as ranges or "highest load"
    "rtx4090_rates": [("rtx4090", p, "fcfs", r, "serial", kv)
                      for r in (0.02, 0.05, 0.08, 0.11) for p, kv in (
                          ("baseline", "lru"), ("baseline", "none"), ("shadow", "lru"),
                          ("shadow", "none"), ("shadow+waste1", "lru"))],
    # past the report's highest 4090 load: does the corrected model still turn waste into
    # a loss, only later, and is that loss in steady state (drift <= 1.2)?
    "rtx4090_high": [("rtx4090", p, "fcfs", r, "serial", "lru")
                     for r in (0.15, 0.16, 0.17, 0.20)
                     for p in ("baseline", "shadow", "shadow+waste1")],
    "h100": (
        [("graphs", p, s, 0.8, "serial", "lru") for p, s in (
            ("baseline", "fcfs"), ("shadow", "fcfs"), ("shadow+waste1", "fcfs"),
            ("shadow+waste1", "agent"))]
        + [("eager", p, s, r, "serial", "lru") for r, p, s in (
            (0.8, "baseline", "fcfs"), (0.8, "shadow", "fcfs"), (0.8, "shadow+waste1", "fcfs"),
            (0.8, "shadow", "agent"), (0.8, "shadow+waste1", "agent"),
            (0.8, "shadow+waste1+noise0.2", "agent"), (0.8, "shadow+waste1+noise0.4", "agent"),
            (0.4, "baseline", "fcfs"), (0.4, "shadow+waste1", "fcfs"),
            (0.4, "shadow+waste1", "agent"))]
        + [("eager", p, s, r, "batched", "lru") for r in (0.6, 0.8) for p, s in (
            ("baseline", "fcfs"), ("shadow+waste1", "fcfs"), ("shadow+waste1", "agent"))]
        + [("moe", p, s, 0.4, "serial", "lru") for p, s in (
            ("baseline", "fcfs"), ("shadow", "fcfs"), ("shadow+waste1", "fcfs"),
            ("shadow+waste1", "agent"))]),
}
GROUP_VARIANTS = {
    "rtx4090": list(VARIANTS),
    # all-shared_sys is the report's own workload (a private system prompt per session)
    # under vLLM 0.32 KV semantics; "all" adds one system prompt per program
    "rtx4090_rates": ["legacy", "all", "all-shared_sys"],
    "rtx4090_high": ["legacy", "all", "all-shared_sys"],
    # several H100 cells preempt (MoE 0.4/s waste1 FCFS: ~130-180; eager 0.8/s: ~10-46), so
    # every fix gets its single and leave-one-out variant there too
    "h100": ["legacy", "all", "+shared_sys", "all-shared_sys", "all+sys_all", "all+gate_sched",
             "+lru_queue", "all-lru_queue", "+full_isl", "all-full_isl", "+resume",
             "all-resume"],
}
KEEP = ["lat_p50", "lat_p99", "drift", "preemptions", "root_cache_hit", "root_ttft_p99",
        "root_tpot_p99", "wasted_frac", "recompute_frac", "busy", "kv_evicted_tokens"]


def _one(job) -> dict:
    var, (config, policy, sched, rate, mix, kv), seed, n = job
    row = clog.one_run((config, policy, sched, rate, n, seed, kv, mix, VARIANTS[var]))
    out = {k: row[k] for k in KEEP}
    out.update(variant=var, config=config, policy=policy, sched=sched, rate=rate, mix=mix,
               kv=kv, seed=seed, sessions=n)
    return out


def run(group: str, variants: list[str], seeds: int, sessions: int, procs: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    done = pd.read_csv(RUNS) if RUNS.exists() else pd.DataFrame()
    have = set()
    if len(done):
        have = {(r.variant, r.config, r.policy, r.sched, round(r.rate, 4), r.mix, r.kv, r.seed,
                 r.sessions) for r in done.itertuples()}
    jobs = [(v, c, s, sessions) for v in variants for c in CELLS[group] for s in range(seeds)
            if (v, c[0], c[1], c[2], round(c[3], 4), c[4], c[5], s, sessions) not in have]
    print(f"{len(jobs)} runs ({len(have)} already in {RUNS.name})", flush=True)
    with mp.Pool(procs) as pool:
        for i, row in enumerate(pool.imap_unordered(_one, jobs)):
            pd.DataFrame([row]).to_csv(RUNS, mode="a", header=not RUNS.exists(), index=False)
            print(f"[{i + 1}/{len(jobs)}] {row['variant']:16s} {row['config']:7s} "
                  f"{row['policy']:22s} {row['sched']:5s} {row['rate']:.2f} {row['mix']:7s} "
                  f"{row['kv']:4s} s{row['seed']} p50={row['lat_p50']:6.1f} "
                  f"pre={row['preemptions']} hit={row['root_cache_hit']:.2f}", flush=True)


# ----------------------------------------------------------------------------- report
def _cells(df, **kw):
    m = df
    for k, v in kw.items():
        m = m[(m[k] - v).abs() < 1e-9] if k == "rate" else m[m[k] == v]
    return m


def ratio(df, var, config, rate, mix, policy, sched, kv="lru", base_kv="lru",
          base=("baseline", "fcfs")) -> tuple[float, float, float, list] | None:
    """p50 / paired no-speculation FCFS p50, per seed: (median, min, max, per seed)."""
    a = _cells(df, variant=var, config=config, rate=rate, mix=mix, policy=policy, sched=sched,
               kv=kv).set_index("seed")
    b = _cells(df, variant=var, config=config, rate=rate, mix=mix, policy=base[0],
               sched=base[1], kv=base_kv).set_index("seed")
    seeds = sorted(set(a.index) & set(b.index))
    if not seeds:
        return None
    rs = [a.loc[s, "lat_p50"] / b.loc[s, "lat_p50"] for s in seeds]
    return statistics.median(rs), min(rs), max(rs), rs


def med(df, col, **kw) -> float | None:
    m = _cells(df, **kw)
    return float(m[col].median()) if len(m) else None


def fmt_ratio(x, drift=None) -> str:
    if x is None:
        return "-"
    s = f"{x[0]:.2f} [{x[1]:.2f}-{x[2]:.2f}]"
    return s + ("†" if drift is not None and drift > 1.2 else "")


def report() -> None:
    df = pd.read_csv(RUNS)
    L = ["# Corrected headline cells: tables (simulated)", "",
         f"Generated by `experiments/corrections.py report` from `{RUNS.relative_to(ROOT)}`. "
         "Ratios are session p50 over the paired no-speculation FCFS p50, per seed, shown as "
         "median [min-max]. † marks a median drift > 1.2 (not steady state). "
         f"Sizes: {sorted(int(x) for x in df.sessions.unique())} sessions, seeds "
         f"{sorted(int(x) for x in df.seed.unique())}.", ""]
    rv = [v for v in VARIANTS if v in set(df[df.config == "rtx4090"].variant)]
    if rv:
        L += ["## RTX 4090, Qwen3-4B, 0.14 sessions/s, FCFS (report §4.2 row, §4.5)", "",
              "| variant | waste1 / baseline p50 | waste1 drift | shadow / baseline | root hit "
              "baseline / shadow / waste1 | preemptions shadow / waste1 | waste1 p50 lru / "
              "pin s | waste1 hit pin | none vs lru p50: baseline / shadow / waste1 | root "
              "TTFT p99 baseline / shadow s |", "|---|---|---|---|---|---|---|---|---|---|"]
        for v in rv:
            kw = dict(variant=v, config="rtx4090", rate=0.14, mix="serial", sched="fcfs")
            w = ratio(df, v, "rtx4090", 0.14, "serial", "shadow+waste1", "fcfs")
            sh = ratio(df, v, "rtx4090", 0.14, "serial", "shadow", "fcfs")
            dr = med(df, "drift", policy="shadow+waste1", kv="lru", **kw)
            hits = [med(df, "root_cache_hit", policy=p, kv="lru", **kw)
                    for p in ("baseline", "shadow", "shadow+waste1")]
            pre = [med(df, "preemptions", policy=p, kv="lru", **kw)
                   for p in ("shadow", "shadow+waste1")]
            lp = [med(df, "lat_p50", policy="shadow+waste1", kv=k, **kw) for k in ("lru", "pin")]
            hp = med(df, "root_cache_hit", policy="shadow+waste1", kv="pin", **kw)
            none = []
            for p in ("baseline", "shadow", "shadow+waste1"):
                x = ratio(df, v, "rtx4090", 0.14, "serial", p, "fcfs", kv="none", base=(p, "fcfs"))
                none.append(f"{x[0]:.3f}" if x else "-")
            tt = [med(df, "root_ttft_p99", policy=p, kv="lru", **kw) for p in ("baseline", "shadow")]
            f2 = lambda x, d=2: "-" if x is None else f"{x:.{d}f}"  # noqa: E731
            L.append(f"| {v} | {fmt_ratio(w, dr)} | {f2(dr)} | {fmt_ratio(sh)} | "
                     f"{' / '.join(f2(h) for h in hits)} | {' / '.join(f2(p, 0) for p in pre)} | "
                     f"{f2(lp[0], 1)} / {f2(lp[1], 1)} | {f2(hp)} | {' / '.join(none)} | "
                     f"{f2(tt[0])} / {f2(tt[1])} |")
        L += ["", "Per-seed waste1 / baseline ratios:", ""]
        for v in rv:
            w = ratio(df, v, "rtx4090", 0.14, "serial", "shadow+waste1", "fcfs")
            if w:
                L.append(f"- {v}: " + " / ".join(f"{x:.3f}" for x in w[3]))
        L.append("")
    lad = df[(df.config == "rtx4090") & ((df.rate - 0.14).abs() > 1e-9)]
    if len(lad):
        L += ["## RTX 4090 load ladder (FCFS)", "",
              "| variant | rate | shadow / baseline | waste1 / baseline | waste1 drift | prefix "
              "caching off, p50 vs on: baseline / shadow |", "|---|---|---|---|---|---|"]
        for v in [v for v in VARIANTS if v in set(lad.variant)]:
            for r in sorted(set(lad[lad.variant == v].rate) | {0.14}):
                sh = ratio(df, v, "rtx4090", r, "serial", "shadow", "fcfs")
                w = ratio(df, v, "rtx4090", r, "serial", "shadow+waste1", "fcfs")
                dr = med(df, "drift", variant=v, config="rtx4090", rate=r, mix="serial",
                         policy="shadow+waste1", sched="fcfs", kv="lru")
                off = [ratio(df, v, "rtx4090", r, "serial", p, "fcfs", kv="none",
                             base=(p, "fcfs")) for p in ("baseline", "shadow")]
                L.append(f"| {v} | {r:.2f} | {fmt_ratio(sh)} | {fmt_ratio(w, dr)} | "
                         f"{'-' if dr is None else f'{dr:.2f}'} | "
                         + " / ".join("-" if x is None else f"{x[0]:.3f}" for x in off) + " |")
        L.append("")
    hv = [v for v in VARIANTS if v in set(df[df.config != "rtx4090"].variant)]
    if hv:
        L += ["## H100 cells (report summary, §4.1, §4.2, §4.3)", "",
              "| cell | " + " | ".join(hv) + " |", "|---|" + "---|" * len(hv)]
        rows = [("graphs 0.8 FCFS shadow", ("graphs", 0.8, "serial", "shadow", "fcfs")),
                ("graphs 0.8 FCFS waste1", ("graphs", 0.8, "serial", "shadow+waste1", "fcfs")),
                ("graphs 0.8 agent waste1", ("graphs", 0.8, "serial", "shadow+waste1", "agent")),
                ("eager 0.8 FCFS shadow", ("eager", 0.8, "serial", "shadow", "fcfs")),
                ("eager 0.8 agent shadow", ("eager", 0.8, "serial", "shadow", "agent")),
                ("eager 0.8 FCFS waste1", ("eager", 0.8, "serial", "shadow+waste1", "fcfs")),
                ("eager 0.8 agent waste1", ("eager", 0.8, "serial", "shadow+waste1", "agent")),
                ("eager 0.8 agent waste1, 20% wrong",
                 ("eager", 0.8, "serial", "shadow+waste1+noise0.2", "agent")),
                ("eager 0.8 agent waste1, 40% wrong",
                 ("eager", 0.8, "serial", "shadow+waste1+noise0.4", "agent")),
                ("eager 0.4 FCFS waste1", ("eager", 0.4, "serial", "shadow+waste1", "fcfs")),
                ("eager 0.4 agent waste1", ("eager", 0.4, "serial", "shadow+waste1", "agent")),
                ("batched 0.6 FCFS waste1", ("eager", 0.6, "batched", "shadow+waste1", "fcfs")),
                ("batched 0.6 agent waste1", ("eager", 0.6, "batched", "shadow+waste1", "agent")),
                ("batched 0.8 FCFS waste1", ("eager", 0.8, "batched", "shadow+waste1", "fcfs")),
                ("batched 0.8 agent waste1", ("eager", 0.8, "batched", "shadow+waste1", "agent")),
                ("MoE 0.4 FCFS shadow", ("moe", 0.4, "serial", "shadow", "fcfs")),
                ("MoE 0.4 FCFS waste1", ("moe", 0.4, "serial", "shadow+waste1", "fcfs")),
                ("MoE 0.4 agent waste1", ("moe", 0.4, "serial", "shadow+waste1", "agent"))]
        for name, (cfg, rate, mix, pol, sched) in rows:
            cells = []
            for v in hv:
                x = ratio(df, v, cfg, rate, mix, pol, sched)
                dr = med(df, "drift", variant=v, config=cfg, rate=rate, mix=mix, policy=pol,
                         sched=sched, kv="lru")
                cells.append(fmt_ratio(x, dr))
            L.append(f"| {name} | " + " | ".join(cells) + " |")
        L += ["", "Preemptions (median over seeds), H100 cells with any:", ""]
        m = df[(df.config != "rtx4090") & (df.preemptions > 0)]
        if len(m):
            g = m.groupby(["config", "mix", "rate", "policy", "sched", "variant"]).preemptions
            for k, x in g.median().items():
                L.append(f"- {' '.join(map(str, k))}: {x:g}")
        else:
            L.append("- none")
        L.append("")
    (OUT / "tables.md").write_text("\n".join(L) + "\n")
    print(f"wrote {OUT / 'tables.md'}")


def check_legacy(procs: int) -> None:
    """The legacy variant must reproduce the report's committed cells exactly."""
    cells = []
    for seed in range(3):
        for pol in ("baseline", "shadow", "shadow+waste1"):
            cells.append(("kv_rtx4090", ("rtx4090", pol, "fcfs", 0.14, 240, seed, "lru", "serial")))
        for kv in ("pin", "none"):
            cells.append(("kv_rtx4090",
                          ("rtx4090", "shadow+waste1", "fcfs", 0.14, 240, seed, kv, "serial")))
        cells.append(("clog_graphs", ("graphs", "shadow+waste1", "fcfs", 0.8, 240, seed, "lru",
                                      "serial")))
    bad = 0
    with mp.Pool(procs) as pool:
        for (tag, a), row in zip(cells, pool.imap(_legacy_one, [c[1] for c in cells])):
            ref = pd.read_csv(ROOT / "results" / f"{tag}.csv")
            m = ref[(ref.config == a[0]) & (ref.policy == a[1]) & (ref.sched == a[2])
                    & ((ref.rate - a[3]).abs() < 1e-9) & (ref.seed == a[5]) & (ref.kv == a[6])
                    & (ref.mix == a[7])].iloc[0]
            ok = all(abs(row[k] - m[k]) <= 1e-9 * max(1.0, abs(m[k]))
                     for k in ("lat_p50", "lat_p99", "preemptions", "root_cache_hit"))
            bad += not ok
            print("ok  " if ok else "DIFF", tag, a, f"{row['lat_p50']:.4f} vs {m['lat_p50']:.4f}")
    print("legacy mismatches:", bad)
    if bad:
        raise SystemExit(1)


def _legacy_one(a):
    return clog.one_run(a + (clog.LEGACY,))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "report", "check-legacy"])
    ap.add_argument("--group", choices=list(CELLS), default="rtx4090")
    ap.add_argument("--variants", default="", help="comma list (default: the group's)")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--sessions", type=int, default=240)
    ap.add_argument("--procs", type=int, default=2)
    a = ap.parse_args()
    if a.cmd == "run":
        vs = a.variants.split(",") if a.variants else GROUP_VARIANTS[a.group]
        run(a.group, vs, a.seeds, a.sessions, a.procs)
    elif a.cmd == "report":
        report()
    else:
        check_legacy(a.procs)


if __name__ == "__main__":
    main()
