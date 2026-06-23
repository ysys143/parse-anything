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

from .odl_extract import substantial_tables
from .run import DocumentResult


def document_dir(out_root: str | Path, result: DocumentResult) -> Path:
    """The per-document output directory: <out_root>/<source_id>/<document_id>. Falls back to
    out_root when the result has no metadata (legacy callers)."""
    meta = result.meta
    if meta is None:
        return Path(out_root)
    return Path(out_root) / meta.source_id / meta.document_id


def write_outputs(result: DocumentResult, out_dir: str | Path) -> None:
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
        tables = _write_document_json(out, result)
        _write_tables(out, tables)


def _table_md(cells: list[list[str]]) -> str:
    if not cells:
        return ""
    width = max((len(r) for r in cells), default=0)
    rows = [list(r) + [""] * (width - len(r)) for r in cells]
    lines = ["| " + " | ".join(c.replace("|", r"\|") for c in rows[0]) + " |",
             "| " + " | ".join("---" for _ in range(width)) + " |"]
    lines += ["| " + " | ".join(c.replace("|", r"\|") for c in r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _serialize_structure(structure) -> tuple[list[dict], list[dict], dict[int, list[str]], dict[int, list[str]]]:
    tables: list[dict] = []
    figures: list[dict] = []
    page_tables: dict[int, list[str]] = defaultdict(list)
    page_figures: dict[int, list[str]] = defaultdict(list)
    for page in structure.pages:
        for table in substantial_tables(page):
            tid = f"t{len(tables) + 1:03d}"
            p1 = table.page_index + 1  # 1-based source page; R2 v1 tables are single-page
            tables.append({
                "table_id": tid, "label": table.label, "caption": table.caption,
                "start_page": p1, "end_page": p1, "source_pages": [p1],
                "regions": [{"page": p1, "bbox": list(table.bbox)}],
                "n_rows": table.n_rows, "n_cols": table.n_cols,
                "cells": [list(r) for r in table.cells], "continued": False,
                "views": {"md": f"tables/{tid}.md", "json": f"tables/{tid}.json"},
            })
            page_tables[table.page_index].append(tid)
        for image in page.images:
            fid = f"f{len(figures) + 1:03d}"
            figures.append({
                "figure_id": fid, "label": image.label, "caption": image.caption,
                "page": image.page_index + 1, "bbox": list(image.bbox),
                "file": None, "kind": image.kind,  # file filled by assets/ (R2.5)
            })
            page_figures[image.page_index].append(fid)
    return tables, figures, page_tables, page_figures


def _write_document_json(out: Path, result: DocumentResult) -> list[dict]:
    tables, figures, page_tables, page_figures = (
        _serialize_structure(result.structure) if result.structure is not None else ([], [], {}, {})
    )
    doc = result.meta.to_dict()
    doc["pages"] = [
        {
            "page_index": p.page_index, "page_number": p.page_index + 1, "page_label": None,
            "mode": p.route, "used_vlm": p.used_vlm, "flags": list(p.flags),
            "markdown_file": f"pages/page-{p.page_index:03d}.md",
            "tables": page_tables.get(p.page_index, []), "figures": page_figures.get(p.page_index, []),
        }
        for p in result.pages if p.route != "folded"
    ]
    doc["tables"] = tables
    doc["figures"] = figures
    (out / "document.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return tables


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
