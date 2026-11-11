"""Campaign trajectories as input for experiments/census.py (the RLM call-shape census).

    python to_census.py <run dir> [<run dir> ...] --out rlm_replies.parquet
    python ../experiments/census.py rlm_replies.parquet ../results/census_rlm_qwen

One row per root reply: example_idx (run/unit/task), rlm_iter, model, response. Replies
only: no context, no sub-call prompts. Reads trajs_compact/ or rlm_trajs/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def rows_of(run: Path, model: str) -> list[dict]:
    rows = []
    for udir in sorted((run / "units").glob("*_c*_r*")):
        src = udir / "trajs_compact"
        if not src.is_dir():
            src = udir / "rlm_trajs"
        for f in sorted(src.glob("*.jsonl")):
            task = f.name.split("_20")[0]
            with open(f) as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    if d.get("type") == "iteration":
                        rows.append({"example_idx": f"{run.name}__{udir.name}__{task}",
                                     "rlm_iter": d["iteration"], "model": model,
                                     "response": d.get("response") or ""})
    return rows


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="Qwen3-30B-A3B-Instruct-2507")
    a = ap.parse_args(argv)
    rows = [r for run in a.runs for r in rows_of(run, a.model)]
    pd.DataFrame(rows).to_parquet(a.out)
    print(f"{len(rows)} replies from {len({r['example_idx'] for r in rows})} task runs -> {a.out}")


if __name__ == "__main__":
    main()
