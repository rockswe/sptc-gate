"""Static figures for the write-up (PNG). The palette is a fixed categorical order
that stays distinguishable under colour-vision deficiency (adjacent CVD dE >= 9.1,
normal-vision >= 19.6 on the light surface). Three slots sit under 3:1 contrast, so
every series is also direct-labeled and carries a marker shape, and each figure has
a table."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
MARKERS = ["o", "s", "^", "D", "v", "P"]


def _style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=10)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.tick_params(colors=INK2, labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _fig(ncols: int = 1, w: float = 6.4, h: float = 3.8):
    fig, axes = plt.subplots(1, ncols, figsize=(w * ncols, h), squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    return fig, axes[0]


def _lines(ax, groups: dict, logx: bool = False, label_last: bool = True,
           legend: bool = True) -> None:
    """groups: name -> (xs, ys), in fixed series order. Direct labels only for
    <= 4 series (more would collide); the legend is always there for >= 2."""
    label_last = label_last and len(groups) <= 4
    ends = []
    for i, (name, (xs, ys)) in enumerate(groups.items()):
        c = SERIES[i % len(SERIES)]
        ax.plot(xs, ys, color=c, linewidth=2, marker=MARKERS[i % len(MARKERS)],
                markersize=5, markeredgecolor=SURFACE, markeredgewidth=1, label=name)
        if label_last and len(xs):
            ends.append((name, xs[-1], ys[-1]))
    if ends:
        _place_labels(ax, ends)
    if logx:
        ax.set_xscale("log", base=2)
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    if legend and len(groups) >= 2:
        ax.legend(frameon=False, fontsize=7, labelcolor=INK2)


NAMES = {"shadow": "spec-ptc", "dataflow": "never-stall shadow", "literal": "literal-only",
         "baseline": "no speculation", "shadow+waste0.5": "spec-ptc + 0.5 bad guesses",
         "shadow+waste1": "spec-ptc + 1 bad guess"}


def _place_labels(ax, ends, min_gap_px: float = 11.0) -> None:
    """Direct labels at line ends, nudged apart vertically so none collide."""
    lo, hi = ax.get_xlim()
    ax.set_xlim(lo, hi + 0.45 * (hi - lo))  # room for the labels
    fig = ax.figure
    fig.canvas.draw()
    to_px, to_data = ax.transData, ax.transData.inverted()
    pts = sorted(((to_px.transform((x, y))[1], name, x, y) for name, x, y in ends))
    placed = []
    for py, name, x, y in pts:
        if placed and py - placed[-1][0] < min_gap_px:
            py = placed[-1][0] + min_gap_px
        placed.append((py, name, x, y))
    for py, name, x, y in placed:
        px = to_px.transform((x, y))[0]
        ax.text(x, to_data.transform((px, py))[1], "  " + name, fontsize=7, color=INK2,
                va="center", ha="left")


def calibration(res: Path) -> Path:
    cal = json.loads((res / "calibration.json").read_text())["loo"]
    names = sorted(cal, key=lambda n: cal[n]["spec_wall_meas"])
    fig, (ax,) = _fig(w=7.5, h=6.0)
    for i, n in enumerate(names):
        r = cal[n]
        ax.plot([r["spec_wall_min"], r["spec_wall_max"]], [i, i], color=GRID, linewidth=6,
                solid_capstyle="round")
        ax.plot(r["spec_wall_meas"], i, "o", color=SERIES[0], markersize=6,
                label="measured median (vLLM)" if i == 0 else None)
        ax.plot(r["spec_wall_sim"], i, "D", color=SERIES[1], markersize=5,
                label="simulated, leave-one-out" if i == 0 else None)
    ax.set_yticks(range(len(names)), names, fontsize=7)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"{v:g}" if v in (1.5, 2, 3, 4, 6) else ""))
    _style(ax, "spec-ptc suite, speculative wall time: measured vs simulated",
           "wall time (s, log); gray bar = min-max of 5 measured reps", "")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower right")
    fig.tight_layout()
    out = res / "fig_calibration.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def stepcost(res: Path, ctx: int = 8000) -> Path:
    df = pd.read_csv(res / "freeride_stepcost.csv")
    df = df[(df.batch > 0) & (df.ctx == ctx) & (df.batch * ctx <= df.kv_capacity)]
    fig, (ax,) = _fig(w=7.2)
    groups = {cfg: (g.batch.tolist(), g.ratio.tolist()) for cfg, g in df.groupby("config", sort=False)}
    _lines(ax, groups, logx=True)
    ax.annotate("1.5x", (1, 1.5), xytext=(2, 3), textcoords="offset points", fontsize=7,
                color=INK2)
    ax.axhline(1.5, color=INK2, linewidth=0.8, linestyle=":")
    _style(ax, f"Decode step time vs batch size (each sequence {ctx // 1000}k tokens of context)",
           "sequences in the batch (log2; only batches whose KV fits)",
           "step time / batch-1 step time")
    fig.tight_layout()
    out = res / "fig_stepcost.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def marginal(res: Path) -> Path:
    df = pd.read_csv(res / "freeride_sim.csv")
    cfgs = list(dict.fromkeys(df.config))
    fig, axes = _fig(ncols=len(cfgs), w=3.6, h=3.4)
    for i, (ax, cfg) in enumerate(zip(axes, cfgs, strict=True)):
        g = df[(df.config == cfg) & df.marginal_vs_solo.notna()]
        groups = {f"{int(c) // 4}-token prompts": (h.k.tolist(), h.marginal_vs_solo.tolist())
                  for c, h in g.groupby("chunk_chars")}
        _lines(ax, groups, logx=True, label_last=False, legend=(i == 0))
        ax.axhline(0.5, color=INK2, linewidth=0.8, linestyle=":")
        _style(ax, cfg.replace(" graphs", "").replace(" (calibrated)", ""),
               "sub-calls already in flight (k)", "added time of call k+1 / solo call" if i == 0 else "")
        ax.set_ylim(0, max(0.62, 1.1 * float(df.marginal_vs_solo.max())))
    fig.tight_layout()
    out = res / "fig_marginal.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def load_sweep(res: Path, csv: str, metric: str, ylabel: str, title: str, out_name: str,
               policies: list[str], scheds=("fcfs", "agent"), scale: float = 1.0,
               kv: str = "lru") -> Path:
    df = pd.read_csv(res / csv)
    df = df[df.kv == kv] if "kv" in df else df
    fig, axes = _fig(ncols=len(scheds), w=5.6, h=4.0)
    ymax = 0
    for ax, sched in zip(axes, scheds, strict=True):
        groups = {}
        for p in policies:
            src = "agent" if (p == "baseline" and sched == "agent-naive") else sched
            g = df[(df.policy == p) & (df.sched == src)].groupby("rate")[metric].median()
            if len(g):
                groups[NAMES.get(p, p)] = (g.index.tolist(), (g * scale).tolist())
                ymax = max(ymax, float((g * scale).max()))
        _lines(ax, groups, label_last=False)
        ax._sptc_ends = [(n, xs[-1], ys[-1]) for n, (xs, ys) in groups.items() if len(xs)]
        label = {"fcfs": "vLLM FCFS", "agent-naive": "deprioritize all speculation",
                 "agent": "confidence-aware admission"}[sched]
        _style(ax, f"{title} ({label})",
               "session arrival rate (sessions/s)", ylabel)
    rates = sorted(df.rate.unique())
    for ax in axes:
        ax.set_ylim(0, ymax * 1.08)
        ax.set_xticks(rates, [f"{r:g}" for r in rates], fontsize=7)
    fig.tight_layout()
    for ax in axes:
        if len(ax._sptc_ends) <= 4:
            _place_labels(ax, ax._sptc_ends)
    out = res / out_name
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def sweep(res: Path) -> Path:
    df = pd.read_csv(res / "sweep_summary.csv")
    fig, (ax,) = _fig(w=6.8)
    groups = {}
    for d in ["get_file", "code_search", "all Copilot tools", "run_command_in_terminal"]:
        g = df[df.dist == d].sort_values("tpot_ms")
        groups[d] = (g.tpot_ms.tolist(), g.p50.tolist())
    _lines(ax, groups, logx=True)
    _style(ax, "spec-ptc speedup on the 22 suite programs, by decode speed and tool class",
           "root model time per output token (ms, log2)", "median speedup over baseline")
    ax.set_ylim(1.0, None)
    fig.tight_layout()
    out = res / "fig_sweep.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out
