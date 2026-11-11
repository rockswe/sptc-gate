"""A replay campaign: the corpus's sessions in several arms, on one engine launch.

    python replay_campaign.py run --out <dir> --corpus <dir> --arms nospec,stream,scout,wide \
        --trees stock=../../spec-ptc,fork=../../spec-ptc-sptc-hints --launch \
        --serve-extra="--max-model-len 65536"
    python replay_campaign.py summarize --out <dir>

A unit is one arm, once: every session of the corpus, `--conc` at a time. Units run one
after another against the same server, each in its own process (replay.py unit), because
the arms import different spec-ptc trees: the stock one at 9b78b7d for `nospec` and `stream`, the
sptc-hints fork for the others.

- **Order.** Repeat 1 in the order given, repeat 2 reversed (ABBA). Arms listed in `--once`
  run a single unit each, after the repeats. `--units stream:1,scout:1` gives the order
  outright.
- **A unit to throw away** (`--warm-arm scout`). The first unit of a launch pays for a cold
  engine: 25 to 72 s of root stalls in both runs of November 10. This unit runs first, is
  kept under `warm/` and is in no table. `--warm-sessions` gives it its own, shorter list
  of sessions.
- **Cold prefix cache for every unit.** A replay sends the same prompts again in every
  unit. Each unit puts its own salt in front of every prompt it sends, so no unit finds
  another's prompts in the engine's prefix cache. Inside a unit the cache works as in a
  live run.
- **Warm-up, budget stop, resume:** as rlm_campaign.py. The warm-up also sends 256, 512 and
  1,024 concurrent short requests: a wide arm at concurrency 8 can reach that.
- **Recorded before the first unit** (`campaign.jsonl`, `begin`): the sha256 of the
  pre-registrations and of this code, of each spec-ptc tree's sources, and of the corpus.
- **A design file** (`--design-file`): which sessions are left out and which turns a
  pre-registration names, as data. It is copied to `design.json` and hashed in `begin`;
  replay_report.py scores its predictions.
- **Extra units** (`--extra-units`, `--extra-sessions`): units that run after all the
  others, with their own list of sessions, and are kept under `extra/` with a summary of
  their own. For what a design declares outside its registered comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROVENANCE_FILES = ("PREREG_REPLAY.md", "PREREG_REPLAY_ADDENDUM.md", "PREREG_RECORD.md",
                    "PREREG_RECORD_ADDENDUM.md", "PREREG_GOVERN.md",
                    "PREREG_GOVERN_ADDENDUM.md", "replay.py",
                    "replay_campaign.py", "replay_corpus.py", "replay_report.py",
                    "rlm_stream.py", "repl_fix.py", "replay_app.py")
WIDE_WAVES = ((256, "short"), (512, "short"), (1024, "short"))
HASH_SEED = "0"


def plan_units(arms: list[str], repeats: int, once: list[str]) -> list[tuple[str, int]]:
    """ABBA over repeats; then the `once` arms, a single unit each. They come last so that
    a budget stop costs a control, not a repeat of a main arm."""
    units: list[tuple[str, int]] = []
    for r in range(1, repeats + 1):
        units += [(arm, r) for arm in (arms if r % 2 else list(reversed(arms)))]
    return units + [(arm, 1) for arm in once]


def unit_name(arm: str, conc: int, rep: int) -> str:
    return f"{arm}_c{conc}_r{rep}"


def sha_file(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def corpus_hash(corpus: Path, sessions: list[str] | None) -> dict:
    manifest = json.loads((corpus / "manifest.json").read_text())
    rows = [r for r in manifest["sessions"] if r.get("replayable")
            and (not sessions or r["session"] in sessions)]
    return {"manifest_sha256": sha_file(corpus / "manifest.json"),
            "sessions": {r["session"]: sha_file(corpus / f"{r['session']}.json") for r in rows}}


def provenance(trees: dict[str, Path], corpus: Path, sessions: list[str] | None) -> dict:
    import replay

    out = {"files": {name: sha_file(HERE / name) for name in PROVENANCE_FILES},
           "corpus": corpus_hash(corpus, sessions), "trees": {}}
    for name, root in trees.items():
        h, n = replay.tree_hash(root)
        try:
            git = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip() or None
        except OSError:  # no git here (a container): launch.json has the commits
            git = None
        out["trees"][name] = {"path": str(root), "py_tree": h, "py_files": n, "git": git}
    return out


def pkg_dir(tree: Path, base: Path) -> Path:
    """A folder holding `spec_ptc` -> <tree>/src, to put on PYTHONPATH in front of any
    installed spec-ptc."""
    d = base / hashlib.sha1(str(tree.resolve()).encode()).hexdigest()[:10]
    d.mkdir(parents=True, exist_ok=True)
    link = d / "spec_ptc"
    if not link.exists():
        link.symlink_to(tree.resolve() / "src", target_is_directory=True)
    return d


def run_campaign(a) -> Path:
    import replay
    import rlm_campaign

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    trees = {k: Path(v).resolve() for k, v in a.trees.items()}
    units = list(a.units) if a.units else plan_units(a.arms, a.repeats, a.once)
    arms = list(dict.fromkeys([arm for arm, _ in [*units, *a.extra_units]]
                              + ([a.warm_arm] if a.warm_arm else [])))
    for arm in arms:
        if arm not in replay.ARMS:
            raise SystemExit(f"unknown arm {arm!r}; choose from {sorted(replay.ARMS)}")
        if replay.ARMS[arm]["tree"] not in trees:
            raise SystemExit(f"arm {arm!r} needs --trees {replay.ARMS[arm]['tree']}=<path>")
    design = None
    if a.design_file:
        text = Path(a.design_file).read_text()
        json.loads(text)  # a design that does not parse stops the run here
        (out / "design.json").write_text(text)
        design = {"file": Path(a.design_file).name,
                  "sha256": hashlib.sha256(text.encode()).hexdigest()}
    camp = open(out / "campaign.jsonl", "a", buffering=1)

    def note(kind: str, **d) -> None:
        camp.write(json.dumps({"t": round(time.time(), 3), "kind": kind, **d}) + "\n")

    base = a.base_url or f"http://localhost:{a.port}/v1"
    note("begin", arms=a.arms, once=a.once, repeats=a.repeats, conc=a.conc, model=a.model,
         base_url=base, sessions=a.sessions, max_minutes=a.max_minutes,
         serve_extra=a.serve_extra, warmup_passes=a.warmup_passes,
         units=[unit_name(arm, a.conc, r) for arm, r in units],
         warm_arm=a.warm_arm, warm_sessions=a.warm_sessions, design=design,
         estimates_s=a.estimates,
         extra_units=[unit_name(arm, a.conc, r) for arm, r in a.extra_units],
         extra_sessions=a.extra_sessions,
         arm_config={arm: replay.ARMS[arm] for arm in arms},
         handler_backlog=a.handler_backlog, launch_delay_ms=a.launch_delay_ms,
         **provenance(trees, Path(a.corpus), a.sessions))
    pkgs = Path(tempfile.mkdtemp(prefix="sptc-replay-pkg-"))
    server = None
    t_begin = time.time()

    def launch_unit(arm: str, rep: int, udir: Path, kind: str = "unit",
                    sessions: list[str] | None = None) -> tuple[bool, float]:
        """One unit in its own process, with its arm's spec-ptc tree on the path."""
        sessions = sessions or a.sessions
        name = udir.name
        tree = trees[replay.ARMS[arm]["tree"]]
        salt = hashlib.sha1(f"{out}{kind}{name}{time.time()}".encode()).hexdigest()[:10]
        env = {k: v for k, v in os.environ.items() if not k.startswith("SPTC_")}
        env.update(PYTHONHASHSEED=HASH_SEED, SPEC_PTC_ROOT=str(tree),
                   PYTHONPATH=os.pathsep.join([str(pkg_dir(tree, pkgs)), str(tree), str(HERE)]),
                   SPTC_ROOT_MAX_DELTAS="0")
        if a.handler_backlog:
            env["SPTC_HANDLER_BACKLOG"] = str(a.handler_backlog)
        if a.launch_delay_ms:
            env["SPTC_REPLAY_LAUNCH_DELAY_MS"] = str(a.launch_delay_ms)
        cmd = [sys.executable, str(HERE / "replay.py"), "unit", "--arm", arm,
               "--corpus", str(a.corpus), "--out", str(udir), "--base-url", base,
               "--model", a.model, "--conc", str(a.conc), "--rep", str(rep),
               "--salt", salt, "--metrics-every", str(a.metrics_every)]
        if sessions:
            cmd += ["--sessions", ",".join(sessions)]
        note(f"{kind}_begin", unit=name, salt=salt, tree=str(tree))
        t0 = time.time()
        udir.mkdir(parents=True, exist_ok=True)
        with open(udir / "unit.log", "a") as log:
            try:
                code = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                      timeout=a.unit_timeout_min * 60).returncode
            except subprocess.TimeoutExpired:
                code = -9
        wall = time.time() - t0
        ok = code == 0 and (udir / "DONE").exists()
        exact = None
        if (udir / "replay.json").exists():
            exact = json.loads((udir / "replay.json").read_text()).get("exact")
        note(f"{kind}_end", unit=name, wall_s=round(wall, 1), exit=code, done=ok, exact=exact)
        label = {"warm_unit": " (thrown away)", "extra_unit": " (extra)"}.get(kind, "")
        print(f"{name}{label}: {wall:.0f} s, exit {code}, "
              f"{'exact' if exact else 'NOT EXACT' if exact is False else 'no result'}",
              flush=True)
        if a.on_unit_done is not None:
            a.on_unit_done(udir)
        return ok, wall

    try:
        if a.launch:
            server = rlm_campaign.Server(a.model, a.port, out / "server.log", a.serve_extra)
            server.start()
            ok = server.wait(a.start_timeout)
            (out / "server.json").write_text(json.dumps(server.facts(), indent=1))
            if not ok:
                note("server_failed")
                raise RuntimeError(f"vLLM did not start; see {out / 'server.log'}")
            note("server_ready", ready_s=server.info.get("ready_s"),
                 kernel_config_dropped=server.info.get("kernel_config_dropped"))
        todo = [(arm, r) for arm, r in units
                if not (out / "units" / unit_name(arm, a.conc, r) / "DONE").exists()]
        extra = [(arm, r) for arm, r in a.extra_units
                 if not (out / "extra" / "units" / unit_name(arm, a.conc, r) / "DONE").exists()]
        if a.warmup_passes and (todo or extra):
            t_w = time.time()
            saved = rlm_campaign.WARMUP_WAVES
            rlm_campaign.WARMUP_WAVES = (*saved, *WIDE_WAVES)
            try:
                waves = rlm_campaign.warmup(base, a.model, a.warmup_passes, note)
            finally:
                rlm_campaign.WARMUP_WAVES = saved
            note("warmup_done", passes=a.warmup_passes, waves=len(waves),
                 wall_s=round(time.time() - t_w, 1), errors=sum(w["errors"] for w in waves))
            print(f"warm-up: {len(waves)} waves in {time.time() - t_w:.0f} s", flush=True)
        if a.warm_arm and todo:
            wdir = out / "warm" / unit_name(a.warm_arm, a.conc, 0)
            if not (wdir / "DONE").exists():
                launch_unit(a.warm_arm, 0, wdir, kind="warm_unit", sessions=a.warm_sessions)
        done_s: dict[str, float] = {}
        for arm, rep in todo:
            name = unit_name(arm, a.conc, rep)
            udir = out / "units" / name
            est = (done_s.get(arm) or float(a.estimates.get(arm) or 0)
                   or (a.unit_estimate_min or 0) * 60)
            spent = time.time() - t_begin
            if a.max_minutes and spent + est > a.max_minutes * 60:
                note("budget_stop", unit=name, spent_s=round(spent), estimate_s=round(est))
                print(f"budget: stop before {name} ({spent / 60:.1f} min spent, "
                      f"~{est / 60:.1f} min more)", flush=True)
                break
            ok, wall = launch_unit(arm, rep, udir)
            if ok:
                done_s[arm] = wall
        for arm, rep in extra:  # after everything registered, and only if the budget allows
            name = unit_name(arm, a.conc, rep)
            est = (float(a.estimates.get(f"extra-{arm}") or 0) or done_s.get(arm)
                   or float(a.estimates.get(arm) or 0) or (a.unit_estimate_min or 0) * 60)
            spent = time.time() - t_begin
            if a.max_minutes and spent + est > a.max_minutes * 60:
                note("budget_stop", unit=f"extra/{name}", spent_s=round(spent),
                     estimate_s=round(est))
                print(f"budget: stop before extra/{name} ({spent / 60:.1f} min spent, "
                      f"~{est / 60:.1f} min more)", flush=True)
                break
            launch_unit(arm, rep, out / "extra" / "units" / name, kind="extra_unit",
                        sessions=a.extra_sessions)
    finally:
        if server is not None:
            (out / "server.json").write_text(json.dumps(server.facts(), indent=1))
            server.stop()
        note("end", spent_s=round(time.time() - t_begin))
        camp.close()
    try:
        import replay_report

        replay_report.write(out)
        if (out / "extra" / "units").is_dir():  # a summary of its own, with no predictions
            (out / "extra" / "design.json").write_text(json.dumps(
                {"name": "extra", "predictions": False, "sessions": a.extra_sessions}))
            replay_report.write(out / "extra")
    except Exception as e:  # noqa: BLE001 - the units are what matters; report offline
        print(f"summary failed: {type(e).__name__}: {e}", flush=True)
    return out


