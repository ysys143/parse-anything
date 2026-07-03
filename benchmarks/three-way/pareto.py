#!/usr/bin/env python3
"""Cost-vs-quality Pareto analysis for the three-way comparison.

Joins cost (summary.json: wall_s, cpu_s, peak_rss_mb, vlm_calls) with quality (scores.json:
num_recall, token_f1, ...) per (parser, doc), then per regime computes the Pareto frontier and
reports dominance. The question this answers: is parse-anything's orchestration Pareto-optimal --
does the extra cost buy quality that the raw ingredients can't reach at the same cost?

Dominance (for a quality metric Q higher-better and a cost metric C lower-better):
  A dominates B  iff  Q_A >= Q_B and C_A <= C_B, with at least one strict.
The FRONTIER = points no other point dominates. A parser off the frontier is strictly worse:
someone gives more quality for less (or equal) cost.

Writes pareto.json + one SVG scatter per (regime, cost-axis). stdlib only.
Usage:
  python pareto.py --run-dir results/<run> --scores results/<run>/scores.json \
      [--quality num_recall] [--out results/<run>/pareto.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

COST_AXES = ("seconds", "vlm_calls", "cpu_s", "peak_rss_mb")
COST_LABEL = {"seconds": "wall-clock s", "vlm_calls": "VLM calls ($ proxy)",
              "cpu_s": "CPU s", "peak_rss_mb": "peak RSS MB"}
PLOT_AXES = ("seconds", "vlm_calls")   # the two most decision-relevant cost axes
PARSER_COLOR = {"odl": "#2a7", "paddle": "#e6a", "pa": "#38d"}


def load_cost(run_dir: Path) -> dict[tuple[str, str], dict]:
    summary = json.loads((run_dir / "summary.json").read_text())
    return {(r["parser"], r["doc"]): r for r in summary}


def dominates(a: dict, b: dict, c: str) -> bool:
    """a dominates b on (quality higher-better, cost c lower-better)."""
    ge_q, le_c = a["quality"] >= b["quality"], a[c] <= b[c]
    strict = a["quality"] > b["quality"] or a[c] < b[c]
    return ge_q and le_c and strict


def frontier(points: list[dict], c: str) -> list[str]:
    """Names of non-dominated points on the (quality, c) plane."""
    front = []
    for p in points:
        if not any(dominates(o, p, c) for o in points if o is not p):
            front.append(p["name"])
    return front


def svg_scatter(points: list[dict], cost_axis: str, quality: str, title: str) -> str:
    """Minimal dependency-free SVG: quality (y, up=better) vs cost (x, right=more expensive)."""
    W, H, pad = 460, 320, 60
    xs = [p[cost_axis] for p in points] or [0]
    ys = [p["quality"] for p in points] or [0]
    xmin, xmax = min(xs + [0]), max(xs + [1e-9])
    ymin, ymax = min(ys + [0]), max(ys + [1e-9])
    xr = xmax - xmin or 1.0
    yr = ymax - ymin or 1.0

    def sx(v: float) -> float:
        return pad + (v - xmin) / xr * (W - 2 * pad)

    def sy(v: float) -> float:
        return H - pad - (v - ymin) / yr * (H - 2 * pad)

    el = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="sans-serif" font-size="11">',
          f'<text x="{W/2}" y="18" text-anchor="middle" font-size="13" font-weight="bold">{title}</text>',
          f'<line x1="{pad}" y1="{H-pad}" x2="{W-pad}" y2="{H-pad}" stroke="#888"/>',
          f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{H-pad}" stroke="#888"/>',
          f'<text x="{W/2}" y="{H-20}" text-anchor="middle">{COST_LABEL[cost_axis]} -> more expensive</text>',
          f'<text x="16" y="{H/2}" text-anchor="middle" transform="rotate(-90 16 {H/2})">{quality} -> better</text>']
    for p in points:
        cx, cy = sx(p[cost_axis]), sy(p["quality"])
        color = PARSER_COLOR.get(p["parser"], "#666")
        ring = ' stroke="#000" stroke-width="2"' if p["on_frontier"] else ''
        el.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="{color}"{ring}/>')
        el.append(f'<text x="{cx+10:.1f}" y="{cy+4:.1f}">{p["parser"]}</text>')
    el.append('<text x="%d" y="%d" font-size="10" fill="#555">O = on Pareto frontier</text>' % (pad, pad-8))
    el.append('</svg>')
    return "\n".join(el)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--scores", required=True)
    ap.add_argument("--quality", default="num_recall",
                    help="quality metric to use as the Pareto y-axis (higher better)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    cost = load_cost(run_dir)
    quality = json.loads(Path(args.scores).read_text())["scores"]  # {"pa/born": {...}}

    regimes: dict[str, list[dict]] = {"born": [], "scan": []}
    for key, qmetrics in quality.items():
        parser, doc = key.split("/")
        c = cost.get((parser, doc), {})
        pt = {"name": key, "parser": parser, "doc": doc,
              "quality": qmetrics.get(args.quality, 0.0),
              "token_f1": qmetrics.get("token_f1", 0.0),
              "seconds": c.get("seconds", 0.0), "cpu_s": c.get("cpu_s", 0.0),
              "peak_rss_mb": c.get("peak_rss_mb", 0.0), "vlm_calls": c.get("vlm_calls", 0),
              "on_frontier": False}
        regimes.setdefault(doc, []).append(pt)

    result: dict = {"quality_metric": args.quality, "regimes": {}}
    for doc, pts in regimes.items():
        if not pts:
            continue
        # a point is "on the frontier" if it's non-dominated on ANY plotted cost axis
        fronts = {c: frontier(pts, c) for c in PLOT_AXES}
        on_any = set().union(*fronts.values())
        for p in pts:
            p["on_frontier"] = p["name"] in on_any
        for cost_axis in PLOT_AXES:
            svg = svg_scatter(pts, cost_axis, args.quality, f"{doc}: {args.quality} vs {COST_LABEL[cost_axis]}")
            (run_dir / f"pareto_{doc}_{cost_axis}.svg").write_text(svg, encoding="utf-8")
        result["regimes"][doc] = {
            "frontier": fronts,
            "points": [{k: p[k] for k in ("name", "quality", "token_f1", "seconds", "cpu_s",
                                          "peak_rss_mb", "vlm_calls", "on_frontier")} for p in pts],
        }

    out = Path(args.out or run_dir / "pareto.json")
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nwrote {out} + pareto_<doc>_<axis>.svg")


if __name__ == "__main__":
    main()
