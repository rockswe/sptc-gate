#!/bin/bash
# Build the bundle for upload as a Kaggle Dataset (e.g. named "sptc-bundle-v4"), for
# kaggle/sptc_kaggle_v4.ipynb (the pressure run). Contains: sptc-sim as committed at HEAD
# (git archive, so nothing uncommitted or gitignored),
# with the vLLM plugin and the Kaggle runners; spec-ptc (from the sptc-hints worktree if
# present, so the client tags requests and re-runs a refused bet at its claim); and
# BUNDLE_INFO.json: both commits, and whether the plugin changed since run 2's bundle. Of
# results/, only what the notebooks read: the pre-registered predictions (prereg_v4,
# prereg_v4_fallback and prereg_v4b, which the v4 notebook scores; prereg_v3, v3b and v2,
# which `vllm_bench.py plan` and experiments/prereg_compare.py default to), the simulated study's
# results/pressure, and the T4 calibration inputs the earlier predictions were made from.
#   kaggle/make_bundle.sh [OUT.zip]     (default: ../sptc-bundle-v4.zip; never overwrites
#                                        an existing bundle)
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(dirname "$HERE")"
OUT="${1:-$ROOT/sptc-bundle-v4.zip}"
RUN2=53722e0  # the second T4 run's bundle commit (results/kaggle_t4_v3/RESULTS.md)
if [ -e "$OUT" ]; then echo "$OUT exists: not overwriting (move it away first)" >&2; exit 1; fi
if [ -n "$(git -C "$HERE" status --porcelain --untracked-files=no)" ]; then
  echo "warning: sptc-sim has uncommitted changes; the bundle has HEAD without them" >&2
fi
TMP="$(mktemp -d)"
mkdir -p "$TMP/sptc-bundle/sptc-sim"
git -C "$HERE" archive HEAD -- . ':!results' | tar -x -C "$TMP/sptc-bundle/sptc-sim"
git -C "$HERE" archive HEAD -- results/calibration.json results/prereg_v4 \
  results/prereg_v4_fallback results/prereg_v4b results/pressure results/prereg_v3 \
  results/prereg_v3b results/prereg_v2 \
  results/kaggle_t4/sptc_out/{calib,concur,suite,load,load_tagged}.json \
  results/t4_run1_analysis/predictions.{json,md} results/sweep_prep/predictions.{json,md} \
  results/sweep_prep/overhead_pure.json results/general/predictions.json \
  | tar -x -C "$TMP/sptc-bundle/sptc-sim"
SPTC="$ROOT/spec-ptc-sptc-hints"; [ -d "$SPTC" ] || SPTC="$ROOT/spec-ptc"
rsync -a --exclude .git --exclude .venv --exclude __pycache__ --exclude media \
  --exclude uv.lock "$SPTC/" "$TMP/sptc-bundle/spec-ptc/"
python3 - "$HERE" "$SPTC" "$RUN2" > "$TMP/sptc-bundle/BUNDLE_INFO.json" <<'EOF'
import json, subprocess, sys, time

sim, sptc, run2 = sys.argv[1:4]
plugin = ["integrations/sptc_vllm", "integrations/pyproject.toml",
          "integrations/spec-ptc-sptc-hints.patch"]


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


same = subprocess.run(["git", "-C", sim, "diff", "--quiet", run2, "HEAD", "--", *plugin])
print(json.dumps({
    "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "sptc_sim": {"commit": git(sim, "rev-parse", "HEAD"),
                 "branch": git(sim, "rev-parse", "--abbrev-ref", "HEAD"),
                 "not_in_bundle_uncommitted": (git(sim, "status", "--porcelain",
                                                   "--untracked-files=no") or "").splitlines()},
    "plugin": {"paths": plugin,
               "last_commit": git(sim, "log", "-1", "--format=%h %s", "--", *plugin),
               "run2_bundle_commit": run2, "unchanged_since_run2": same.returncode == 0},
    "spec_ptc": {"source": sptc, "commit": git(sptc, "rev-parse", "HEAD"),
                 "branch": git(sptc, "rev-parse", "--abbrev-ref", "HEAD"),
                 "in_bundle_uncommitted": (git(sptc, "status", "--porcelain") or "").splitlines()},
}, indent=1))
EOF
(cd "$TMP" && zip -qr "$OUT" sptc-bundle)
rm -rf "$TMP"
du -h "$OUT"
