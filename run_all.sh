#!/bin/bash
# Reproduce every number and figure in docs/report.md (CPU only; ~2 h on 12 cores).
# Needs the spec-ptc clone at ../spec-ptc (pinned 9b78b7d). The tool-latency table is
# committed; to rebuild it, set COPILOT to one day of the Copilot dataset (docs/design-notes.md).
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
CLOG="$PY experiments/clog.py"
R=0.05,0.1,0.2,0.4,0.6,0.8

$PY -m pytest -q
$PY experiments/validate_cost.py                 # step cost vs published ITL tables
$PY experiments/validate_mock.py --reps 3        # agent side vs real spec-ptc (cached reps reused)
$PY experiments/calibrate.py                     # 22 medians of spec-ptc's runs.csv
[ -f results/copilot_tool_latency.csv ] || \
  $PY -I experiments/copilot_tools.py \
    "${COPILOT:?set COPILOT=/path/to/date.2026-06-06.tar.gz}" results/copilot_tool_latency.csv
$PY experiments/sweep.py                         # TPOT x tool-latency sweep
$PY experiments/freeride.py                      # Q2

# Q1, calibrated H100 + Qwen3-4B (eager), all policies x all schedulers
$CLOG --config eager --rates $R
# confidence-aware scheduler without a perfect oracle
$CLOG --config eager --rates 0.05,0.2,0.4,0.6,0.8 --scheds fcfs,agent \
  --policies shadow+waste1+noise0.1,shadow+waste1+noise0.2,shadow+waste1+noise0.4 \
  --tag clog_eager_noise
# sensitivity: the largest per-sequence overhead calibration tolerates
$CLOG --config eager_hiseq --rates $R --scheds fcfs,agent \
  --policies baseline,shadow,shadow+waste1 --tag clog_eager_hiseq
# programs that already batch their fan-out (llm_query_batched)
$CLOG --config eager --mix batched --rates $R --scheds fcfs,agent \
  --policies baseline,shadow,shadow+waste1 --tag clog_eager_batched
# other servers
$CLOG --config graphs --rates $R --scheds fcfs,agent-naive,agent \
  --policies baseline,shadow,dataflow,shadow+waste1
$CLOG --config moe --rates 0.05,0.1,0.2,0.3,0.4 --scheds fcfs,agent-naive,agent \
  --policies baseline,shadow,dataflow,shadow+waste1
# KV retention across tool gaps on a 24 GB GPU
$CLOG --config rtx4090 --rates 0.02,0.05,0.08,0.11,0.14 --scheds fcfs \
  --policies baseline,shadow,shadow+waste1 --kv lru,pin,none --tag kv_rtx4090
$PY experiments/figures.py
