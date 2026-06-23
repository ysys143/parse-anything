"""Per-page signal computation for triage (the I/O behind triage.decide_route).

Evidence: docs/measurement-findings.md F10 (scan/born-digital split reliable; table
detection from pdf-inspector for grids, ODL for merged-cell; image detection works) and the
real-corpus finding that complex VECTOR figures (matplotlib-style scientific plots) carry no
raster image object and their plot grid trips the table detector -- so we also count path
objects (F13/F14). Contract: pdf-pipeline-requirements §3.3-§3.4.

Signal sources: text char count (pypdfium2), image + path object counts (pypdfium2),
table-row count (pdf-inspector). pdf-inspector misses merged-cell tables (F2/F10) -- callers
that need those should supply an ODL-derived override.
"""
from __future__ import annotations

import pypdfium2 as pdfium

from .triage import PageSignals

_FPDF_PAGEOBJ_PATH = 2   # pdfium page-object type for vector paths
_FPDF_PAGEOBJ_IMAGE = 3  # pdfium page-object type for images


def _table_rows_per_page(pdf_path: str, n_pages: int) -> list[int]:
    try:
        import pdf_inspector as pi

        res = pi.extract_pages_markdown(pdf_path)
        pages = res.pages if hasattr(res, "pages") else res
        mds = [p.markdown if hasattr(p, "markdown") else str(p) for p in pages]
        rows = [sum(1 for ln in m.splitlines() if ln.count("|") >= 2) for m in mds]
    except Exception:
        rows = []
    return (rows + [0] * n_pages)[:n_pages]


def document_signals(pdf_path: str) -> list[PageSignals]:
    """Compute ``PageSignals`` for every page. One pdf-inspector pass for the whole doc."""
    doc = pdfium.PdfDocument(pdf_path)
    try:
        n = len(doc)
        text_chars: list[int] = []
        images: list[int] = []
        paths: list[int] = []
        for i in range(n):
            page = doc[i]
            text_chars.append(len(page.get_textpage().get_text_bounded().strip()))
            img = path = 0
            for obj in page.get_objects():
                if obj.type == _FPDF_PAGEOBJ_IMAGE:
                    img += 1
                elif obj.type == _FPDF_PAGEOBJ_PATH:
                    path += 1
            images.append(img)
            paths.append(path)
    finally:
        doc.close()
    table_rows = _table_rows_per_page(pdf_path, n)
    return [
        PageSignals(text_chars=text_chars[i], table_rows=table_rows[i], image_count=images[i], vector_paths=paths[i])
        for i in range(n)
    ]
