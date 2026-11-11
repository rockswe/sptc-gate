"""Two sweeps of the T4 bench's `both_default` preset, per pattern (offline, stdlib only).

    python both_compare.py <old client's run dir> <new client's run dir>

The bench's own table pools every session of an arm, and the pooled median sits between
the patterns' clusters (4 s to 16 s), so it jumps. This script takes the median per
pattern, the ratio to stock (fcfs-d/spec+bad) and to no speculation, and their geometric
mean over the four patterns, as results/kaggle_t4_v4/RESULTS.md did for the third T4 run.
"""

import glob, json, math, statistics, sys
from collections import Counter, defaultdict

def load(d):
    arms = defaultdict(lambda: defaultdict(list)); extra = defaultdict(Counter)
    for f in sorted(glob.glob(d + "/sweep/runs/*.json")):
        r = json.load(open(f))
        for s in r.get("sessions", []):
            arms[r["arm"]][s["pattern"]].append(s["wall_s"])
            calls = s.get("calls", []); dec = s.get("decoys", [])
            e = extra[r["arm"]]
            e["sessions"] += 1
            e["bets"] += sum(c.get("kind") == "bet" for c in calls)
            e["bets_done"] += sum(c.get("kind") == "bet" and c.get("outcome") == "completed" for c in calls)
            e["fallbacks"] += sum(c.get("kind") == "fallback" for c in calls)
            e["decoys"] += len(dec)
            e["decoys_ran"] += sum(d.get("outcome") in ("completed", "cancelled") for d in dec)
            e["decoy_tokens"] += sum(d.get("tokens") or 0 for d in dec)
            e["stops"] += bool(s.get("shadow_stopped"))
    return arms, extra

def geo(xs): return math.exp(statistics.fmean(math.log(x) for x in xs))

res = {}
for label, d in (("old", sys.argv[1]), ("new", sys.argv[2])):
    arms, extra = load(d)
    pats = sorted(arms["fcfs-d/spec+bad"])
    med = {a: {p: statistics.median(arms[a][p]) for p in pats} for a in arms}
    res[label] = (med, extra, pats)
    print(f"\n=== {label} client: session wall, median per pattern (s), and ratio to stock (fcfs-d/spec+bad) ===")
    print(f"{'arm':16s} " + " ".join(f"{p:>18s}" for p in pats) + "   geo mean vs stock   vs nospec")
    for a in ("fcfs-d/nospec", "fcfs-d/spec", "fcfs-d/spec+bad", "prio-d/both", "cap-d/both", "plugin-d/both"):
        if a not in med: continue
        r_stock = [med[a][p] / med["fcfs-d/spec+bad"][p] for p in pats]
        r_nospec = [med[a][p] / med["fcfs-d/nospec"][p] for p in pats]
        print(f"{a:16s} " + " ".join(f"{med[a][p]:7.2f} ({x:5.2f}x)   " for p, x in zip(pats, r_stock)) + f"   {geo(r_stock):.3f}              {geo(r_nospec):.3f}")
    print("per session:  " + " | ".join(f"{a}: bets {e['bets']/e['sessions']:.1f} (ran {e['bets_done']/e['sessions']:.1f}), re-runs {e['fallbacks']/e['sessions']:.1f}, decoys {e['decoys']/e['sessions']:.1f} (ran {e['decoys_ran']/e['sessions']:.1f}), stops {e['stops']}/{e['sessions']}" for a, e in extra.items() if a in ("cap-d/both", "plugin-d/both")))
old, new = res["old"][0], res["new"][0]
pats = res["old"][2]
print("\n=== new client over old client, same arm, per pattern (below 1: the new client is faster) ===")
for a in ("fcfs-d/nospec", "fcfs-d/spec", "fcfs-d/spec+bad", "prio-d/both", "cap-d/both", "plugin-d/both"):
    rs = [new[a][p] / old[a][p] for p in pats]
    print(f"{a:16s} " + " ".join(f"{p}: {x:.3f}" for p, x in zip(pats, rs)) + f"   geo mean {geo(rs):.3f}")
