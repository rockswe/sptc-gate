"""The published client patches are the code the replays measured.

integrations/spec-ptc-sptc-hints.patch and integrations/spec-ptc-fork/[2-7]-*.patch,
applied in order to spec-ptc 9b78b7d, have to give the trees whose hashes the replay runs
recorded before their first unit (campaign.jsonl in results/modal_h100_replay/ and
results/modal_govern/: for patch 5 the launch of PREREG_GOVERN.md that was stopped, for
patch 6 its two runs). Patch 7 came after the last run: no run measured it, and its tree
is the one hashed here when it was written."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest
import replay

REPO = Path(__file__).resolve().parents[2]
SPEC_PTC = Path(os.environ["SPEC_PTC_ROOT"])
BASE = "9b78b7d"
SERIES = [REPO / "integrations" / "spec-ptc-sptc-hints.patch",
          *sorted((REPO / "integrations" / "spec-ptc-fork").glob("[0-9]-*.patch"))]
RUNS = REPO / "results" / "modal_h100_replay"
REGISTERED, FOLLOW_UP = "20261110-042602-replay", "20261110-053243-replay"
# patch 5 (limits that follow the load): the launch that was stopped. Patch 6 (no growth
# while the engine is not stepping): the two runs of PREREG_GOVERN.md and its addendum.
GOVERN = REPO / "results" / "modal_govern"
GOVERN_STOPPED = GOVERN / "stopped" / "20261111-083951-small"
GOVERN_RUNS = [GOVERN / "20261111-090725-small", GOVERN / "20261111-091523-replay"]
# patch 7 (one ceiling for the windows of a process): written after the runs, measured by none
PATCH_7_TREE = "9a5b714a2d78d0222398b923abb12c637ddee5f819dc714b36590db59b746f14"


def recorded(run: str | Path) -> dict:
    begin = json.loads((RUNS / run / "campaign.jsonl").read_text().splitlines()[0])
    assert begin["kind"] == "begin"
    return {name: t["py_tree"] for name, t in begin["trees"].items()}


def base_tree(dst: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("no git")
    tar = subprocess.run(["git", "-C", str(SPEC_PTC), "archive", "--format=tar", BASE],
                         capture_output=True)
    if tar.returncode:
        pytest.skip(f"no git checkout of spec-ptc with {BASE} at {SPEC_PTC}")
    with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as t:
        t.extractall(dst, filter="data")


def apply(tree: Path, patch: Path) -> None:
    # outside any repository, so that git applies the diff to the files as they are
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tree.parent)}
    done = subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch)], cwd=tree,
                          env=env, capture_output=True, text=True)
    assert done.returncode == 0, (patch.name, done.stderr)


def test_the_series_is_the_seven_patches_in_order():
    assert [p.name.split("-")[0] for p in SERIES[1:]] == ["2", "3", "4", "5", "6", "7"]
    assert [p.name.split("-")[1] for p in SERIES[1:]] == ["dbee0c2", "2555dd1", "ac5d733",
                                                         "e09ff01", "11b6d39", "47f0b98"]


def test_the_patches_give_the_trees_the_replays_hashed(tmp_path):
    tree = tmp_path / "spec-ptc"
    tree.mkdir()
    base_tree(tree)
    registered, follow_up = recorded(REGISTERED), recorded(FOLLOW_UP)
    # the unpatched client is the `stock` tree of both runs
    assert replay.tree_hash(tree)[0] == registered["stock"] == follow_up["stock"]
    after = {}
    for patch in SERIES:
        apply(tree, patch)
        after[patch.name.split("-")[0]] = replay.tree_hash(tree)[0]
    assert after["3"] == registered["fork"]
    assert after["4"] == follow_up["fork"]
    stopped, (small, h100) = recorded(GOVERN_STOPPED), map(recorded, GOVERN_RUNS)
    assert after["5"] == stopped["fork"]
    assert after["6"] == small["fork"] == h100["fork"]
    assert registered["stock"] == stopped["stock"] == small["stock"] == h100["stock"]
    assert after["7"] == PATCH_7_TREE
    assert len({registered["stock"], *after.values()}) == 8  # every patch changes the sources


def test_a_patch_carries_no_author_and_no_local_path():
    for patch in SERIES:
        text = patch.read_text()
        assert text.startswith("diff --git "), patch.name  # a plain diff, not a mail
        assert "/Users/" not in text and "@gmail" not in text, patch.name
