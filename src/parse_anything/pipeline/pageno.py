"""Printed page-number extraction (R13).

A document's PRINTED page number (in the footer/header) is what a TOC references and what a human
uses to navigate -- NOT the PDF file page index, which front matter (cover, TOC, preface) offsets.
ODL filters out headers/footers, so we read them from the pypdfium2 raw text layer's margin band.
The disambiguator against stray footnote/figure numbers is the one property a page number has: it
forms a monotone ``+1`` run across consecutive PDF pages, i.e. a constant offset ``k = printed - i``
supported by many pages. A footnote "12" yields a different offset on every page (support 1) and is
filtered out. The result is a per-page label map (not a single global offset), so a Roman -> Arabic
restart or per-section renumbering is honoured wherever it is actually read.
"""
from __future__ import annotations

from collections import Counter

import pypdfium2 as pdfium


def _band_numbers(tp, page_height: float, band: float = 0.12) -> list[int]:
    """Integer tokens whose vertical centre lies in the top or bottom ``band`` of the page (any x).
    Digit-only runs so an adjacent running-header word can't swallow the number."""
    lo, hi = band * page_height, (1.0 - band) * page_height
    out: list[int] = []
    run: list[str] = []

    def flush() -> None:
        if run:
            s = "".join(run)
            if 1 <= len(s) <= 4:
                out.append(int(s))
            run.clear()

    for i in range(tp.count_chars()):
        left, bottom, right, top = tp.get_charbox(i)
        ch = tp.get_text_range(i, 1)
        if (bottom + top) / 2 < lo or (bottom + top) / 2 > hi:
            if ch in "0123456789":  # ASCII only -- note '①'.isdigit() is True
                run.append(ch)
                continue
        flush()
    flush()
    return out


def _resolve(per_page: list[list[int]], n_pages: int) -> dict[int, str | None]:
    votes: Counter[int] = Counter()
    for i, nums in enumerate(per_page):
        for k in {v - i for v in nums}:  # one vote per offset PER PAGE (a repeated stray number != support)
            votes[k] += 1
    if not votes:
        return {i: None for i in range(n_pages)}
    # a real page-number offset is shared by many consecutive pages; a footnote's is not
    supported = {k for k, c in votes.items() if c >= 3} or {votes.most_common(1)[0][0]}
    k_star = max(supported, key=lambda k: votes[k])
    labels: dict[int, str | None] = {}
    for i in range(n_pages):
        read = next((v for v in per_page[i] if (v - i) in supported), None)
        labels[i] = str(read) if read is not None else str(i + k_star)  # extrapolate gaps
    return labels


def extract_printed_page_numbers(pdf_path: str, n_pages: int) -> dict[int, str | None]:
    """Map each PDF page index -> its printed page number (str), inferring/extrapolating via the
    dominant footer offset. Returns all-None when no footer numbers form a consistent run."""
    doc = pdfium.PdfDocument(pdf_path)
    try:
        per_page: list[list[int]] = []
        for i in range(n_pages):
            page = doc[i]
            per_page.append(_band_numbers(page.get_textpage(), page.get_size()[1]))
        return _resolve(per_page, n_pages)
    finally:
        doc.close()


def printed_to_index(labels: dict[int, str | None]) -> dict[str, int]:
    """Inverse map printed-label -> pdf index (first occurrence wins on duplicates)."""
    inv: dict[str, int] = {}
    for idx, lbl in sorted(labels.items()):
        if lbl is not None and lbl not in inv:
            inv[lbl] = idx
    return inv
