"""Document structure-authority cascade (R13).

Prefer the document's OWN declared hierarchy over inference -- this is the anti-overfit backbone:
(1) the PDF outline/bookmarks (machine-readable nav tree, authoritative when present), then
(2) a printed table-of-contents page parsed from the text (dotted-leader ``title ···· page`` lines),
then None -> the caller falls back to numbering-class inference (``sections.py``). The printed-TOC's
page numbers are PRINTED page numbers, resolved to PDF indices via ``pageno`` (front-matter offset).
"""
from __future__ import annotations

import re
from typing import NamedTuple

from .numbering import infer_text_levels
from .odl_extract import OdlDocument


class OutlineEntry(NamedTuple):
    title: str
    level: int
    printed_page: str | None   # as written in the TOC (e.g. "5"); None for PDF-outline entries
    page_index: int | None     # PDF page index (filled directly by outline; resolved later for TOC)
    source: str


class HeadingAuthority(NamedTuple):
    entries: list[OutlineEntry]
    toc_page_indices: frozenset[int]   # printed-TOC pages -- excluded from body-heading detection
    source: str


# "title ···········(middle-dot / dot / ellipsis leader)·· 5"
_LEADER = re.compile(r"^(?P<title>.+?)\s*[·.…‧・]{3,}\s*(?P<page>\d+|[ivxlcdmIVXLCDM]+)\s*$")


def load_pdf_outline(pdf_path: str) -> list[OutlineEntry] | None:
    """PDF bookmark tree via pypdfium2 ``get_toc`` (``.title``/``.level``/``.page_index``). None if empty."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_path)
    try:
        entries: list[OutlineEntry] = []
        for it in doc.get_toc():
            title = (it.title or "").strip()
            if title:
                entries.append(OutlineEntry(title, (it.level or 0) + 1, None, it.page_index, "pdf_outline"))
        return entries or None
    except Exception:  # noqa: BLE001 -- a malformed outline must not break the pipeline
        return None
    finally:
        doc.close()


def parse_printed_toc(structure: OdlDocument) -> HeadingAuthority | None:
    """Parse a printed TOC: pages carrying a CLUSTER (>=4) of dotted-leader entries. The level comes
    from the title's numbering class (``classify_numbering``), NOT the line's ODL kind -- a TOC tags
    sibling entries inconsistently (Ⅰ as list item, Ⅱ as paragraph)."""
    toc_pages: list[int] = []
    raw: list[tuple[str, str]] = []   # (title, printed_page) in reading order
    for page in structure.pages:
        hits: list[tuple[str, str]] = []
        for p in page.paragraphs:
            m = _LEADER.match(p.text.strip())
            if not m:
                continue
            hits.append((m.group("title").strip(" ·.…‧・"), m.group("page")))
        if len(hits) >= 4:  # a cluster -> a real TOC page (one stray dotted line is not a TOC)
            toc_pages.append(page.page_index)
            raw.extend(hits)
    if not raw:
        return None
    # The TOC entry list IS a reading-order heading sequence -> level it document-relative (same nesting
    # stack as the body) instead of the overfit fixed rank, so authority overrides stay gapless.
    levels = infer_text_levels([t for t, _ in raw])
    entries = [OutlineEntry(t, lv or 1, pg, None, "printed_toc") for (t, pg), lv in zip(raw, levels)]
    return HeadingAuthority(entries, frozenset(toc_pages), "printed_toc")


def resolve_heading_authority(pdf_path: str | None, structure: OdlDocument) -> HeadingAuthority | None:
    """Highest-confidence structure authority, or None to fall back to numbering inference."""
    if pdf_path:
        outline = load_pdf_outline(pdf_path)
        if outline:
            return HeadingAuthority(outline, frozenset(), "pdf_outline")
    return parse_printed_toc(structure)
