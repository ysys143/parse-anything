"""Run the parse-anything pipeline over the golden corpus and adapt each document.json into the flat
shape score.py expects (``{caption, structured, elements}``), then you score with::

    python run_bench.py --mode deterministic --out runs/det      # no API, no cost
    python score.py --out runs/det

    python run_bench.py --mode det_vlm --out runs/vlm             # LIVE VLM (needs GEMINI_API_KEY; costs)
    python score.py --out runs/vlm

The adapter is FAITHFUL: it copies only what the pipeline actually produced (figure descriptions ->
``caption``; gated ``extractions`` + table cells + chart_data -> ``structured``; every bbox'd node ->
``elements``). It never synthesizes a caption or a value the pipeline didn't emit -- an empty caption in
deterministic mode is an honest "no VLM ran", not a fabricated pass.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_GT = _HERE / "gt"
# make `import parse_anything` work when run from the benchmarks dir
sys.path.insert(0, str(_HERE.parents[1] / "src"))


def _adapt(doc: dict) -> dict:
    """document.json -> score.py's flat shape. Faithful copy only (no fabrication)."""
    nodes = [*doc.get("blocks", []), *doc.get("tables", []), *doc.get("figures", [])]
    elements = [{"kind": n.get("kind") or n.get("type"), "bbox": n["bbox"]}
                for n in nodes if n.get("bbox")]
    # caption := the VLM figure descriptions the pipeline emitted (empty in deterministic mode)
    caption = "\n".join(f["description"] for f in doc.get("figures", []) if f.get("description"))
    structured: dict = {}
    if doc.get("extractions"):                 # B*b gated form/dimension/title-block overlay
        structured["extractions"] = doc["extractions"]
    # table cells + chart_data carry the born-digital values C_entity / A_unit look for
    tables = [{"id": t.get("id"), "cells": t.get("cells")} for t in doc.get("tables", []) if t.get("cells")]
    if tables:
        structured["tables"] = tables
    chart = [f["chart_data"] for f in doc.get("figures", []) if f.get("chart_data")]
    if chart:
        structured["chart_data"] = chart
    return {"caption": caption, "structured": structured, "elements": elements}


def _slice_page(pdf: Path, page_1based: int, dst: Path) -> Path:
    """Extract the ONE labelled page into a fresh 1-page PDF -- so a live det_vlm run touches only the page
    the gt actually scores, not all 489 pages of a policy doc. Images have no page hint and are used whole."""
    import pypdfium2 as pdfium

    src = pdfium.PdfDocument(str(pdf))
    try:
        out = pdfium.PdfDocument.new()
        out.import_pages(src, [page_1based - 1])   # gt page is 1-based; import_pages is 0-based
        out.save(str(dst))
        out.close()
    finally:
        src.close()
    return dst


def _run_one(sample: Path, stem: str, mode: str, corpus_root: Path, primary: str = "gemini",
             page: "int | None" = None) -> dict:
    import parse_anything.cli as cli

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        pdf = sample
        # for a live run, slice the multi-page PDF down to the single labelled page (huge cost saver);
        # deterministic mode is cheap so it keeps whole-doc grounding
        if page and mode != "deterministic" and sample.suffix.lower() == ".pdf":
            pdf = _slice_page(sample, page, Path(td) / "page.pdf")
        argv = ["--pdf", str(pdf), "--out", str(out), "--source-id", stem]
        argv += ["--no-vlm"] if mode == "deterministic" else ["--mode", "det_vlm", "--primary", primary]
        # env_file default (.env at repo root) supplies the key for det_vlm; deterministic ignores it
        code = cli.run_cli(argv, cli.Runtime(environ={}, stdout=io.StringIO()),
                           env_file=corpus_root.parents[1] / ".env")
        if code != 0:
            raise RuntimeError(f"pipeline exited {code} for {sample}")
        docs = list((out / stem).glob("*/document.json"))
        if not docs:
            raise RuntimeError(f"no document.json produced for {sample}")
        return _adapt(json.loads(docs[0].read_text(encoding="utf-8")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["deterministic", "det_vlm"], default="deterministic")
    ap.add_argument("--primary", choices=["gemini", "paddle"], default="gemini",
                    help="det_vlm page transcriber (captions are always Gemini)")
    ap.add_argument("--out", required=True, help="dir to write <label-stem>.json adapted outputs")
    ap.add_argument("--corpus", default=str(_HERE.parents[1] / ".local" / "semantic-captioning"),
                    help="corpus root that the gt 'sample' paths are relative to")
    ap.add_argument("--only", default=None, help="only run labels whose stem contains this substring")
    a = ap.parse_args()

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus_root = Path(a.corpus)
    ran = failed = 0
    for gt in sorted(_GT.glob("*.json")):
        label = json.loads(gt.read_text(encoding="utf-8"))
        stem = gt.stem
        if a.only and a.only not in stem:
            continue
        sample = corpus_root / label.get("sample", "")
        if not sample.exists():
            print(f"  {stem:24} SKIP (sample missing: {sample})")
            continue
        try:
            adapted = _run_one(sample, stem, a.mode, corpus_root, a.primary, label.get("page"))
        except Exception as exc:   # noqa: BLE001 -- one bad sample must not abort the sweep
            print(f"  {stem:24} ERROR {type(exc).__name__}: {exc}")
            failed += 1
            continue
        (out_dir / f"{stem}.json").write_text(json.dumps(adapted, ensure_ascii=False, indent=2), encoding="utf-8")
        n_el = len(adapted["elements"])
        has_cap = "cap" if adapted["caption"] else "no-cap"
        print(f"  {stem:24} OK  elements={n_el:3} {has_cap} structured_keys={list(adapted['structured'])}")
        ran += 1
    print(f"--- {ran} run, {failed} failed (mode={a.mode}) -> {out_dir} ---")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
