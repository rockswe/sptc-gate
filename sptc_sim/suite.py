"""spec-ptc's benchmark suite: patterns and the committed results (runs.csv)."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

SPEC_PTC = Path(os.environ.get("SPEC_PTC_DIR", Path(__file__).resolve().parents[2] / "spec-ptc"))
RUNS_CSV = SPEC_PTC / "benchmark/suite/results/v1/runs.csv"


@lru_cache(maxsize=1)
def patterns() -> dict:
    """name -> spec-ptc Pattern (imports the suite modules from the local clone)."""
    if str(SPEC_PTC) not in sys.path:
        sys.path.insert(0, str(SPEC_PTC))
    import benchmark.suite.patterns_v2  # noqa: F401
    import benchmark.suite.patterns_v3  # noqa: F401
    import benchmark.suite.patterns_v4  # noqa: F401
    import benchmark.suite.patterns_v5  # noqa: F401
    import benchmark.suite.patterns_v6  # noqa: F401
    from benchmark.suite.patterns import PATTERNS

    return {p.name: p for p in PATTERNS}


def context() -> str:
    patterns()
    from benchmark.suite.patterns import CONTEXT

    return CONTEXT


def response_text(name: str) -> str:
    patterns()
    from benchmark.suite.patterns import response_text as rt

    return rt(patterns()[name])


def runs() -> pd.DataFrame:
    return pd.read_csv(RUNS_CSV)


def measured_medians() -> pd.DataFrame:
    df = runs()
    g = df.groupby(["pattern", "mode"]).agg(
        wall_med=("wall_s", "median"),
        stream_med=("stream_s", "median"),
        exec_med=("exec_s", "median"),
        call_med=("call_s_median", "median"),
        n=("wall_s", "size"),
        hits=("hits", "median"),
        misses=("misses", "median"),
        evicted=("evicted", "median"),
        dispatched=("dispatched", "median"),
    )
    return g.reset_index()
