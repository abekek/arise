"""Generate publication-ready figures from ARISE benchmark result JSON files.

Usage:
    python benchmarks/plot_results.py benchmarks/results/*.json --output figures/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ---------------------------------------------------------------------------
# Matplotlib styling
# ---------------------------------------------------------------------------

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "legend.fontsize": 10,
    "figure.figsize": (8, 5),
    "figure.dpi": 150,
    "savefig.dpi": 300,
})

# savefig.bbox_inches is not recognised by all matplotlib versions;
# we pass it explicitly in each savefig call instead.
_SAVEFIG_KWARGS: dict[str, Any] = {"bbox_inches": "tight"}

# Mode → color mapping
MODE_COLORS: dict[str, str] = {
    "arise": "#1f77b4",        # blue
    "no-evolution": "#d62728", # red
    "fixed-tools": "#2ca02c",  # green
}

PHASE_BOUNDARIES = [15, 30, 45]
PHASE_BOUNDARY_LABELS = ["Phase 2", "Phase 3", "Phase 4"]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_result(path: str | Path) -> dict[str, Any]:
    with open(path) as fh:
        return json.load(fh)


def label_for(result: dict[str, Any]) -> str:
    return f"{result['model']} ({result['mode']})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rolling_success(episodes: list[dict[str, Any]], window: int = 5) -> tuple[list[int], list[float]]:
    """Return (episode_numbers, rolling_success_rates)."""
    successes = [int(e["success"]) for e in episodes]
    xs = [e["episode"] for e in episodes]
    rates: list[float] = []
    for i in range(len(successes)):
        start = max(0, i - window + 1)
        rates.append(float(np.mean(successes[start : i + 1])))
    return xs, rates


def phase_success_rates(result: dict[str, Any]) -> dict[str, float]:
    """Return phase success rates dict (keys as strings '1'..'4')."""
    # Prefer summary field if present and populated
    psr = result.get("summary", {}).get("phase_success_rates", {})
    if psr:
        return {str(k): float(v) for k, v in psr.items()}
    # Fall back: compute from episodes
    phase_map: dict[str, list[int]] = {}
    for ep in result.get("episodes", []):
        phase = str(ep.get("phase", "?"))
        phase_map.setdefault(phase, []).append(int(ep["success"]))
    return {p: float(np.mean(vs)) for p, vs in phase_map.items()}


def overall_success(result: dict[str, Any]) -> float:
    sr = result.get("summary", {}).get("total_success_rate")
    if sr is not None:
        return float(sr)
    successes = [int(e["success"]) for e in result.get("episodes", [])]
    return float(np.mean(successes)) if successes else 0.0


def total_skills(result: dict[str, Any]) -> int:
    ts = result.get("summary", {}).get("total_skills")
    if ts is not None:
        return int(ts)
    # Derive from last episode skills_count
    episodes = result.get("episodes", [])
    if episodes:
        return int(episodes[-1].get("skills_count", 0))
    return 0


def _add_phase_boundaries(ax: plt.Axes, ymax: float = 1.0) -> None:
    for x, lbl in zip(PHASE_BOUNDARIES, PHASE_BOUNDARY_LABELS):
        ax.axvline(x=x, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
        ax.text(
            x + 0.4,
            ymax * 0.97,
            lbl,
            fontsize=8,
            color="gray",
            va="top",
        )


# ---------------------------------------------------------------------------
# Figure 1: learning_curve.pdf
# ---------------------------------------------------------------------------

def plot_learning_curve(results: list[dict[str, Any]], output_dir: Path) -> None:
    fig, ax = plt.subplots()

    for result in results:
        mode = result.get("mode", "arise")
        color = MODE_COLORS.get(mode, "#7f7f7f")
        label = label_for(result)
        xs, rates = rolling_success(result.get("episodes", []))
        ax.plot(xs, rates, label=label, color=color, linewidth=1.8)

    _add_phase_boundaries(ax)
    ax.set_title("Agent Success Rate Over Episodes")
    ax.set_xlabel("Episode")
    ax.set_ylabel("Success Rate")
    ax.set_ylim(0, 1.05)
    ax.legend(loc="upper left")
    ax.grid(axis="y", alpha=0.3)

    out = output_dir / "learning_curve.pdf"
    fig.savefig(out, **_SAVEFIG_KWARGS)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 2: tool_accumulation.pdf
# ---------------------------------------------------------------------------

def plot_tool_accumulation(results: list[dict[str, Any]], output_dir: Path) -> None:
    arise_results = [r for r in results if r.get("mode") == "arise"]
    if not arise_results:
        return

    fig, ax = plt.subplots()

    key_episode_fractions = [0.25, 0.5, 0.75, 1.0]

    for result in arise_results:
        episodes = result.get("episodes", [])
        if not episodes:
            continue
        label = label_for(result)
        xs = [e["episode"] for e in episodes]
        ys = [e.get("skills_count", 0) for e in episodes]
        ax.plot(xs, ys, label=label, linewidth=1.8)

        # Annotate at key points
        n = len(episodes)
        for frac in key_episode_fractions:
            idx = min(int(frac * n) - 1, n - 1)
            if idx < 0:
                continue
            ep = episodes[idx]
            skill_val = ep.get("skills_count", 0)
            ax.annotate(
                str(skill_val),
                xy=(ep["episode"], skill_val),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=8,
                color="gray",
            )

    _add_phase_boundaries(ax, ymax=max(
        (e.get("skills_count", 0) for r in arise_results for e in r.get("episodes", [])),
        default=1,
    ))
    ax.set_title("Tool Library Growth")
    ax.set_xlabel("Episode")
    ax.set_ylabel("Active Skill Count")
    ax.legend(loc="upper left")
    ax.grid(axis="y", alpha=0.3)

    out = output_dir / "tool_accumulation.pdf"
    fig.savefig(out, **_SAVEFIG_KWARGS)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 3: model_comparison.pdf
# ---------------------------------------------------------------------------

def plot_model_comparison(results: list[dict[str, Any]], output_dir: Path) -> None:
    arise_results = [r for r in results if r.get("mode") == "arise"]
    if not arise_results:
        return

    fig, ax = plt.subplots()

    color_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for i, result in enumerate(arise_results):
        color = color_cycle[i % len(color_cycle)]
        label = result.get("model", "unknown")
        xs, rates = rolling_success(result.get("episodes", []))
        ax.plot(xs, rates, label=label, color=color, linewidth=1.8)

    _add_phase_boundaries(ax)
    ax.set_title("Model Comparison (with ARISE)")
    ax.set_xlabel("Episode")
    ax.set_ylabel("Success Rate")
    ax.set_ylim(0, 1.05)
    ax.legend(loc="upper left")
    ax.grid(axis="y", alpha=0.3)

    out = output_dir / "model_comparison.pdf"
    fig.savefig(out, **_SAVEFIG_KWARGS)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 4: phase_breakdown.pdf
# ---------------------------------------------------------------------------

def plot_phase_breakdown(results: list[dict[str, Any]], output_dir: Path) -> None:
    phases = ["1", "2", "3", "4"]
    n_results = len(results)
    if n_results == 0:
        return

    x = np.arange(len(phases))
    bar_width = 0.8 / n_results

    fig, ax = plt.subplots()

    for i, result in enumerate(results):
        mode = result.get("mode", "arise")
        color = MODE_COLORS.get(mode, "#7f7f7f")
        label = label_for(result)
        psr = phase_success_rates(result)
        heights = [psr.get(p, 0.0) for p in phases]
        offset = (i - n_results / 2 + 0.5) * bar_width
        ax.bar(x + offset, heights, width=bar_width, label=label, color=color, alpha=0.85)

    ax.set_title("Success Rate by Phase")
    ax.set_xlabel("Phase")
    ax.set_ylabel("Success Rate")
    ax.set_xticks(x)
    ax.set_xticklabels([f"Phase {p}" for p in phases])
    ax.set_ylim(0, 1.1)
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)

    out = output_dir / "phase_breakdown.pdf"
    fig.savefig(out, **_SAVEFIG_KWARGS)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

TableRow = tuple[str, str, float, float, float, float, float, int]


def build_rows(results: list[dict[str, Any]]) -> list[TableRow]:
    rows: list[TableRow] = []
    for result in results:
        model = result.get("model", "unknown")
        mode = result.get("mode", "unknown")
        psr = phase_success_rates(result)
        p1 = psr.get("1", 0.0)
        p2 = psr.get("2", 0.0)
        p3 = psr.get("3", 0.0)
        p4 = psr.get("4", 0.0)
        overall = overall_success(result)
        tools = total_skills(result)
        rows.append((model, mode, p1, p2, p3, p4, overall, tools))
    return rows


def write_summary_table_txt(rows: list[TableRow], output_dir: Path) -> None:
    header = f"{'Model':<20}{'Mode':<16}{'Phase1':>8}{'Phase2':>8}{'Phase3':>8}{'Phase4':>8}{'Overall':>9}{'Tools':>7}"
    sep = "-" * len(header)
    lines = [header, sep]
    for model, mode, p1, p2, p3, p4, overall, tools in rows:
        lines.append(
            f"{model:<20}{mode:<16}{p1:>8.2f}{p2:>8.2f}{p3:>8.2f}{p4:>8.2f}{overall:>9.2f}{tools:>7}"
        )
    text = "\n".join(lines) + "\n"
    out = output_dir / "summary_table.txt"
    out.write_text(text)


def write_summary_table_tex(rows: list[TableRow], output_dir: Path) -> None:
    lines = [
        r"\begin{table}[ht]",
        r"  \centering",
        r"  \caption{ARISE Benchmark Results}",
        r"  \label{tab:arise_results}",
        r"  \begin{tabular}{llrrrrrr}",
        r"    \toprule",
        r"    Model & Mode & Phase 1 & Phase 2 & Phase 3 & Phase 4 & Overall & Tools \\",
        r"    \midrule",
    ]
    for model, mode, p1, p2, p3, p4, overall, tools in rows:
        model_esc = model.replace("_", r"\_")
        mode_esc = mode.replace("-", r"\mbox{-}")
        lines.append(
            f"    {model_esc} & {mode_esc} & {p1:.2f} & {p2:.2f} & {p3:.2f} & {p4:.2f} & {overall:.2f} & {tools} \\\\"
        )
    lines += [
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}",
        "",
    ]
    out = output_dir / "summary_table.tex"
    out.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def print_summary(rows: list[TableRow], output_dir: Path) -> None:
    print("=== ARISE Benchmark Results ===\n")
    header = f"{'Model':<20}{'Mode':<16}{'Phase1':>8}{'Phase2':>8}{'Phase3':>8}{'Phase4':>8}{'Overall':>9}{'Tools':>7}"
    print(header)
    print("-" * len(header))
    for model, mode, p1, p2, p3, p4, overall, tools in rows:
        print(f"{model:<20}{mode:<16}{p1:>8.2f}{p2:>8.2f}{p3:>8.2f}{p4:>8.2f}{overall:>9.2f}{tools:>7}")
    print(f"\nFigures saved to: {output_dir}/")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate publication-ready figures from ARISE benchmark result JSON files."
    )
    parser.add_argument(
        "result_files",
        nargs="+",
        metavar="RESULT_JSON",
        help="One or more result JSON files.",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/figures/",
        metavar="DIR",
        help="Output directory for figures (default: benchmarks/figures/).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for path in args.result_files:
        try:
            results.append(load_result(path))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: could not load {path}: {exc}", file=sys.stderr)

    if not results:
        print("No valid result files loaded. Exiting.", file=sys.stderr)
        sys.exit(1)

    plot_learning_curve(results, output_dir)
    plot_tool_accumulation(results, output_dir)
    plot_model_comparison(results, output_dir)
    plot_phase_breakdown(results, output_dir)

    rows = build_rows(results)
    write_summary_table_txt(rows, output_dir)
    write_summary_table_tex(rows, output_dir)

    print_summary(rows, output_dir)


if __name__ == "__main__":
    main()
