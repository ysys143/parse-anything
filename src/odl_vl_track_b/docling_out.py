"""DoclingDocument wire output for the Track B proxy.

ODL's ``DoclingSchemaTransformer`` consumes only four top-level keys from ``json_content``:
``texts`` / ``tables`` / ``pictures`` / ``pages`` (verified via JAR in the B1 analysis). Each
element needs ``prov[0].{page_no, bbox{l,t,r,b,coord_origin}}`` or it is skipped. We emit the
minimal shape: one ``text`` block per page carrying the VLM Markdown, plus ``page_dimensions``.

Coordinates use PDF points with ``coord_origin="BOTTOMLEFT"`` (pypdfium2's ``get_size()`` unit),
so ODL needs no page-height conversion. Strings are sanitized (NUL / lone surrogate -> U+FFFD)
because Starlette-style JSON encoding fails on them (mirrors the reference server's
``sanitize_unicode`` and ``odl_extract._clean_text``).

The response envelope mirrors the official server's ``build_response`` (hybrid_server.py L231-244).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BBox = dict[str, Any]


@dataclass(frozen=True, slots=True)
class PageBlock:
    """One processed page: 1-based page number, PDF-point size, VLM Markdown, optional flags."""

    page_no: int
    width: float
    height: float
    markdown: str
    label: str = "text"  # docling text label: text | section_header | caption | ...
    flags: tuple[str, ...] = ()  # guard flags (B-4); not part of the wire schema, kept for ledger


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


def _page_bbox(width: float, height: float) -> BBox:
    # Full-page box in PDF points, bottom-left origin (l,b)=(0,0), (r,t)=(w,h).
    return {"l": 0.0, "t": float(height), "r": float(width), "b": 0.0, "coord_origin": "BOTTOMLEFT"}


def build_docling_document(pages: list[PageBlock]) -> dict[str, Any]:
    """Assemble the minimal DoclingDocument dict ODL will absorb."""
    texts: list[dict[str, Any]] = []
    pages_dict: dict[str, Any] = {}
    for pb in pages:
        bbox = _page_bbox(pb.width, pb.height)
        texts.append(
            {
                "label": pb.label,
                "text": sanitize_str(pb.markdown),
                "prov": [{"page_no": pb.page_no, "bbox": bbox}],
            }
        )
        pages_dict[str(pb.page_no)] = {"page_dimensions": {"width": float(pb.width), "height": float(pb.height)}}
    return {"texts": texts, "tables": [], "pictures": [], "pages": pages_dict}


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
