"""Output assembly (pdf-pipeline-requirements §7).

Per-document outputs land under ``<out_root>/<source_id>/<document_id>/`` (see document_dir):
- pages/ : per-page Markdown      - document.md : assembled Markdown
- document.json : loss-aware source of truth (identity, provenance, pages, tables, figures)
- tables/ : per-table JSON + Markdown views
- assets/ : extracted figure images (R2.5)
- ledger.jsonl / results.jsonl : per-page route/flags

Markdown is the human view; JSON is the source of truth (document id = content hash, original
fig/table labels, bbox, cells). Run artifacts are git-ignored.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from .arithmetic import check_table_arithmetic as _check_arithmetic
from .odl_extract import substantial_tables
from .run import DocumentResult


def document_dir(out_root: str | Path, result: DocumentResult) -> Path:
    """The per-document output directory: <out_root>/<source_id>/<document_id>. Falls back to
    out_root when the result has no metadata (legacy callers)."""
    meta = result.meta
    if meta is None:
        return Path(out_root)
    return Path(out_root) / meta.source_id / meta.document_id


def write_outputs(result: DocumentResult, out_dir: str | Path, *, pdf_path: str | None = None, arithmetic: bool = True) -> None:
    out = Path(out_dir)
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    doc_parts: list[str] = []
    for p in result.pages:
        record = {"page_index": p.page_index, "route": p.route, "used_vlm": p.used_vlm, "flags": list(p.flags)}
        if p.route == "folded":
            results.append(record)
            continue
        name = f"page-{p.page_index:03d}.md"
        (pages_dir / name).write_text(p.markdown, encoding="utf-8")
        record["markdown_file"] = f"pages/{name}"
        results.append(record)
        doc_parts.append(p.markdown)

    (out / "document.md").write_text("\n\n---\n\n".join(doc_parts), encoding="utf-8")
    _write_jsonl(out / "ledger.jsonl", result.ledger())
    _write_jsonl(out / "results.jsonl", results)

    if result.meta is not None:
        labels_by_page = {p.page_index: p.labels for p in result.pages}
        tables, figures, page_tables, page_figures = (
            _serialize_structure(result.structure, labels_by_page, arithmetic=arithmetic) if result.structure is not None else ([], [], {}, {})
        )
        _write_assets(out, figures, pdf_path)  # fills each figure["file"]
        _write_document_json(out, result, tables, figures, page_tables, page_figures)
        _write_tables(out, tables)


def _table_md(cells: list[list[dict]]) -> str:
    if not cells:
        return ""
    text = [[c["text"] for c in row] for row in cells]
    width = max((len(r) for r in text), default=0)
    rows = [r + [""] * (width - len(r)) for r in text]
    lines = ["| " + " | ".join(c.replace("|", r"\|") for c in rows[0]) + " |",
             "| " + " | ".join("---" for _ in range(width)) + " |"]
    lines += ["| " + " | ".join(c.replace("|", r"\|") for c in r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _rich_cells(cells: tuple, cell_boxes: tuple) -> list[list[dict]]:
    """Row-major cells as {text, bbox} (per-cell bbox from ODL; None when absent)."""
    out = []
    for r, row in enumerate(cells):
        boxes = cell_boxes[r] if r < len(cell_boxes) else ()
        out.append([{"text": t, "bbox": list(boxes[i]) if (i < len(boxes) and boxes[i]) else None}
                    for i, t in enumerate(row)])
    return out


def _table_chains(tables: list) -> list[list]:
    """Group ODL tables into continuation chains via `previous_table_id` (spanning tables) so a
    table split across pages becomes one logical table. Tables without an id are their own chain."""
    by_id = {t.table_id: t for t in tables if t.table_id}
    next_of = {t.previous_table_id: t for t in tables if t.previous_table_id in by_id}
    is_continuation = {t.table_id for t in tables if t.previous_table_id in by_id}
    chains = []
    for t in tables:
        if t.table_id in is_continuation:
            continue  # reached from its chain head
        chain = [t]
        cur = t
        while cur.table_id is not None and cur.table_id in next_of:
            cur = next_of[cur.table_id]
            chain.append(cur)
        chains.append(chain)
    return chains


def _serialize_structure(
    structure, labels_by_page: dict[int, tuple[dict, ...]], *, arithmetic: bool = True
) -> tuple[list[dict], list[dict], dict[int, list[str]], dict[int, list[str]]]:
    """Serialize ODL structure (bbox-grounded): merge page-spanning tables into one logical table
    (source_pages), emit per-cell bbox, backfill missing labels from VLM-detected captions (R4.3),
    and add VLM-detected figures ODL missed. Every entry is `source`-tagged."""
    page_tables: dict[int, list[str]] = defaultdict(list)
    page_figures: dict[int, list[str]] = defaultdict(list)

    all_tables = [t for page in structure.pages for t in substantial_tables(page)]
    tables: list[dict] = []
    for chain in _table_chains(all_tables):
        head = chain[0]
        tid = f"t{len(tables) + 1:03d}"
        source_pages: list[int] = []
        regions, cells, boxes = [], [], []
        for seg in chain:
            p1 = seg.page_index + 1
            if p1 not in source_pages:
                source_pages.append(p1)
            regions.append({"page": p1, "bbox": list(seg.bbox)})
            cells.extend(seg.cells)
            boxes.extend(seg.cell_boxes)
            page_tables[seg.page_index].append(tid)
        label, caption = head.label, head.caption
        if label is None:  # ODL missed the caption; use a VLM-read one on the head page
            vlm_t = [lbl for lbl in labels_by_page.get(head.page_index, ()) if lbl["kind"] == "table"]
            if vlm_t:
                label, caption = vlm_t[0]["label"], vlm_t[0]["caption"]
        arith = _check_arithmetic(cells) if arithmetic else None  # R8.7 invariant guard (None if no total row)
        tables.append({
            "table_id": tid, "label": label, "caption": caption, "source": "odl",
            "source_pages": source_pages,  # start/end = source_pages[0]/[-1]
            "regions": regions, "n_rows": sum(t.n_rows for t in chain), "n_cols": head.n_cols,
            "cells": _rich_cells(tuple(cells), tuple(boxes)), "continued": len(chain) > 1,
            "arithmetic": arith,
            "views": {"md": f"tables/{tid}.md", "json": f"tables/{tid}.json"},
        })

    figures: list[dict] = []
    for page in structure.pages:
        pi = page.page_index
        vlm_figures = [lbl for lbl in labels_by_page.get(pi, ()) if lbl["kind"] == "figure"]
        for image in page.images:
            fid = f"f{len(figures) + 1:03d}"
            label, caption = image.label, image.caption
            if label is None and vlm_figures:
                vlm = vlm_figures.pop(0)
                label, caption = vlm["label"], vlm["caption"]
            figures.append({
                "figure_id": fid, "label": label, "caption": caption, "source": "odl",
                "page": pi + 1, "bbox": list(image.bbox), "file": None, "kind": image.kind,
            })
            page_figures[pi].append(fid)
        for vlm in vlm_figures:  # VLM-detected figures ODL missed entirely (no bbox/asset)
            fid = f"f{len(figures) + 1:03d}"
            figures.append({
                "figure_id": fid, "label": vlm["label"], "caption": vlm["caption"], "source": "vlm",
                "page": pi + 1, "bbox": None, "file": None, "kind": "figure",
            })
            page_figures[pi].append(fid)
    return tables, figures, page_tables, page_figures


def _write_assets(out: Path, figures: list[dict], pdf_path: str | None, *, scale: float = 2.0) -> None:
    """Crop each figure's bbox from the rendered page to assets/<figure_id>.png and set its
    `file` pointer. ODL bbox is PDF space (origin bottom-left); the render is top-left."""
    if not figures or not pdf_path:
        return
    import io

    import pypdfium2 as pdfium
    from PIL import Image

    from .render import render_page_png

    adir = out / "assets"
    adir.mkdir(exist_ok=True)
    doc = pdfium.PdfDocument(pdf_path)
    try:
        rendered: dict[int, Image.Image] = {}
        heights: dict[int, float] = {}
        for fig in figures:
            if not fig.get("bbox"):  # VLM-detected figure has no bbox to crop
                continue
            pi = fig["page"] - 1
            if pi not in rendered:
                rendered[pi] = Image.open(io.BytesIO(render_page_png(pdf_path, pi, scale=scale))).convert("RGB")
                heights[pi] = doc[pi].get_size()[1]
            img, h = rendered[pi], heights[pi]
            x0, y0, x1, y1 = fig["bbox"]
            box = (int(x0 * scale), int((h - y1) * scale), int(x1 * scale), int((h - y0) * scale))
            box = (max(0, box[0]), max(0, box[1]), min(img.width, box[2]), min(img.height, box[3]))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            name = f"{fig['figure_id']}.png"
            img.crop(box).save(adir / name)
            fig["file"] = f"assets/{name}"
    finally:
        doc.close()


def _write_document_json(out: Path, result: DocumentResult, tables: list[dict], figures: list[dict],
                         page_tables: dict[int, list[str]], page_figures: dict[int, list[str]]) -> None:
    doc = result.meta.to_dict()
    paragraphs_by_page = {}
    if result.structure is not None:
        paragraphs_by_page = {pg.page_index: pg.paragraphs for pg in result.structure.pages}
    doc["pages"] = [
        {
            "page_index": p.page_index, "page_number": p.page_index + 1, "page_label": None,
            "mode": p.route, "used_vlm": p.used_vlm, "flags": list(p.flags),
            "markdown_file": f"pages/page-{p.page_index:03d}.md",
            "tables": page_tables.get(p.page_index, []), "figures": page_figures.get(p.page_index, []),
            "blocks": [{"kind": b.kind, "bbox": list(b.bbox), "text": b.text}
                       for b in paragraphs_by_page.get(p.page_index, ())],
        }
        for p in result.pages if p.route != "folded"
    ]
    doc["tables"] = tables
    doc["figures"] = figures
    (out / "document.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_tables(out: Path, tables: list[dict]) -> None:
    if not tables:
        return
    tdir = out / "tables"
    tdir.mkdir(exist_ok=True)
    for table in tables:
        (tdir / f"{table['table_id']}.json").write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
        (tdir / f"{table['table_id']}.md").write_text(_table_md(table["cells"]), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            f.write("\n")
