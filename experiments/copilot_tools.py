"""Tool-latency distribution from the GitHub Copilot coding-agent dataset 2026
(Azure Public Dataset, CC-BY). Streams one day's .tar.gz without extracting it.

  python -I experiments/copilot_tools.py <path/to/date.YYYY-MM-DD.tar.gz> <out.csv>
"""

import csv
import gzip
import io
import json
import sys
import tarfile
from collections import defaultdict


def quantiles(xs, qs=(0.5, 0.9, 0.99)):
    xs = sorted(xs)
    return [xs[min(len(xs) - 1, int(q * len(xs)))] for q in qs]


def main(path: str, out: str) -> None:
    by_tool = defaultdict(list)
    batch_sizes = defaultdict(int)
    sessions = 0
    with tarfile.open(path, "r:gz") as tar:
        for m in tar:
            if not (m.isfile() and m.name.endswith(".jsonl.gz")):
                continue
            raw = tar.extractfile(m).read()
            for line in io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(raw)), "utf-8"):
                sess = json.loads(line)
                sessions += 1
                for turn in sess.get("turns") or []:
                    for b in turn.get("tool_batches") or []:
                        calls = b.get("function_calls") or []
                        batch_sizes[len(calls)] += 1
                        for c in calls:
                            d = c.get("duration_ms")
                            if isinstance(d, (int, float)) and d >= 0:
                                by_tool[c.get("name") or "?"].append(d / 1000.0)
    allx = [x for v in by_tool.values() for x in v]
    rows = [("ALL", len(allx), *quantiles(allx))]
    for name, xs in sorted(by_tool.items(), key=lambda kv: -len(kv[1]))[:15]:
        rows.append((name, len(xs), *quantiles(xs)))
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tool", "n", "p50_s", "p90_s", "p99_s"])
        w.writerows(rows)
    nb = sum(batch_sizes.values())
    print(f"sessions={sessions} tool_calls={len(allx)} batches={nb} "
          f"single_call_batches={batch_sizes.get(1, 0) / max(1, nb):.3f}")
    for r in rows:
        print(f"{r[0]:32s} n={r[1]:8d} p50={r[2]:8.3f}s p90={r[3]:8.3f}s p99={r[4]:8.3f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
