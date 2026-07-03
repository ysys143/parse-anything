#!/usr/bin/env python3
"""Make an image-only ("scanned") PDF from a born-digital PDF.

Renders each page to a raster image and re-embeds it with NO text layer, so parse-anything's
born-digital grounding + value oracle have nothing to anchor to -> the VLM must do real OCR.
This is the discriminating stress doc: same content as the original (born-digital = ground truth),
but every model's raw transcription now stands on its own.

Usage:
  python make_scan_pdf.py --pdf document.pdf --out scan.pdf [--dpi 150] [--grayscale] [--pages 0-45]
"""
from __future__ import annotations

import argparse

import pypdfium2 as pdfium
from PIL import Image


def _parse_pages(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(n))
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [p for p in out if 0 <= p < n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dpi", type=int, default=150, help="render DPI (scan realism vs size)")
    ap.add_argument("--grayscale", action="store_true", help="convert to grayscale (scan-like)")
    ap.add_argument("--pages", default=None, help="page range e.g. 0-45 or 0,2,5 (default all)")
    args = ap.parse_args()

    doc = pdfium.PdfDocument(args.pdf)
    idxs = _parse_pages(args.pages, len(doc))
    scale = args.dpi / 72.0
    images: list[Image.Image] = []
    for i in idxs:
        page = doc[i]
        pil = page.render(scale=scale).to_pil().convert("RGB")
        if args.grayscale:
            pil = pil.convert("L").convert("RGB")
        images.append(pil)
    if not images:
        raise SystemExit("no pages rendered")
    images[0].save(args.out, save_all=True, append_images=images[1:], format="PDF", resolution=float(args.dpi))
    print(f"wrote {args.out}: {len(images)} image-only pages @ {args.dpi}dpi "
          f"grayscale={args.grayscale} (no text layer)")


if __name__ == "__main__":
    main()
