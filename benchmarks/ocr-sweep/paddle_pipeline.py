#!/usr/bin/env python3
"""PaddleOCR-VL in its INTENDED full-page pipeline mode (layout detection -> per-element
recognition via the vLLM server -> markdown assembly), as a drop-in alternative to the single-shot
prewarm. This is the fair way to run PaddleOCR-VL (single-shot 'OCR:' underrepresents it).

Serve PaddleOCR-VL on vLLM first, then this runs the `paddleocr` client pipeline per page:
    PaddleOCRVL(vl_rec_backend="vllm", vl_rec_server_url=<base>).predict(png) -> save_to_markdown

Writes the same layout the shim/score expects:
    <raw_dir>/<sanitized-model>/NNNN.md   (1-based page)
    <cache_file>  {"texts":[...]}
    <metrics_file>  per-page latency + a final batched_wall_s row

Deps (client side): pip install "paddleocr[doc-parser]" paddlepaddle-gpu ; layout runs on the client.

Usage:
  python paddle_pipeline.py --pdf document.pdf --server-url http://127.0.0.1:8000 \
     --model-id "PaddlePaddle/PaddleOCR-VL (pipeline)" --raw-dir raw_born \
     --cache-file cache_born.json --metrics-file metrics_born.jsonl
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import tempfile
import time

import pypdfium2 as pdfium


def sanitize(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in s)


def render_all(pdf: str, scale: float = 2.0) -> list[str]:
    """Render pages to PNG files (sequential; pypdfium2 not thread-safe). Returns file paths."""
    doc = pdfium.PdfDocument(pdf)
    paths = []
    tmp = tempfile.mkdtemp(prefix="pp_pages_")
    for i in range(len(doc)):
        p = os.path.join(tmp, f"{i:04d}.png")
        doc[i].render(scale=scale).to_pil().save(p, format="PNG")
        paths.append(p)
    return paths


def page_markdown(pipeline, png_path: str) -> str:
    """Run the PaddleOCR-VL pipeline on one page image and return assembled markdown."""
    with tempfile.TemporaryDirectory() as out:
        for res in pipeline.predict(png_path):
            res.save_to_markdown(save_path=out)
        mds = sorted(glob.glob(os.path.join(out, "**", "*.md"), recursive=True))
        return "\n\n".join(open(m, encoding="utf-8").read() for m in mds)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--server-url", required=True, help="vLLM base url, e.g. http://127.0.0.1:8000")
    ap.add_argument("--model-id", default="PaddlePaddle/PaddleOCR-VL (pipeline)")
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--cache-file", required=True)
    ap.add_argument("--metrics-file", required=True)
    args = ap.parse_args()

    from paddleocr import PaddleOCRVL
    pipeline = PaddleOCRVL(vl_rec_backend="vllm-server", vl_rec_server_url=args.server_url)

    pages = render_all(args.pdf)
    raw_model_dir = os.path.join(args.raw_dir, sanitize(args.model_id))
    os.makedirs(raw_model_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.metrics_file) or ".", exist_ok=True)

    texts, rows = [], []
    wall0 = time.monotonic()
    for i, png in enumerate(pages):
        t0 = time.monotonic()
        try:
            text = page_markdown(pipeline, png)
            state = "done"
        except Exception as exc:  # noqa: BLE001
            text, state = "", f"failed:{type(exc).__name__}"
            print(f"[pipeline] page {i} FAILED: {exc!r}", flush=True)
        texts.append(text)
        with open(os.path.join(raw_model_dir, f"{i + 1:04d}.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        rows.append({"model": args.model_id, "seq": i + 1,
                     "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                     "chars": len(text), "state": state})
        if (i + 1) % 5 == 0:
            print(f"[pipeline] {i + 1}/{len(pages)} pages", flush=True)
    wall = time.monotonic() - wall0

    with open(args.metrics_file, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
        fh.write(json.dumps({"model": args.model_id, "seq": 0, "batched_wall_s": round(wall, 1),
                             "pages": len(pages)}) + "\n")
    with open(args.cache_file, "w", encoding="utf-8") as fh:
        json.dump({"texts": texts}, fh)
    ok = sum(1 for r in rows if r["state"] == "done")
    print(f"[pipeline] {args.model_id}: {ok}/{len(pages)} pages in {wall:.0f}s -> {args.cache_file}")


if __name__ == "__main__":
    main()
