"""PDF page rendering (pypdfium2).

Evidence: docs/measurement-findings.md F1. Contract: pdf-pipeline-requirements §3.1
(license-clean renderer, high-DPI support). pypdfium2 is BSD/Apache; PyMuPDF (AGPL) is
avoided by default (§9).
"""
from __future__ import annotations

import io

import pypdfium2 as pdfium


def page_count(pdf_path: str) -> int:
    doc = pdfium.PdfDocument(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def render_page_png(pdf_path: str, page_index: int, *, scale: float = 2.0) -> bytes:
    """Render one page to PNG bytes. ``scale`` ~2.0 is ~144 DPI; raise it for dense tables
    (F4: legibility drives VLM numeric accuracy)."""
    doc = pdfium.PdfDocument(pdf_path)
    try:
        pil_image = doc[page_index].render(scale=scale).to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        doc.close()
