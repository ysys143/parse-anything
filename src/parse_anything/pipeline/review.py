"""Domain-adaptation review harness: a side-by-side HTML view of a run.

Contract: processing-tiers R-A2 (source vs extraction side by side) and R-A3 (surface only
the risky items -- flagged pages). This is the tool that makes per-domain measurement and
human verification cheap; the human reviews flagged pages, not everything, and those verdicts
become the domain golden set (R-A5).

It renders each non-folded page image (base64) next to its extracted Markdown and its guard
flags; flagged pages are marked so a reviewer can jump straight to them.
"""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any

from .render import render_page_png
from .run import DocumentResult


def _load_document_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _page_sizes(pdf_path: str) -> dict[int, tuple[float, float]]:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_path)
    try:
        return {i: doc[i].get_size() for i in range(len(doc))}
    finally:
        doc.close()


def _node_index(document_json: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not document_json:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key in ("blocks", "tables", "figures"):
        for node in document_json.get(key, []) or []:
            if isinstance(node, dict) and node.get("id") is not None:
                out[str(node["id"])] = node
    return out


def _page_node_ids(document_json: dict[str, Any], page_index: int, index: dict[str, dict[str, Any]]) -> list[str]:
    page_ids: list[str] = []
    for page in document_json.get("pages", []) or []:
        if not isinstance(page, dict) or page.get("page_index") != page_index:
            continue
        for key in ("content", "blocks", "tables", "figures"):
            for node_id in page.get(key, []) or []:
                sid = str(node_id)
                if sid not in page_ids:
                    page_ids.append(sid)
    if page_ids:
        return page_ids
    page_number = page_index + 1
    return [node_id for node_id, node in index.items() if node.get("page") == page_number or page_number in (node.get("pages") or [])]


def _node_bbox(node: dict[str, Any], page_number: int) -> list[float] | None:
    bbox = node.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        return [float(v) for v in bbox]
    for region in node.get("regions", []) or []:
        if isinstance(region, dict) and region.get("page") == page_number:
            rb = region.get("bbox")
            if isinstance(rb, list) and len(rb) == 4:
                return [float(v) for v in rb]
    return None


def _bbox_style(bbox: list[float], size: tuple[float, float]) -> str | None:
    width, height = size
    if width <= 0 or height <= 0:
        return None
    x0, y0, x1, y1 = bbox
    if x1 <= x0 or y1 <= y0:
        return None

    def pct(value: float) -> float:
        return max(0.0, min(100.0, value))

    left = pct(x0 / width * 100)
    top = pct((height - y1) / height * 100)
    w = pct((x1 - x0) / width * 100)
    h = pct((y1 - y0) / height * 100)
    return f"left:{left:.3f}%;top:{top:.3f}%;width:{w:.3f}%;height:{h:.3f}%"


def _node_title(node: dict[str, Any]) -> str:
    return str(node.get("label") or node.get("caption") or node.get("text") or node.get("type") or node.get("id") or "node")


def _node_summary(node: dict[str, Any]) -> str:
    parts = [str(node.get(k) or "").strip() for k in ("label", "caption", "description", "text")]
    body = " ".join(p for p in parts if p)
    return body or _node_title(node)


def _overlay_html(page_index: int, document_json: dict[str, Any] | None,
                  sizes: dict[int, tuple[float, float]]) -> tuple[str, str]:
    if not document_json or page_index not in sizes:
        return "", ""
    index = _node_index(document_json)
    node_ids = _page_node_ids(document_json, page_index, index)
    markers: list[str] = []
    cards: list[str] = []
    page_number = page_index + 1
    for display_idx, node_id in enumerate(node_ids, start=1):
        node = index.get(node_id)
        if not node:
            continue
        attr_id = html.escape(node_id, quote=True)
        title = html.escape(_node_title(node), quote=True)
        body = html.escape(_node_summary(node))
        node_type = html.escape(str(node.get("type") or "node"))
        cards.append(
            f"<div class='node' id='node-{attr_id}' data-node='{attr_id}'>"
            f"<div><b>{title}</b> <span>{node_type}</span></div><p>{body}</p></div>"
        )
        bbox = _node_bbox(node, page_number)
        if bbox is None:
            continue
        style = _bbox_style(bbox, sizes[page_index])
        if style is None:
            continue
        markers.append(
            f"<a class='mk' href='#node-{attr_id}' data-node='{attr_id}' style='{style}' "
            f"title='{title}'>{display_idx}</a>"
        )
    node_html = "<div class='nodes'>" + "".join(cards) + "</div>" if cards else ""
    return "".join(markers), node_html


def build_review_html(
    pdf_path: str,
    result: DocumentResult,
    *,
    scale: float = 1.5,
    document_json: dict[str, Any] | None = None,
) -> str:
    flagged = sum(1 for p in result.pages if p.flags and p.route != "folded")
    sizes = _page_sizes(pdf_path) if document_json else {}
    parts = [
        "<!doctype html><meta charset='utf-8'><title>ODL-VL review</title>",
        "<style>body{font-family:sans-serif;margin:1rem}.pg{display:flex;gap:1rem;border-top:1px solid #ccc;padding:1rem 0}"
        ".src{position:relative;flex:0 0 48%;align-self:flex-start}.src img{width:100%;border:1px solid #ddd;display:block}"
        ".mk{position:absolute;border:2px solid #e11d48;background:rgba(225,29,72,.10);color:#e11d48;font:700 11px monospace;"
        "display:flex;align-items:flex-start;justify-content:flex-end;padding:2px;text-decoration:none;min-width:18px;min-height:18px}"
        ".mk:hover,.mk.active{background:rgba(225,29,72,.22);box-shadow:0 0 0 2px rgba(225,29,72,.22)}"
        ".col{flex:1}.flag{background:#fee;color:#900;padding:2px 6px;border-radius:4px;margin:2px;display:inline-block}"
        "pre{white-space:pre-wrap;background:#f6f6f6;padding:.5rem;max-height:48vh;overflow:auto}.flagged{outline:3px solid #f33}"
        ".nodes{margin-top:.75rem;display:grid;gap:.5rem}.node{border:1px solid #ddd;border-radius:6px;padding:.5rem;background:#fff}"
        ".node span{color:#666;font:12px monospace}.node p{margin:.35rem 0 0}.node.active{border-color:#e11d48;background:#fff1f2}</style>",
        "<script>function highlightNode(id){document.querySelectorAll('.mk.active,.node.active').forEach(function(e){e.classList.remove('active')});"
        "document.querySelectorAll('[data-node]').forEach(function(e){if(e.getAttribute('data-node')===id)e.classList.add('active')});"
        "var n=document.getElementById('node-'+id);if(n)n.scrollIntoView({block:'nearest'})}"
        "document.addEventListener('click',function(e){var t=e.target.closest('[data-node]');if(!t)return;highlightNode(t.getAttribute('data-node'))})</script>",
        f"<h1>Review — {html.escape(Path(pdf_path).name)}</h1>",
        f"<p>{len(result.pages)} pages, {flagged} flagged for review.</p>",
    ]
    for p in result.pages:
        if p.route == "folded":
            parts.append(f"<div class='pg'><div class='col'>page {p.page_index}: folded into the spanning table</div></div>")
            continue
        img_b64 = base64.b64encode(render_page_png(pdf_path, p.page_index, scale=scale)).decode("ascii")
        flag_html = "".join(f"<span class='flag'>{html.escape(f)}</span>" for f in p.flags) or "<em>no flags</em>"
        cls = " flagged" if p.flags else ""
        overlay, node_html = _overlay_html(p.page_index, document_json, sizes)
        parts.append(
            f"<div class='pg{cls}'>"
            f"<div class='src'><img src='data:image/png;base64,{img_b64}' alt='page {p.page_index}'>{overlay}</div>"
            f"<div class='col'><b>page {p.page_index}</b> — route={html.escape(p.route)} "
            f"vlm={p.used_vlm}<div>{flag_html}</div><pre>{html.escape(p.markdown)}</pre>{node_html}</div></div>"
        )
    return "".join(parts)


def write_review(pdf_path: str, result: DocumentResult, out_path: str | Path, *, scale: float = 1.5,
                 document_json: dict[str, Any] | None = None) -> None:
    path = Path(out_path)
    if document_json is None:
        document_json = _load_document_json(path.parent / "document.json")
    path.write_text(build_review_html(pdf_path, result, scale=scale, document_json=document_json), encoding="utf-8")
