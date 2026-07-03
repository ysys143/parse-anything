#!/usr/bin/env python3
"""Drive the three-way parser comparison over the born + scan corpus.

For each parser (odl, paddle, pa) x each doc (born, scan) it runs the matching runner and writes:
  results/<run>/<parser>/<doc>/pages.json   (per-page markdown)
  results/<run>/<parser>/<doc>/meta.json    (status / latency / char count)

Dry-run (default): odl + pa(deterministic) run for real; paddle is skipped (no API spend). Pass
--live to make the real PaddleOCR-VL calls and run pa in full det_vlm --primary paddle mode.

Usage:
  python run_compare.py --corpus corpus --results results --run dryrun        # no API
  python run_compare.py --corpus corpus --results results --run live --live    # real Paddle
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from runners import result_to_dict, run_odl, run_paddle, run_parse_anything

PARSERS = ("odl", "paddle", "pa")
DOCS = ("born", "scan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus", help="dir with born.pdf + scan.pdf")
    ap.add_argument("--results", default="results")
    ap.add_argument("--run", default="dryrun", help="run label (subdir under results/)")
    ap.add_argument("--live", action="store_true", help="make real PaddleOCR-VL API calls")
    ap.add_argument("--only", default="", help="comma list of parsers to run (default all)")
    args = ap.parse_args()

    corpus = Path(args.corpus).resolve()
    run_dir = (Path(args.results) / args.run).resolve()
    only = {p for p in args.only.split(",") if p} or set(PARSERS)

    summary = []
    for parser in PARSERS:
        if parser not in only:
            continue
        for doc in DOCS:
            pdf = corpus / f"{doc}.pdf"
            if not pdf.exists():
                print(f"[skip] {parser}/{doc}: {pdf} missing")
                continue
            outdir = run_dir / parser / doc
            if outdir.exists():
                shutil.rmtree(outdir)
            outdir.mkdir(parents=True)
            print(f"[run ] {parser}/{doc} (live={args.live}) ...", flush=True)
            if parser == "odl":
                res = run_odl(pdf, outdir / "_work")
            elif parser == "paddle":
                res = run_paddle(pdf, outdir / "_raw", live=args.live)
            else:
                res = run_parse_anything(pdf, outdir / "_out", live=args.live)
            (outdir / "pages.json").write_text(json.dumps(res.pages, ensure_ascii=False), encoding="utf-8")
            (outdir / "meta.json").write_text(json.dumps(result_to_dict(res), indent=2), encoding="utf-8")
            row = result_to_dict(res)
            summary.append(row)
            print(f"       -> {row['status']}  {row['n_pages']}p  {row['n_chars']}ch  {row['seconds']}s"
                  + (f"  [{row['error']}]" if row["error"] else ""))

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {run_dir}/summary.json ({len(summary)} runs)")


if __name__ == "__main__":
    main()
