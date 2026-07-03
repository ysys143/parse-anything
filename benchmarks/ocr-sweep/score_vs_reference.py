#!/usr/bin/env python3
"""Whole-document scoring against a REAL reference text (not pypdfium2).

pypdfium2's text extraction is itself a lossy, reading-order-scrambling OCR-ish step, so scoring
models against it measures "similarity to pypdfium2", not accuracy — and it demonstrably distorted
the ranking (olmOCR looked worst against pypdfium2, but is top-3 against the real text). This scorer
compares each model's WHOLE-document output (all pages concatenated) against an authoritative
reference (e.g. the publisher's full text), order-insensitively.

Metrics (whole-doc, order-free):
  token_f1     bag-of-words F1 vs the reference (the headline number)
  tok_recall   fraction of reference words the model produced
  tok_prec     fraction of model words that are in the reference (low = verbose/hallucinated)
  num_recall   fraction of the reference's >=4-char numbers the model reproduced
  num_halluc   fraction of the model's numbers NOT in the reference (inflated: figure/table numbers
               may not be in a body-text reference)

Each model = one dir containing `raw_born/<name>/NNNN.md` (as produced by prewarm/paddle_pipeline).
Point --results at the parent(s) of those model dirs (e.g. extracted results archives).

Usage:
  python score_vs_reference.py --reference gt/reference.txt --out results/scores_vs_gt.md \
      --results /tmp/ocr_ex /tmp/pipe_ex
"""
from __future__ import annotations

import argparse
import glob
import os
import re

_TAG = re.compile(r"</?[A-Za-z!][^>]*>")
_MD = re.compile(r"[#*_`>|\\]|!\[[^\]]*\]\([^)]*\)|\[\[[^\]]*\]\]")
_WS = re.compile(r"\s+")
_NUM = re.compile(r"\d[\d,\.]{3,}")


def normalize(t: str) -> str:
    t = _TAG.sub(" ", t)
    t = re.sub(r"<\|[^|]*\|>", " ", t)
    t = _MD.sub(" ", t)
    return _WS.sub(" ", t).strip().lower()


def tokens(t: str) -> list[str]:
    return [w for w in re.split(r"[^\w]+", t) if w]


def numbers(t: str) -> set[str]:
    return {m.group(0).replace(",", "") for m in _NUM.finditer(t)}


def find_models(roots: list[str]) -> dict[str, list[str]]:
    """Return {model_name: [page md files]} by locating raw_born dirs under the roots."""
    out: dict[str, list[str]] = {}
    for root in roots:
        for rb in glob.glob(os.path.join(root, "**", "raw_born"), recursive=True):
            name = os.path.basename(os.path.dirname(rb))
            files = sorted(glob.glob(os.path.join(rb, "**", "*.md"), recursive=True))
            if files:
                out.setdefault(name, []).extend(files)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True)
    ap.add_argument("--results", nargs="+", required=True, help="dirs containing <model>/raw_born/...")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ref = normalize(open(args.reference, encoding="utf-8").read())
    ref_tok, ref_num = set(tokens(ref)), numbers(ref)
    ref_words = len(tokens(ref))

    rows = []
    for name, files in find_models(args.results).items():
        text = normalize("\n".join(open(f, encoding="utf-8").read() for f in files))
        tk, nm = set(tokens(text)), numbers(text)
        inter = len(ref_tok & tk)
        prec = inter / len(tk) if tk else 0.0
        rec = inter / len(ref_tok) if ref_tok else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        nrec = len(ref_num & nm) / len(ref_num) if ref_num else 0.0
        nhal = len(nm - ref_num) / len(nm) if nm else 0.0
        rows.append((name, len(files), round(f1, 3), round(rec, 3), round(prec, 3),
                     round(nrec, 3), round(nhal, 3), len(tokens(text))))
    rows.sort(key=lambda r: -r[2])

    lines = ["# Whole-document scores vs reference text", "",
             f"Reference: {os.path.basename(args.reference)} ({ref_words} words). "
             "Each model's pages concatenated, order-insensitive. token_f1 is the headline.", "",
             "| model | pages | token_f1 | tok_recall | tok_prec | num_recall | num_halluc | words |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append("| " + " | ".join(str(x) for x in r) + " |")
    lines.append("")
    lines.append("_num_halluc is inflated: a body-text reference omits numbers that legitimately "
                 "appear in figures/tables on the page._")
    open(args.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"[score_vs_reference] wrote {args.out} ({len(rows)} models)")
    for r in rows:
        print(f"  {r[0]:<34} f1={r[2]}  num_rec={r[5]}")


if __name__ == "__main__":
    main()
