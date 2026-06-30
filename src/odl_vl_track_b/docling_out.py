"""DoclingDocument wire output for the Track B proxy.

ODL's ``DoclingSchemaTransformer`` consumes four top-level keys from ``json_content``:
``texts`` / ``tables`` / ``pictures`` / ``pages`` (verified via JAR + Java source in B1). Each
element needs ``prov[0].{page_no, bbox{l,t,r,b,coord_origin}}`` or it is skipped.

The VLM returns Markdown, so we parse it into structured elements instead of dumping one flat text
block (which loses tables — the B-3 limitation). Markdown headings become ``section_header`` texts
(with ``meta.level``), Markdown tables become ``tables`` with BOTH ``data.grid`` (required: ODL
reads row/col dims from it, DoclingSchemaTransformer.java L439-448) and ``data.table_cells``
(cell text, keyed by start_row/col, L464-471); everything else is a ``text`` paragraph.

Blocks are stacked top-to-bottom into synthetic per-block bboxes (PDF points, BOTTOMLEFT origin)
so ODL keeps reading order. The VLM gives no real coordinates, so these are evenly partitioned.
Strings are sanitized (NUL / lone surrogate -> U+FFFD) to keep JSON encoding from raising.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

BBox = dict[str, Any]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_SEP_CHARS = set("-: |")


@dataclass(frozen=True, slots=True)
class PageBlock:
    """One processed page: 1-based page number, PDF-point size, VLM Markdown, optional flags."""

    page_no: int
    width: float
    height: float
    markdown: str
    flags: tuple[str, ...] = ()  # guard flags (B-4); not wire schema, kept for ledger


def sanitize_str(s: str) -> str:
    """NUL and lone UTF-16 surrogates -> U+FFFD. Keeps JSON encoding from raising."""
    out: list[str] = []
    for ch in s:
        o = ord(ch)
        if o == 0 or 0xD800 <= o <= 0xDFFF:
            out.append("�")
        else:
            out.append(ch)
    return "".join(out)


def _bbox(width: float, height: float, idx: int, n: int) -> BBox:
    """Synthetic block bbox: evenly partition the page top-to-bottom (BOTTOMLEFT origin)."""
    top = height * (1 - idx / n)
    bottom = height * (1 - (idx + 1) / n)
    return {"l": 0.0, "t": top, "r": float(width), "b": bottom, "coord_origin": "BOTTOMLEFT"}


def _is_separator_row(cells: list[str]) -> bool:
    """A Markdown table delimiter row like ``|---|:--:|`` (only dashes/colons/spaces)."""
    return bool(cells) and all(set(c) <= _SEP_CHARS - {"|"} and c for c in cells)


def _split_table_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_markdown_blocks(markdown: str) -> list[tuple[str, Any]]:
    """Parse Markdown into ordered blocks: ('heading',(level,text)) | ('table',rows) | ('text',str).

    A table is a run of lines that start with ``|``; its delimiter row is dropped. Consecutive
    non-blank non-heading lines coalesce into one paragraph.
    """
    lines = markdown.split("\n")
    blocks: list[tuple[str, Any]] = []
    para: list[str] = []

    def flush_para() -> None:
        text = "\n".join(para).strip()
        if text:
            blocks.append(("text", text))
        para.clear()

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            flush_para()
            i += 1
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            flush_para()
            blocks.append(("heading", (len(heading.group(1)), heading.group(2).strip())))
            i += 1
            continue
        if stripped.startswith("|"):
            flush_para()
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = _split_table_row(lines[i])
                if not _is_separator_row(cells):
                    rows.append(cells)
                i += 1
            if rows:
                blocks.append(("table", rows))
            continue
        para.append(lines[i])
        i += 1
    flush_para()
    return blocks


def _table_element(rows: list[list[str]], prov: list[dict[str, Any]]) -> dict[str, Any]:
    num_rows = len(rows)
    num_cols = max((len(r) for r in rows), default=0)
    # grid carries dimensions only (ODL reads row/col counts from it); cell text lives in table_cells.
    grid = [["" for _ in range(num_cols)] for _ in range(num_rows)]
    cells: list[dict[str, Any]] = []
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            cells.append(
                {
                    "start_row_offset_idx": r, "end_row_offset_idx": r + 1,
                    "start_col_offset_idx": c, "end_col_offset_idx": c + 1,
                    "row_span": 1, "col_span": 1, "text": sanitize_str(cell),
                }
            )
    return {"prov": prov, "data": {"grid": grid, "table_cells": cells, "num_rows": num_rows, "num_cols": num_cols}}


def markdown_to_elements(markdown: str, page_no: int, width: float, height: float) -> tuple[list[dict], list[dict]]:
    """Parse one page's Markdown into (texts, tables) DoclingDocument elements."""
    blocks = parse_markdown_blocks(markdown)
    if not blocks:
        text = markdown.strip()
        blocks = [("text", text)] if text else []
    n = max(1, len(blocks))
    texts: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    for idx, (kind, payload) in enumerate(blocks):
        prov = [{"page_no": page_no, "bbox": _bbox(width, height, idx, n)}]
        if kind == "heading":
            level, text = payload
            texts.append({"label": "section_header", "text": sanitize_str(text), "prov": prov, "meta": {"level": level}})
        elif kind == "table":
            tables.append(_table_element(payload, prov))
        else:
            texts.append({"label": "text", "text": sanitize_str(payload), "prov": prov})
    return texts, tables


def build_docling_document(pages: list[PageBlock]) -> dict[str, Any]:
    """Assemble the DoclingDocument dict ODL absorbs, with structured tables/headings per page."""
    texts: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    pages_dict: dict[str, Any] = {}
    for pb in pages:
        page_texts, page_tables = markdown_to_elements(pb.markdown, pb.page_no, pb.width, pb.height)
        texts.extend(page_texts)
        tables.extend(page_tables)
        pages_dict[str(pb.page_no)] = {"page_dimensions": {"width": float(pb.width), "height": float(pb.height)}}
    return {"texts": texts, "tables": tables, "pictures": [], "pages": pages_dict}


def build_response(
    status: str,
    json_content: dict[str, Any],
    *,
    processing_time: float,
    errors: list[str],
    failed_pages: list[int],
) -> dict[str, Any]:
    """Envelope matching the official docling-fast server (status/document/errors/failed_pages)."""
    return {
        "status": status,
        "document": {"json_content": json_content},
        "processing_time": processing_time,
        "errors": errors,
        "failed_pages": failed_pages,
    }
