#!/usr/bin/env python3
"""Render the three-way comparison into results/<run>/report.md.

Consumes summary.json (from run_compare.py) + scores.json (from score_compare.py) and produces a
single markdown report: run status table, per-regime metric tables, the marginal-value verdict,
and short raw side-by-side excerpts of page 1 from each parser.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PARSER_LABEL = {"odl": "opendataloader-pdf (ODL, deterministic-only)",
                "paddle": "PaddleOCR-VL-1.6 (VLM-only)",
                "pa": "parse-anything (forced --primary paddle, VLM every page)",
                "pa_triaged": "parse-anything (--diagnose, native triage)"}
METRICS = ("pages", "char_sim", "token_f1", "num_recall", "num_halluc", "coverage")


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--scores", required=True)
    ap.add_argument("--pareto", default=None, help="pareto.json (from pareto.py); enables the Pareto section")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)

    summary = json.loads((run_dir / "summary.json").read_text())
    scored = json.loads(Path(args.scores).read_text())
    scores, verdicts = scored["scores"], scored["verdicts"]
    pareto = json.loads(Path(args.pareto).read_text()) if args.pareto and Path(args.pareto).exists() else None

    L = [f"# Three-way PDF parser comparison - `{run_dir.name}`", "",
         "**parse-anything** vs its two raw ingredients: **opendataloader-pdf** (deterministic Java "
         "extractor) and **PaddleOCR-VL-1.6** (document VLM). Ground truth = the born-digital text "
         "layer; `scan.pdf` is that same document rasterized (no text layer), so it isolates the "
         "OCR/VLM regime. Higher is better except `num_halluc` (fabricated numbers, lower better).", ""]

    L += ["## Run status & cost", ""]
    L.append(table(["parser", "doc", "status", "pages", "chars", "wall_s", "cpu_s", "peak_rss_mb",
                    "vlm_calls", "error"],
                   [[r["parser"], r["doc"], r["status"], r["n_pages"], r["n_chars"], r["seconds"],
                     r.get("cpu_s", "-"), r.get("peak_rss_mb", "-"), r.get("vlm_calls", "-"),
                     r.get("error", "")] for r in summary]))
    L.append("")

    for doc in ("born", "scan"):
        L += [f"## {doc} regime", ""]
        rows = []
        for parser in ("odl", "paddle", "pa"):
            s = scores.get(f"{parser}/{doc}")
            if not s:
                rows.append([PARSER_LABEL[parser], *(["-"] * len(METRICS))])
                continue
            rows.append([PARSER_LABEL[parser], *[s.get(m, "-") for m in METRICS]])
        L.append(table(["parser", *METRICS], rows))
        v = verdicts.get(doc, {})
        L += ["", f"**Verdict:** `{v.get('verdict','?')}` — winner **{v.get('winner','?')}**, "
              f"margin {v.get('margin','?')} ({v.get('detail','')})", ""]

    # cost vs quality + Pareto frontier
    if pareto:
        qm = pareto.get("quality_metric", "num_recall")
        L += ["## Cost vs quality (Pareto)", "",
              f"Quality axis = `{qm}` (higher better). Cost axes: `wall_s`, `vlm_calls` ($ proxy), "
              "`cpu_s`, `peak_rss_mb` (all lower better). A parser is **on the frontier** if no other "
              "parser gives more quality at equal-or-lower cost. parse-anything is only worth its "
              "orchestration overhead where it stays on the frontier.", ""]
        for doc, reg in pareto["regimes"].items():
            L += [f"### {doc}", ""]
            rows = []
            for p in reg["points"]:
                parser = p["name"].split("/")[0]
                rows.append([PARSER_LABEL.get(parser, parser), p["quality"], p["token_f1"],
                             p["seconds"], p["vlm_calls"], p["cpu_s"], p["peak_rss_mb"],
                             "yes" if p["on_frontier"] else "-"])
            L.append(table([f"parser", qm, "token_f1", "wall_s", "vlm_calls", "cpu_s",
                            "peak_rss_mb", "on_frontier"], rows))
            fronts = reg["frontier"]
            L += ["", f"Frontier by wall_s: **{', '.join(fronts.get('seconds', [])) or '-'}**; "
                  f"by vlm_calls: **{', '.join(fronts.get('vlm_calls', [])) or '-'}**.",
                  f"Plots: `pareto_{doc}_seconds.svg`, `pareto_{doc}_vlm_calls.svg`.", ""]

    # raw page-1 excerpts
    L += ["## Raw page-1 excerpts", ""]
    for parser in ("odl", "paddle", "pa"):
        for doc in ("born", "scan"):
            pj = run_dir / parser / doc / "pages.json"
            if not pj.exists():
                continue
            pages = json.loads(pj.read_text())
            excerpt = (pages[0][:600] if pages else "(no output)").replace("\n", " ")
            L += [f"### {parser} / {doc}", "", "```", excerpt, "```", ""]

    (run_dir / "report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {run_dir/'report.md'}")


if __name__ == "__main__":
    main()
