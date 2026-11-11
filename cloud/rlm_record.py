"""Record RLM sessions with rlms' batch path fixed (PREREG_RECORD.md).

    python rlm_record.py run --out <dir> --tasks <tasks.json> --launch \\
        --serve-extra="--max-model-len 65536" --warmup-passes 2

The replay's result leans on one session whose root had fallen back to single calls after
rlms lost its batch prompts (results/modal_h100_replay/RESULTS.md, "What it changes").
This recording asks what the model writes when that does not happen.

It is the campaign of rlm_campaign.py, which this file does not change, with `nospec` as
its only arm unless `--arms` says otherwise, and three things around it:

- **batch_fix.py is applied, for every arm.** Every prompt of an llm_query_batched is
  answered.
- **A probe before the first unit** (batch_fix.probe, after the warm-up): batches of 20
  through rlms' own path against the engine, first with stock rlms, then with the fix. If a
  prompt is lost with the fix on, the run stops there, before any unit runs.
- **A deadline for a task's sub-calls** (SPTC_SUBCALL_DEADLINE_S, 1,200 s after the task
  starts; 0: none). rlms checks its 900 s timeout between turns only, so one block can keep
  a whole unit waiting: on November 9 a serial loop held one for 1,828 s. Past the deadline
  the task's LM handler refuses sub-calls, the program gets an error string for each, and
  the task is marked failed whatever it answers afterwards. No task that ends before its
  deadline is touched.

What it adds to a run's records:

- campaign.jsonl, `begin`: the sha256 of PREREG_RECORD.md and of this code, next to the
  campaign's own files.
- campaign.jsonl, `batch_probe`: both probes, batch by batch.
- per unit, batch_fix.json: batched prompts sent through the fix and those that failed,
  by cause, and the tasks the deadline stopped.
- events.jsonl, `subcall_deadline`: a task that passed its deadline.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEADLINE_S = float(os.environ.get("SPTC_SUBCALL_DEADLINE_S", "1200"))
PROBE_GAPS = tuple(float(x) for x in os.environ.get("SPTC_PROBE_GAPS", "0,0,6").split(","))
EXTRA_PROVENANCE = ("PREREG_RECORD.md", "batch_fix.py", "rlm_record.py", "record_app.py")

_task = threading.local()
_lock = threading.Lock()


class SubcallDeadline(RuntimeError):
    """A sub-call of a task that is past its deadline. rlms turns it into the error
    string the program gets."""


class ProbeFailed(RuntimeError):
    """The engine lost a batch prompt with the fix on. No unit was run."""


# --------------------------------------------------------------------------- the deadline
def install_deadline(runner, deadline_s: float):
    """Refuse a task's sub-calls once it is `deadline_s` old, and mark it failed.

    A task's LM handler is built on the task's thread (rlms, _spawn_completion_context),
    so it can carry the task's deadline. Every sub-call, single or batched, speculative or
    not, asks the handler for its client first: that is where it is refused. The root's
    own calls (depth 0) are not."""
    from rlm.core.lm_handler import LMHandler

    orig_init, orig_get, orig_task = LMHandler.__init__, LMHandler.get_client, runner._run_task

    def __init__(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        self._sptc_task = getattr(_task, "state", None)

    def get_client(self, model=None, depth=0):
        st = getattr(self, "_sptc_task", None)
        if st is not None and depth >= 1 and time.time() > st["deadline"]:
            with _lock:
                st["refused"] += 1
            raise SubcallDeadline(
                f"sub-call refused: this task passed its deadline of {deadline_s:.0f} s")
        return orig_get(self, model, depth)

    def run_task(task, model, base_url, spec, log, outdir, **kw):
        st = {"deadline": time.time() + deadline_s, "refused": 0}
        _task.state = st
        try:
            row = orig_task(task, model, base_url, spec, log, outdir, **kw)
        finally:
            _task.state = None
        if st["refused"]:
            log.log("subcall_deadline", task_id=task.task_id, refused=st["refused"],
                    deadline_s=deadline_s, ok_before=bool(row.get("ok")))
            row.update(ok=False, score=0.0,
                       error=f"SubcallDeadline: {st['refused']} sub-call requests refused "
                             f"after {deadline_s:.0f} s")
        return row

    LMHandler.__init__, LMHandler.get_client, runner._run_task = __init__, get_client, run_task

    def remove() -> None:
        LMHandler.__init__, LMHandler.get_client, runner._run_task = (orig_init, orig_get,
                                                                      orig_task)

    return remove


# --------------------------------------------------------------------------- the run
def run(a) -> Path:
    import rlm_campaign

    rlm_campaign.setup_paths(a.spec_ptc)
    import batch_fix
    import benchmark.oolong_campaign.runner as runner

    if not a.warmup_passes:
        raise SystemExit("the probe runs after the warm-up: --warmup-passes must be 1 or more")
    saved = {"files": rlm_campaign.PROVENANCE_FILES, "warmup": rlm_campaign.warmup,
             "unit": runner.run_unit}
    rlm_campaign.PROVENANCE_FILES = (*saved["files"], *EXTRA_PROVENANCE)

    def warmup(base_url, model, passes, note=None):
        waves = saved["warmup"](base_url, model, passes, note)
        probes = []
        if not batch_fix.applied():
            probes.append(batch_fix.probe(base_url, model, gaps=PROBE_GAPS))  # stock rlms
        batch_fix.apply()
        probes.append(batch_fix.probe(base_url, model, gaps=PROBE_GAPS))
        for p in probes:
            if note is not None:
                note("batch_probe", **p)
            print(f"batch probe, fix {'on' if p['fixed'] else 'off'}: {p['errors']} of "
                  f"{p['prompts']} prompts lost "
                  f"({', '.join(str(b['errors']) for b in p['batches'])} by batch)", flush=True)
        if probes[-1]["errors"]:
            raise ProbeFailed(f"{probes[-1]['errors']} of {probes[-1]['prompts']} probe prompts "
                              f"failed with the fix on: {probes[-1]['batches']}")
        return waves

    def run_unit(model, base_url, spec, concurrency, repeat, tasks, outdir):
        batch_fix.stats(reset=True)
        stats = saved["unit"](model, base_url, spec, concurrency, repeat, tasks, outdir)
        stopped = [t["task_id"] for t in stats.get("tasks", [])
                   if str(t.get("error") or "").startswith("SubcallDeadline")]
        (Path(outdir) / "batch_fix.json").write_text(json.dumps(
            {"applied": batch_fix.applied(), **batch_fix.stats(),
             "subcall_deadline_s": DEADLINE_S, "deadline_tasks": stopped}, indent=1))
        return stats

    rlm_campaign.warmup, runner.run_unit = warmup, run_unit
    remove_deadline = install_deadline(runner, DEADLINE_S) if DEADLINE_S > 0 else None
    try:
        return rlm_campaign.run_campaign(a, on_unit_done=getattr(a, "on_unit_done", None))
    finally:
        if remove_deadline is not None:
            remove_deadline()
        rlm_campaign.PROVENANCE_FILES = saved["files"]
        rlm_campaign.warmup, runner.run_unit = saved["warmup"], saved["unit"]
        batch_fix.revert()


def parse(argv: list[str]):
    import rlm_campaign

    argv = list(argv)
    if "run" not in argv:
        raise SystemExit("rlm_record.py has one subcommand: run (rlm_campaign.py has the others)")
    if not any(x == "--arms" or x.startswith("--arms=") for x in argv):
        argv += ["--arms", "nospec"]
    a = rlm_campaign.parser().parse_args(argv)
    for arm in a.arms:
        if arm not in rlm_campaign.ARMS:
            raise SystemExit(f"unknown arm {arm!r}; choose from {rlm_campaign.ARMS}")
    return a


def main(argv=None) -> None:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    a = parse(sys.argv[1:] if argv is None else argv)
    out = run(a)
    print((Path(out) / "summary.md").read_text())


if __name__ == "__main__":
    main()
