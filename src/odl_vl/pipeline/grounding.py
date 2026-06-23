"""Deterministic grounding for det_vlm: inject BOTH deterministic sources into the VLM prompt
(processing-tiers R-M1, the agreed ODL + pypdfium2 dual injection).

- pypdfium2 text layer = the printed text and NUMERIC VALUES authority (never altered).
- ODL = the structure: headings, reading order, and table grids to follow.

The VLM transcribes the page IMAGE, anchored to this deterministic context. The post-hoc value
oracle still hard-gates numbers, so grounding improves fidelity without becoming a trust path.
"""
from __future__ import annotations

from typing import Any

from .odl_extract import substantial_tables

_MAX_TEXT_CHARS = 6000
_MAX_TABLE_ROWS = 30


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "\n[...truncated...]"


def _odl_structure_outline(odl_page: Any) -> str:
    lines: list[str] = []
    for para in getattr(odl_page, "paragraphs", ()):
        prefix = "# " if para.kind == "heading" else ("- " if para.kind == "list item" else "")
        if para.text.strip():
            lines.append(prefix + para.text.strip())
    for table in substantial_tables(odl_page):
        head = f"[table {table.n_rows}x{table.n_cols}" + (f": {table.label}" if table.label else "") + "]"
        lines.append(head)
        for row in table.cells[:_MAX_TABLE_ROWS]:
            lines.append(" | ".join(c for c in row))
    return "\n".join(lines)


def build_grounded_prompt(base_prompt: str, pypdf_text: str, odl_page: Any | None = None) -> str:
    """Compose base_prompt + a deterministic grounding block (pypdfium2 values + ODL structure).
    Returns base_prompt unchanged when there is no deterministic text to ground with (scan)."""
    if not pypdf_text.strip():
        return base_prompt
    parts = [
        base_prompt,
        "",
        "--- DETERMINISTIC GROUNDING (authoritative; do not contradict) ---",
        "Text layer (pypdfium2) -- the printed text and NUMERIC VALUES are authoritative; "
        "transcribe them verbatim and NEVER alter a number:",
        _truncate(pypdf_text, _MAX_TEXT_CHARS),
    ]
    outline = _odl_structure_outline(odl_page) if odl_page is not None else ""
    if outline.strip():
        parts += ["", "Structure (ODL) -- headings, reading order, and table grids to follow:", _truncate(outline, _MAX_TEXT_CHARS)]
    parts += [
        "--- END GROUNDING ---",
        "",
        "Transcribe the PAGE IMAGE into Markdown, consistent with the grounding above. Where the "
        "image and the text layer agree, use the text-layer spelling and numbers.",
    ]
    return "\n".join(parts)
