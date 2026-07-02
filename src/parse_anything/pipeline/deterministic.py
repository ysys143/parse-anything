"""Deterministic extraction (pypdfium2): text + numeric tokens with positions.

Evidence: docs/measurement-findings.md F8 (born-digital value oracle is degradation-
independent because it reads the PDF text layer, not the rendered image) and F2.
Contract: pdf-pipeline-requirements §3.2, processing-tiers R-T1/R-V1.

The numeric tokens are the *value oracle*: the source set for guards.source_gate and the
authoritative values for cell injection. Positions (x, y) are kept for bbox-anchored cell
mapping (the robust alternative to reading-order alignment).
"""
from __future__ import annotations

from dataclasses import dataclass

import pypdfium2 as pdfium

_NUMERIC_CHARS = frozenset("0123456789,.")


@dataclass(frozen=True, slots=True)
class NumberToken:
    value: str       # normalized: grouping commas stripped (e.g. "1234567")
    raw: str         # as written (e.g. "1,234,567")
    x: float         # token center x (page points)
    y: float         # token top y (page points)
    page_index: int


def page_text(pdf_path: str, page_index: int) -> str:
    doc = pdfium.PdfDocument(pdf_path)
    try:
        return doc[page_index].get_textpage().get_text_bounded()
    finally:
        doc.close()


def text_char_count(pdf_path: str, page_index: int) -> int:
    """Non-space char count of the text layer. ~0 => scanned/no text layer (triage signal)."""
    return len(page_text(pdf_path, page_index).strip())


def number_tokens(pdf_path: str, page_index: int, *, min_value: float | None = None) -> list[NumberToken]:
    """Numeric tokens (digit runs with grouping commas / decimal point) in reading order,
    each with its position. Optionally keep only tokens with value >= ``min_value``."""
    doc = pdfium.PdfDocument(pdf_path)
    try:
        tp = doc[page_index].get_textpage()
        tokens: list[NumberToken] = []
        run: list[tuple[float, float, float, float, str]] = []

        def flush() -> None:
            if not run:
                return
            raw = "".join(c[4] for c in run).strip(".,")
            if not any(ch.isdigit() for ch in raw):
                return
            value = raw.replace(",", "")
            try:
                fv = float(value)
            except ValueError:
                return
            if min_value is not None and fv < min_value:
                return
            x0 = min(c[0] for c in run)
            x1 = max(c[2] for c in run)
            tokens.append(NumberToken(value=value, raw=raw, x=(x0 + x1) / 2, y=run[0][3], page_index=page_index))

        for i in range(tp.count_chars()):
            left, bottom, right, top = tp.get_charbox(i)
            ch = tp.get_text_range(i, 1)
            if ch in _NUMERIC_CHARS and ch.strip():
                run.append((left, bottom, right, top, ch))
            else:
                flush()
                run = []
        flush()
        return tokens
    finally:
        doc.close()
