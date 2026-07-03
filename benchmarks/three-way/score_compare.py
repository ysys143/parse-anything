#!/usr/bin/env python3
"""Score the three parsers head-to-head against the born-digital text layer.

Reuses the OCR-sweep metric primitives (normalize / tokens / numbers / token_f1) so the numbers
are directly comparable to the existing sweep. Ground truth = born.pdf text layer, per page; the
scan is the SAME document rasterized, so the born text layer scores both regimes.

Input: a results tree written by run_compare.py --
  results/<run>/<parser>/<doc>/pages.json   (list[str], one markdown string per page)
  results/<run>/<parser>/<doc>/meta.json    (RunResult dict)

Output: per (parser, doc) metric rows + the marginal-value verdict.
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ocr-sweep"))
from score import normalize, numbers, token_f1, tokens  # noqa: E402  reuse sweep primitives

import pypdfium2 as pdfium  # noqa: E402


def gt_pages(pdf_path: str) -> list[str]:
    doc = pdfium.PdfDocument(pdf_path)
    return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]


def score_pages(out_pages: list[str], gt_norm: list[str], gt_tok: list[list[str]],
                gt_num: list[set]) -> dict | None:
    """Score a parser's per-page markdown against GT. If page counts differ (ODL may emit a
    single blob), we align on min length and fall back to whole-doc scoring for blob output."""
    if not out_pages:
        return None
    sims, f1s, recs, halls, covs = [], [], [], [], []
    n = min(len(out_pages), len(gt_norm))
    if len(out_pages) == 1 and len(gt_norm) > 1:
        # single-blob output: score against the concatenated GT (whole-doc fidelity)
        gt_all = normalize(" ".join(gt_norm))
        gt_all_tok = tokens(gt_all)
        gt_all_num = set().union(*gt_num) if gt_num else set()
        pairs = [(normalize(out_pages[0]), gt_all, gt_all_tok, gt_all_num)]
    else:
        pairs = [(normalize(out_pages[i]), gt_norm[i], gt_tok[i], gt_num[i]) for i in range(n)]
    for out_norm, g_norm, g_tok, g_num in pairs:
        out_tok, out_num = tokens(out_norm), numbers(out_norm)
        sims.append(difflib.SequenceMatcher(None, g_norm, out_norm).ratio())
        f1s.append(token_f1(g_tok, out_tok))
        recs.append(len(g_num & out_num) / len(g_num) if g_num else 1.0)
        halls.append(len(out_num - g_num) / len(out_num) if out_num else 0.0)
        covs.append(len(out_tok) / len(g_tok) if g_tok else 0.0)
    avg = lambda xs: round(sum(xs) / len(xs), 3)
    return {"pages": len(sims), "char_sim": avg(sims), "token_f1": avg(f1s),
            "num_recall": avg(recs), "num_halluc": avg(halls), "coverage": avg(covs)}


def load_results(run_dir: Path) -> dict[tuple[str, str], dict]:
    """(parser, doc) -> {'meta':..., 'pages':[...]}"""
    out: dict[tuple[str, str], dict] = {}
    for pages_file in run_dir.glob("*/*/pages.json"):
        parser, doc = pages_file.parent.parent.name, pages_file.parent.name
        meta = json.loads((pages_file.parent / "meta.json").read_text()) if (pages_file.parent / "meta.json").exists() else {}
        out[(parser, doc)] = {"meta": meta, "pages": json.loads(pages_file.read_text())}
    return out


# ===========================================================================
# VERDICT: does parse-anything's orchestration add measurable value?
# ---------------------------------------------------------------------------
# TODO(user contribution) -- implement `marginal_value_verdict` below.
#
# You have, per document regime (born / scan), the scored metrics for all three parsers:
#   scores[("odl", doc)]    -- deterministic extractor alone
#   scores[("paddle", doc)] -- VLM alone
#   scores[("pa", doc)]     -- full pipeline
# each a dict: {char_sim, token_f1, num_recall, num_halluc, coverage, pages}.
#
# The design decision that matters: how do you DECLARE that orchestration "wins"? Options to weigh:
#   - Which metric is the arbiter? (num_recall is document-critical -- fabricated/omitted numbers
#     are the worst failure; char_sim rewards order fidelity; token_f1 is order-insensitive recall.)
#   - "Wins" vs the BEST ingredient (max(odl, paddle)) or vs EACH? The honest bar is: pa must beat
#     max(odl, paddle) -- otherwise the orchestration isn't buying anything you couldn't get raw.
#   - How big a delta counts as real vs noise? (a margin threshold, e.g. >= 0.02)
#   - Should num_halluc be a veto? (a parser that scores high but fabricates numbers should not win.)
# ===========================================================================
def marginal_value_verdict(scores: dict[tuple[str, str], dict], doc: str) -> dict:
    """Return {'verdict': str, 'winner': str, 'margin': float, 'detail': str} for one doc regime.

    Placeholder: compares parse-anything to the best raw ingredient on num_recall with a 0.02
    margin and a num_halluc veto. Replace with your own arbiter/threshold policy.
    """
    pa = scores.get(("pa", doc))
    odl = scores.get(("odl", doc))
    paddle = scores.get(("paddle", doc))
    if not pa:
        return {"verdict": "n/a", "winner": "-", "margin": 0.0, "detail": "parse-anything missing"}
    ARBITER, MARGIN, HALLUC_VETO = "num_recall", 0.02, 0.15
    ingredients = {k: v for k, v in (("odl", odl), ("paddle", paddle)) if v}
    if not ingredients:
        return {"verdict": "pa_only", "winner": "pa", "margin": 0.0,
                "detail": "no ingredient scored"}
    best_name = max(ingredients, key=lambda k: ingredients[k][ARBITER])
    best = ingredients[best_name][ARBITER]
    margin = round(pa[ARBITER] - best, 3)
    if pa["num_halluc"] > HALLUC_VETO:
        return {"verdict": "pa_vetoed", "winner": best_name, "margin": margin,
                "detail": f"pa num_halluc={pa['num_halluc']} > {HALLUC_VETO}"}
    if margin >= MARGIN:
        verdict, winner = "orchestration_adds_value", "pa"
    elif margin <= -MARGIN:
        verdict, winner = "ingredient_better", best_name
    else:
        verdict, winner = "tie", "pa" if pa[ARBITER] >= best else best_name
    return {"verdict": verdict, "winner": winner, "margin": margin,
            "detail": f"pa {ARBITER}={pa[ARBITER]} vs best({best_name})={best}"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="results/<run> tree from run_compare.py")
    ap.add_argument("--born", required=True, help="born-digital ground-truth PDF")
    ap.add_argument("--out", required=True, help="scores JSON output")
    args = ap.parse_args()

    gt = gt_pages(args.born)
    gt_norm = [normalize(t) for t in gt]
    gt_tok = [tokens(t) for t in gt_norm]
    gt_num = [numbers(t) for t in gt_norm]

    results = load_results(Path(args.run_dir))
    scores: dict[tuple[str, str], dict] = {}
    for (parser, doc), payload in results.items():
        s = score_pages(payload["pages"], gt_norm, gt_tok, gt_num)
        if s:
            s["status"] = payload["meta"].get("status", "?")
            s["seconds"] = payload["meta"].get("seconds", 0)
            scores[(parser, doc)] = s

    verdicts = {doc: marginal_value_verdict(scores, doc) for doc in ("born", "scan")}
    payload = {"scores": {f"{p}/{d}": v for (p, d), v in scores.items()}, "verdicts": verdicts}
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
