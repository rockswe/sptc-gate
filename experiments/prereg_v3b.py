"""Addendum to results/prereg_v3 for section B4 of kaggle/sptc_kaggle_v3.ipynb, written
before any GPU run: the no-bets reference arm `fcfs-b4/spec`, its claims, the B4 protocol
change (same prompts on every arm), and corrections to v3's B4 rule text.

No new simulation. In the simulator `fcfs-b4/*` arms are stock FCFS exactly (prereg_v3's
predictions.md), so the reference's predicted rows are prereg_v3's `fcfs/spec` rows, per
set (P1, P0, P1-alt). The script checks that identity on the rows v3 does have
(fcfs-b4/spec+bad equals fcfs/spec+bad), and checks prereg_v3's sha256 against its prereg
commit. results/prereg_v3 and results/prereg_v2 are never edited.

  PYTHONPATH=.:integrations .venv/bin/python experiments/prereg_v3b.py [--out results/prereg_v3b]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kaggle"))

import prereg_compare as PC  # noqa: E402
import prereg_v2 as P2  # noqa: E402
import vllm_bench as vb  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "results" / "prereg_v3"
OUT = ROOT / "results" / "prereg_v3b"
LOADS = (4, 8)
NOBETS = vb.BASELINE_NOBETS
METRICS = ("session_p50", "root_tpot_p50", "root_tpot_p99")

PROTOCOL = [
    "**Same prompts on every B4 arm.** In v3's protocol the three arms on each stock "
    "FCFS launch (fcfs-b4, proxy, proxy-sem) had numbered prompt prefixes (`[spec d1 n8 "
    "r0]`, `[spec d1 v1 n8 r0]`, `[spec d1 v2 n8 r0]`), to keep their runs out of each "
    "other's prefix cache. Sub-calls stop at EOS, so a different prefix can change their "
    "length: B4-1..8 and B4P-1..8 compared unlike prompts. Now every B4 arm sends the same "
    "text (`[spec n8 r0]`, the number of bad guesses left out), and the arms that share a "
    "launch are kept apart by vLLM's per-request `cache_salt` (`sptc-v1`, `sptc-v2`, "
    "`sptc-v3`; it enters the first KV block's hash). If a server refuses `cache_salt` the "
    "bench falls back to numbered prefixes and says so; every run records `salt` and "
    "`cache_salt`. The predicted values of v3's B4 claims do not change: the simulator has "
    "no prompt text.",
    "**No-bets reference `fcfs-b4/spec`** on the same stock FCFS launches: speculation "
    "without bad guesses, 3 repeats at 8 and 4 agents (6 more runs). Claims B4C-* and "
    "B4N-* below.",
    "**Work and prefix-cache columns.** The B4 table of `sweep/summary.md` now gives, per "
    "arm, sub-call completion tokens per session against fcfs-b4, session p50 against the "
    "no-bets reference, the share of decoys refused, and the server's prefix-cache hit "
    "share (`vllm:prefix_cache_hits` over `vllm:prefix_cache_queries`, per run).",
]

READING = [
    "**B4 cannot show a cost of refusing too many bets.** Every bet in this bench is a "
    "decoy: a bad guess of the same size, never claimed. Real speculative calls are kind "
    "`early`, which no gate and no bets-only priority touches. So refusing every bet is "
    "the best possible gate here, and the B4 arms rank by how many bets they refuse. The "
    "no-bets reference measures that best case directly. An arm within tolerance of it "
    "(B4N-*) has refused nearly every bet. Where two arms both refuse (nearly) all bets "
    "(in P1 at 8 agents, the window cap and the plugin both refuse 100%: B4P-3/4 predict "
    "0.994), their ratio compares two arms that send almost no bets, and says nothing "
    "about which gate is smarter. 'If the GPU agrees, the T4 win needs no scheduler "
    "change at this load' holds only for a workload whose bets are all worthless.",
    "**Work check (secondary, not a verdict).** Next to each B4 ratio, read the ratio of "
    "sub-call tokens per session (numerator over denominator; "
    "`experiments/prereg_compare.py` prints it as 'work'). Away from 1 by more than the "
    "claim's tolerance, the two arms did not run the same workload and the claim is read "
    "as confounded, whatever its verdict.",
    "**Prefix-cache check (secondary).** The proxy and no-bets arms' prefix-cache hit "
    "share should be close to fcfs-b4's on the same launches. A clearly higher share means "
    "`cache_salt` did not keep the runs apart.",
    "**Launch depth (known limit, not corrected).** Four B4 arms share each stock FCFS "
    "launch (fcfs-b4, proxy, proxy-sem, no-bets: 16 measured runs in round 0, 8 in "
    "round 1), while prio-bets and plugin-b4 have a launch each (4 and 2). Arm order "
    "rotates within a launch and the rounds are ABBA, but claims across launches (B4P-*, "
    "B4-9..16, B4N for prio-bets and plugin-b4) compare runs made at different depths into "
    "a launch. Read them with the per-launch GPU clocks in `sweep/summary.md` ('Per server "
    "launch').",
]

CORRECTIONS = [
    "v3's rule 'baselines' (predictions.json `rules.baselines` and predictions.md) says the "
    "B4 denominators are fcfs-b4/spec+bad. That holds for B4-1..16 only. B4P-1..8 divide "
    "plugin-b4/spec+bad (plugin launches) by proxy/spec+bad or proxy-sem/spec+bad (stock "
    "FCFS launches). prereg_compare scores every claim with its own numerator and "
    "denominator, so no verdict changes; only the rule text was wrong.",
    "The same rule's '(same server, other prompt prefix)' no longer holds: see the "
    "protocol change above.",
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_v3() -> dict:
    """prereg_v3's files against the sha256 of its prereg commit (prereg_compare's table)."""
    got = {k: ("match" if sha256(V3 / k) == want else "MISMATCH")
           for k, want in PC.PREREG_SHA256["prereg_v3"].items()}
    if "MISMATCH" in got.values():
        raise SystemExit(f"results/prereg_v3 does not match its prereg commit: {got}")
    return got


def build_set(st: dict) -> tuple[dict, list[dict]]:
    """One prediction set of v3 -> (the B4 rows with the reference added, claims)."""
    rows = {(r["arm"], r["agents"]): r for r in st["summary"]["rows"]}
    for n in LOADS:  # the identity the reference's rows rest on
        for b4, base in (("fcfs-b4/spec+bad", "fcfs/spec+bad"),
                         ("plugin-b4/spec+bad", "plugin/spec+bad")):
            if any(rows[(b4, n)][m] != rows[(base, n)][m] for m in METRICS):
                raise SystemExit(f"{b4} != {base} at {n}: the sim does not equal them")
        rows[(NOBETS, n)] = {**rows[("fcfs/spec", n)], "arm": NOBETS,
                             "copied_from": "fcfs/spec"}
    keep = [rows[(a, n)] for a in vb.B4_ARMS for n in LOADS]
    c = P2.ratio_claims(rows, "B4C", "B4: cost of the bets (no-bets reference)",
                        [(NOBETS, vb.BASELINE_REF, n) for n in LOADS],
                        ("session_p50", "root_tpot_p50"))
    c += P2.ratio_claims(rows, "B4N", "B4: each arm vs refusing every bet",
                         [(a, NOBETS, n) for a in vb.BASELINE_ARMS if a != vb.BASELINE_REF
                          for n in LOADS], ("session_p50", "root_tpot_p50"))
    seen: dict[str, int] = {}
    for x in c:
        seen[x["id"]] = seen.get(x["id"], 0) + 1
        x["id"] = f"{x['id']}-{seen[x['id']]}"
    return {"rows": keep, "slo": st["summary"]["slo"]}, c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    v3_files = check_v3()
    v3 = json.loads((V3 / "predictions.json").read_text())
    git = P2.git_state()
    try:
        rel = str(out.resolve().relative_to(ROOT))
        git["dirty_files"] = [x for x in git["dirty_files"] if not x[3:].startswith(rel)]
    except ValueError:
        pass
    sets = {}
    for key, st in v3["sets"].items():
        summ, claims = build_set(st)
        dec = [x for x in st["decoy_rejected"] if x["arm"] in vb.B4_ARMS]
        sets[key] = {"summary": summ, "claims": claims, "decoy_rejected": dec,
                     "proxy": st.get("proxy", [])}
    res = {
        "stamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "label": "PREDICTED by the simulator before any GPU run of kaggle/sptc_kaggle_v3.ipynb "
                 "(addendum to prereg_v3, section B4; no new simulation)",
        "version": "v3b",
        "code": {**git, "script": "experiments/prereg_v3b.py"},
        "based_on": {"prereg_v3_commit": "2e39a4d", "prereg_v3_files": v3_files,
                     "prereg_v3_code_commit": v3["code"]["commit"],
                     "prereg_v3_stamp": v3["stamp_utc"]},
        "primary": v3["primary"],
        "sets": sets,
        "summary": sets[v3["primary"]]["summary"],
        "overhead": [],
        "general": {"claims": [], "quick_claims": []},
        "protocol_changes": PROTOCOL,
        "reading_rules": READING,
        "corrections_to_v3": CORRECTIONS,
        "rules": {**v3["rules"],
                  "baselines": "B4C and B4N ratio claims use v3's ratio rule (tol "
                               f"{P2.TOL}); each claim's denominator is its own: "
                               "fcfs-b4/spec+bad for B4C, the no-bets reference "
                               f"{NOBETS} for B4N, both on the stock FCFS launches."},
    }
    ns = argparse.Namespace(preset="baselines", arms=None, agents=None, reps=None, turns=None,
                            rounds=None, warm_pass=False,
                            predictions=str(V3 / "predictions.json"))
    res["gpu_minutes"] = {"baselines": {k: v for k, v in vb.plan(ns).items() if k != "rows"}}
    (out / "predictions.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "predictions.md").write_text(markdown(res, v3))
    print(f"wrote {out}")


def markdown(res: dict, v3: dict) -> str:
    p1 = res["sets"]["P1"]
    L = ["# Pre-registered predictions, addendum v3b: section B4", "",
         f"**PREDICTED by the simulator, not measured.** Written {res['stamp_utc']} by "
         "`experiments/prereg_v3b.py`, before any GPU run of `kaggle/sptc_kaggle_v3.ipynb`. "
         "Not edited after the run. `experiments/prereg_compare.py` scores it next to "
         "`results/prereg_v3` (primary) and `results/prereg_v2`.", "",
         f"- Code: commit `{res['code']['commit']}`"
         + (" (clean tree)" if not res["code"]["dirty_files"] else
            f" with uncommitted changes: {res['code']['dirty_files']}") + ".",
         f"- Based on `results/prereg_v3` (prereg commit 2e39a4d, written "
         f"{res['based_on']['prereg_v3_stamp']}; its files checked against that commit's "
         f"sha256: {res['based_on']['prereg_v3_files']}). Nothing in prereg_v3 or prereg_v2 "
         "changes.",
         f"- No new simulation. The no-bets reference `{NOBETS}` is simulated as stock FCFS "
         "with speculation and no bad guesses, which is v3's `fcfs/spec` row per set. The "
         "script checks the identity it rests on: in every set, v3's fcfs-b4/spec+bad and "
         "plugin-b4/spec+bad rows equal fcfs/spec+bad and plugin/spec+bad at 4 and 8 agents.",
         "- Nothing fit: the claims are ratios of v3's predicted rows.", "",
         "## Protocol change after v3, before any run", ""]
    L += [f"- {x}" for x in res["protocol_changes"]]
    L += ["", "## Corrections to v3's B4 text", ""]
    L += [f"- {x}" for x in res["corrections_to_v3"]]
    L += ["", "## How to read B4 (fixed before the run)", ""]
    L += [f"- {x}" for x in res["reading_rules"]]
    rows = {(r["arm"], r["agents"]): r for r in p1["summary"]["rows"]}
    p0 = {(r["arm"], r["agents"]): r for r in res["sets"]["P0"]["summary"]["rows"]}
    rej = {(x["arm"], x["agents"]): x["frac"] for x in p1["decoy_rejected"]}
    L += ["", "## B4 rows and ratios (P1; P0 in brackets)", "",
          "| arm | agents | session p50 s | root TPOT p50 ms | vs fcfs-b4: session p50 | "
          "vs no bets: session p50 | vs no bets: root TPOT p50 | decoys rejected |",
          "|---|---|---|---|---|---|---|---|"]
    for name in vb.B4_ARMS:
        for n in LOADS:
            r, q = rows[(name, n)], p0[(name, n)]
            ref, nb = rows[(vb.BASELINE_REF, n)], rows[(NOBETS, n)]
            L.append(f"| {name} | {n} | {r['session_p50']:.2f} [{q['session_p50']:.2f}] | "
                     f"{r['root_tpot_p50']:.1f} [{q['root_tpot_p50']:.1f}] | "
                     f"{r['session_p50'] / ref['session_p50']:.3f} | "
                     f"{r['session_p50'] / nb['session_p50']:.3f} | "
                     f"{r['root_tpot_p50'] / nb['root_tpot_p50']:.3f} | "
                     f"{vb._fmt(rej.get((name, n)))} |")
    L += ["", "## Claims (P1 predicted; P0, P1-alt in brackets)", "",
          "| id | section | claim | predicted | tol |", "|---|---|---|---|---|"]
    other = {k: {x["id"]: x["predicted"] for x in st["claims"]}
             for k, st in res["sets"].items() if k != "P1"}
    for c in p1["claims"]:
        alt = ", ".join(f"{other[k][c['id']]:.3f}" for k in other)
        L.append(f"| {c['id']} | {c['section']} | {c['numerator'][0]} / {c['denominator'][0]}"
                 f" at {c['numerator'][1]}: {c['metric']} | {c['predicted']:.3f} [{alt}] | "
                 f"{c['tol']} |")
    g = res["gpu_minutes"]["baselines"]
    L += ["", "## Rules", "",
          f"- **ratio** (v3's, unchanged): {res['rules']['ratio']}",
          f"- **validity** (v3's, unchanged): {res['rules']['validity']}",
          f"- **baselines.** {res['rules']['baselines']}", "",
          "## GPU time of section B4 (estimate, `vllm_bench.py plan` on v3's predictions)", "",
          f"Preset `baselines`: {g['runs']} runs, {g['launches']} launches (plus up to "
          f"{g['cache_fill_launches_max']} cache-filling), about {g['est_minutes']} min "
          f"(v3: {v3['gpu_minutes']['baselines']['est_minutes']} min).", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
