#!/usr/bin/env python3
"""Objective scoring (axis A) for the OCR sweep.

Ground truth = the BORN-DIGITAL document.pdf text layer (pypdfium2), per page. Because scan.pdf is
that same document rasterized, the born text layer scores BOTH docs. We score each model's RAW
per-page output (raw_<doc>/<model>/NNNN.md, seq N -> page N-1) against the GT page text.

Metrics per model/doc (averaged over pages):
  char_sim   difflib ratio of normalized text        (order-sensitive fidelity)
  token_f1   word-set F1 of normalized text          (order-INSENSITIVE: did it read the words)
  num_recall fraction of GT numbers present in output (>= 4 digits; document-critical)
  num_halluc fraction of output numbers NOT in GT     (fabrication proxy; lower better)
  coverage   len(output words) / len(GT words)        (omission/truncation; ~1 ideal)
Plus, from parse-anything's own value oracle: oracle_flags (unsourced_number count in the ledger).
Reports a per-model table and the born-vs-scan delta (= what parse-anything's deterministic layer adds).

stdlib + pypdfium2. Usage:
  python score.py --results results-from-vm/results --born document.pdf --out results/scores.md
"""
from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re

import pypdfium2 as pdfium

_TAG = re.compile(r"<[^>]+>")                 # html tags
_MD = re.compile(r"[#*_`>|\\]|!\[[^\]]*\]\([^)]*\)|\[\[[^\]]*\]\]")  # md/grounding markup
_WS = re.compile(r"\s+")
_NUM = re.compile(r"\d[\d,\.]{3,}")           # >= 4-char numeric tokens (years, stats, ids)


def normalize(text: str) -> str:
    text = _TAG.sub(" ", text)
    text = re.sub(r"<\|[^|]*\|>", " ", text)   # deepseek grounding tokens <|ref|> etc.
    text = _MD.sub(" ", text)
    text = _WS.sub(" ", text)
    return text.strip().lower()


def tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^\w]+", text) if t]


def numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", "") for m in _NUM.finditer(text)}


def token_f1(gt: list[str], out: list[str]) -> float:
    if not gt and not out:
        return 1.0
    g, o = set(gt), set(out)
    inter = len(g & o)
    if inter == 0:
        return 0.0
    prec, rec = inter / len(o), inter / len(g)
    return 2 * prec * rec / (prec + rec)


def gt_pages(pdf_path: str) -> list[str]:
    doc = pdfium.PdfDocument(pdf_path)
    return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]


def raw_pages(mdir: str, doc: str) -> list[str]:
    # raw_<doc>/<sanitized-model>/NNNN.md ; NNNN is the 1-based page seq
    base = os.path.join(mdir, f"raw_{doc}")
    files = sorted(glob.glob(os.path.join(base, "*", "*.md")))
    return files


def oracle_flags(mdir: str, doc: str) -> int:
    hits = glob.glob(os.path.join(mdir, f"out_{doc}", "*", "*", "ledger.jsonl"))
    if not hits:
        return -1
    n = 0
    with open(hits[0], encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            for f in json.loads(line).get("flags", []):
                if "unsourced_number" in f:
                    n += 1
    return n


def score_model_doc(mdir: str, doc: str, gt_norm: list[str], gt_tok: list[list[str]],
                    gt_num: list[set]) -> dict | None:
    files = raw_pages(mdir, doc)
    if not files:
        return None
    sims, f1s, recs, halls, covs = [], [], [], [], []
    for f in files:
        base = os.path.basename(f)                      # e.g. 0004.md
        try:
            page = int(os.path.splitext(base)[0]) - 1
        except ValueError:
            continue
        if page < 0 or page >= len(gt_norm):
            continue
        out_norm = normalize(open(f, encoding="utf-8").read())
        out_tok, out_num = tokens(out_norm), numbers(out_norm)
        sims.append(difflib.SequenceMatcher(None, gt_norm[page], out_norm).ratio())
        f1s.append(token_f1(gt_tok[page], out_tok))
        gn = gt_num[page]
        recs.append(len(gn & out_num) / len(gn) if gn else 1.0)
        halls.append(len(out_num - gn) / len(out_num) if out_num else 0.0)
        covs.append(len(out_tok) / len(gt_tok[page]) if gt_tok[page] else 0.0)
    if not sims:
        return None
    avg = lambda xs: round(sum(xs) / len(xs), 3)
    return {
        "pages": len(sims), "char_sim": avg(sims), "token_f1": avg(f1s),
        "num_recall": avg(recs), "num_halluc": avg(halls), "coverage": avg(covs),
        "oracle_flags": oracle_flags(mdir, doc),
    }


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--born", required=True, help="born-digital ground-truth PDF (document.pdf)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    gt = gt_pages(args.born)
    gt_norm = [normalize(t) for t in gt]
    gt_tok = [tokens(t) for t in gt_norm]
    gt_num = [numbers(t) for t in gt_norm]

    mdirs = sorted(d for d in glob.glob(os.path.join(args.results, "*")) if os.path.isdir(d))
    lines = ["# OCR sweep - objective scores (axis A)", "",
             f"Ground truth: {os.path.basename(args.born)} text layer ({len(gt)} pages). "
             "Scan and born scored against the same GT. Higher is better except num_halluc/oracle_flags.", ""]

    rows, per = [], {}
    for mdir in mdirs:
        model = os.path.basename(mdir)
        for doc in ("born", "scan"):
            s = score_model_doc(mdir, doc, gt_norm, gt_tok, gt_num)
            if not s:
                continue
            per[(model, doc)] = s
            rows.append([model, doc, s["pages"], s["char_sim"], s["token_f1"],
                         s["num_recall"], s["num_halluc"], s["coverage"], s["oracle_flags"]])
    lines.append(table(["model", "doc", "pages", "char_sim", "token_f1", "num_recall",
                        "num_halluc", "coverage", "oracle_flags"], rows))
    lines.append("")

    # born - scan delta on the two headline metrics = parse-anything deterministic-layer contribution
    lines.append("## parse-anything contribution (born - scan delta)")
    drows = []
    models = sorted({m for (m, _) in per})
    for m in models:
        b, s = per.get((m, "born")), per.get((m, "scan"))
        if b and s:
            drows.append([m, round(b["char_sim"] - s["char_sim"], 3),
                          round(b["token_f1"] - s["token_f1"], 3),
                          round(b["num_recall"] - s["num_recall"], 3)])
    lines.append(table(["model", "d_char_sim", "d_token_f1", "d_num_recall"], drows)
                 if drows else "_(need both born and scan results)_")
    lines.append("")

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"[score] wrote {args.out} ({len(rows)} model/doc rows)")


if __name__ == "__main__":
    main()