def _kv(s: str) -> dict:
    return dict(x.split("=", 1) for x in s.split(",") if x)


def _units(s: str) -> list[tuple[str, int]]:
    out = []
    for x in s.split(","):
        if x:
            arm, _, rep = x.partition(":")
            out.append((arm, int(rep or 1)))
    return out


def parser() -> argparse.ArgumentParser:
    import rlm_campaign

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--corpus", type=Path, required=True)
    r.add_argument("--sessions", type=lambda s: s.split(","), default=None,
                   help="sessions of the corpus to replay, in this order (default: all)")
    r.add_argument("--arms", type=lambda s: s.split(","), default=["nospec", "stream", "scout",
                                                                  "wide"])
    r.add_argument("--once", type=lambda s: [x for x in s.split(",") if x], default=[],
                   help="arms that run one unit only (controls)")
    r.add_argument("--repeats", type=int, default=2)
    r.add_argument("--units", type=_units, default=[],
                   help="the units in order, as arm:repeat,... (in place of --arms, --repeats "
                        "and --once)")
    r.add_argument("--warm-arm", default="",
                   help="run one unit of this arm first and throw it away (kept under warm/)")
    r.add_argument("--warm-sessions", type=lambda s: [x for x in s.split(",") if x],
                   default=None, help="the sessions of the thrown-away unit (default: --sessions)")
    r.add_argument("--design-file", default="",
                   help="a pre-registered design as JSON (replay_report.prereg_fixed)")
    r.add_argument("--estimates", type=_kv, default={},
                   help="seconds a unit of each arm should take, as arm=seconds,... (the budget "
                        "stop uses them until an arm has run)")
    r.add_argument("--extra-units", type=_units, default=[],
                   help="units that run last, on --extra-sessions, kept under extra/")
    r.add_argument("--extra-sessions", type=lambda s: [x for x in s.split(",") if x],
                   default=None, help="the sessions of the extra units (default: --sessions)")
    r.add_argument("--conc", type=int, default=8)
    r.add_argument("--trees", type=_kv,
                   default={"stock": str(HERE.parents[1] / "spec-ptc"),
                            "fork": str(HERE.parents[1] / "spec-ptc-sptc-hints")})
    r.add_argument("--model", default=rlm_campaign.MODEL)
    r.add_argument("--base-url", default=None)
    r.add_argument("--port", type=int, default=8210)
    r.add_argument("--launch", action="store_true", help="start vLLM with the campaign's flags first")
    r.add_argument("--serve-extra", type=lambda s: s.split(), default=[])
    r.add_argument("--start-timeout", type=float, default=1200)
    r.add_argument("--metrics-every", type=float, default=0.5)
    r.add_argument("--max-minutes", type=float, default=0, help="0: no budget stop")
    r.add_argument("--unit-estimate-min", type=float, default=0)
    r.add_argument("--unit-timeout-min", type=float, default=45)
    r.add_argument("--warmup-passes", type=int, default=0)
    r.add_argument("--handler-backlog", type=int, default=0,
                   help="listen backlog of rlms' LM handler in every arm (0: rlms' own, 5)")
    r.add_argument("--launch-delay-ms", type=float, default=0,
                   help="dry runs only: make each speculative launch take this long, as in a "
                        "busy process (replay.LAUNCH_DELAY_S)")
    s = sub.add_parser("summarize")
    s.add_argument("--out", type=Path, required=True)
    return ap


def main(argv=None) -> None:
    for p in (str(HERE),):
        if p not in sys.path:
            sys.path.insert(0, p)
    a = parser().parse_args(argv)
    if a.cmd == "run":
        a.on_unit_done = None
        run_campaign(a)
        md = Path(a.out) / "summary.md"
        print(md.read_text() if md.exists() else "no summary")
    else:
        import replay_report

        print(replay_report.write(Path(a.out)))


if __name__ == "__main__":
    main()
