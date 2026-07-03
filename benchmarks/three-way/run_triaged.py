#!/usr/bin/env python3
"""Run parse-anything in its NATIVE triaged mode (--diagnose) as a 'pa_triaged' parser row.

This shows parse-anything's real operating point: it diagnoses each document (D-1) and routes
born-digital -> deterministic (VLM 0 calls, ~ODL cost) and scan -> det_vlm. Writes results into
results/<run>/pa_triaged/<doc>/ in the same {pages,meta}.json format the scorer/pareto consume.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from runners import result_to_dict, run_parse_anything

# Absolute paths: run_parse_anything runs the CLI with cwd=REPO, so relative paths would resolve
# against the repo root instead of this dir (the mismatch that made the first triaged run fail).
RUN_DIR = Path("results/live").resolve()
CORPUS = Path("corpus").resolve()

for doc in ("born", "scan"):
    pdf = CORPUS / f"{doc}.pdf"
    outdir = RUN_DIR / "pa_triaged" / doc
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    print(f"[triaged] pa_triaged/{doc} (--diagnose) ...", flush=True)
    res = run_parse_anything(pdf, outdir / "_out", live=True, diagnose=True, name="pa_triaged")
    (outdir / "pages.json").write_text(json.dumps(res.pages, ensure_ascii=False), encoding="utf-8")
    (outdir / "meta.json").write_text(json.dumps(result_to_dict(res), indent=2), encoding="utf-8")
    row = result_to_dict(res)
    print(f"   -> {row['status']}  {row['n_pages']}p  {row['n_chars']}ch  {row['seconds']}s  "
          f"vlm_calls={row['vlm_calls']}" + (f"  [{row['error']}]" if row["error"] else ""))

print("done")
