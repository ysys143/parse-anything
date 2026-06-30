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
from collections.abc import Iterable
from pathlib import Path

from .outline import resolve_heading_authority
from .pageno import extract_printed_page_numbers, printed_to_index
from .reflow import reflow_markdown
from .run import DocumentResult
from .sections import apply_heading_levels, build_sections, heading_levels
from .structure import build_graph


def document_dir(out_root: str | Path, result: DocumentResult) -> Path:
    """The per-document output directory: <out_root>/<source_id>/<document_id>. Falls back to
    out_root when the result has no metadata (legacy callers)."""
    meta = result.meta
    if meta is None:
        return Path(out_root)
    return Path(out_root) / meta.source_id / meta.document_id


def _anchor_line(norm_lines: list[str], text: str) -> int | None:
    """Index of the Markdown line carrying the anchor block's text, matching the LONGEST leading
    word-phrase that appears on a line. ODL joins reading-order text the VLM may re-split across
    table cells, so a fixed-length prefix breaks: we shrink the phrase word-by-word until it lands
    (preferring the most specific match), then give up below 4 chars to avoid trivial collisions."""
    words = " ".join((text or "").split()).split()
    for n in range(len(words), 0, -1):
        tok = " ".join(words[:n])
        if len(tok) < 4:
            break
        for i, nl in enumerate(norm_lines):
            if tok in nl:
                return i
    return None


def _snap_past_table(lines: list[str], idx: int) -> int:
    """If the anchor line is part of a Markdown pipe-table, advance to the table's last row. Inserting
    an image between a table's header and separator (or mid-body) breaks the table, so we place the
    figure just after the whole contiguous table block instead."""
    if "|" not in lines[idx]:
        return idx
    j = idx
    while j + 1 < len(lines) and lines[j + 1].strip() and "|" in lines[j + 1]:
        j += 1
    return j


def interleave_figures(markdown: str, figs: list[dict], blocks: tuple) -> str:
    """Insert ODL figure image references into a page's VLM Markdown at reading-order position.

    Our deterministic layer (ODL) detects figure regions -- signatures, stamps, logos -- with a
    bbox that a pure VLM transcription lacks. So a VLM types a signature out as text and loses the
    fact it is a mark, not characters. Here we re-attach each figure as ``![label](assets/fNNN.png)``
    just after the nearest text block above it (top-to-bottom reading order). The VLM's transcription
    is left in place: loss-aware -- nothing removed, so searchable text AND the original image both
    survive. This is a born-digital capability a single OCR pass cannot reproduce (no figure channel).
    """
    if not figs:
        return markdown
    lines = markdown.split("\n")
    norm = [" ".join(ln.split()) for ln in lines]
    top_refs: list[str] = []
    end_refs: list[str] = []
    placed: list[tuple[int, str]] = []
    for fig in sorted(figs, key=lambda f: -f["bbox"][3]):  # top of page first (larger y = higher)
        ref = f'![{fig.get("label") or "figure"}]({fig["file"]})'
        if not blocks:
            end_refs.append(ref)
            continue
        fy = fig["bbox"][3]
        above = [b for b in blocks if b.bbox[3] >= fy]
        if not above:  # figure sits above all text -> page top (e.g. header logo)
            top_refs.append(ref)
            continue
        anchor = min(above, key=lambda b: b.bbox[3])  # closest block above the figure
        idx = _anchor_line(norm, anchor.text)
        if idx is None:  # anchor text not found in the VLM output -> append (still present, not lost)
            end_refs.append(ref)
        else:
            placed.append((_snap_past_table(lines, idx), ref))
    for idx, ref in sorted(placed, key=lambda x: -x[0]):  # bottom-up insert keeps earlier indices valid
        lines[idx + 1:idx + 1] = ["", ref]
    if top_refs:
        prefix: list[str] = []
        for r in top_refs:
            prefix += [r, ""]
        lines[0:0] = prefix
    out = "\n".join(lines)
    if end_refs:
        out = out + "\n\n" + "\n\n".join(end_refs)
    return out


def write_outputs(result: DocumentResult, out_dir: str | Path, *, pdf_path: str | None = None,
                  arithmetic: bool = True, inline_figures: bool = True, headings: bool = True) -> None:
    out = Path(out_dir)
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Collect structure + crop figure assets up front so their references can be interleaved into
    # the page Markdown at reading-order position (R11 figure fidelity) before the pages are written.
    pages_meta: dict[int, dict] = {}
    blocks: list[dict] = []
    tables: list[dict] = []
    figures: list[dict] = []
    sections: list[dict] = []
    page_labels: dict[int, str | None] = {}
    page_headings: dict[int, list[tuple[str, int]]] = {}
    figs_by_page: dict[int, list[dict]] = {}
    blocks_by_page: dict[int, tuple] = {}
    if result.meta is not None and result.structure is not None:
        labels_by_page = {p.page_index: p.labels for p in result.pages}
        pages_meta, blocks, tables, figures = build_graph(result.structure, labels_by_page, arithmetic=arithmetic)
        for t in tables:  # per-table view files are named by the table's graph id
            t["views"] = {"md": f"tables/{t['id']}.md", "json": f"tables/{t['id']}.json"}
        _write_assets(out, figures, pdf_path)  # fills each figure["file"]
        for f in figures:
            if f.get("file") and f.get("bbox"):  # only ODL figures with a real crop can be inlined
                figs_by_page.setdefault(f["page"] - 1, []).append(f)
        blocks_by_page = {pg.page_index: pg.paragraphs for pg in result.structure.pages}
        if headings:  # R13 section hierarchy: cascade authority -> levels -> sections tree + md #
            page_labels = extract_printed_page_numbers(pdf_path, result.meta.n_pages) if pdf_path else {}
            authority = resolve_heading_authority(pdf_path, result.structure)
            level_map = heading_levels(blocks, authority, printed_to_index(page_labels))
            sections, section_by_node = build_sections(blocks, tables, figures, level_map)
            for node in (*blocks, *tables, *figures):
                if node["id"] in section_by_node:
                    node["section"] = section_by_node[node["id"]]
            by_id = {b["id"]: b for b in blocks}
            for bid, lvl in level_map.items():
                b = by_id[bid]
                page_headings.setdefault(b["page"] - 1, []).append((b["text"], lvl))

    results: list[dict] = []
    doc_parts: list[str] = []
    seen_headings: set[str] = set()  # de-dup chapter/section running headers repeated across pages
    for p in result.pages:
        record = {"page_index": p.page_index, "route": p.route, "used_vlm": p.used_vlm, "flags": list(p.flags)}
        if p.route == "folded":
            results.append(record)
            continue
        markdown = reflow_markdown(p.markdown)  # join column-wrapped lines into flowing paragraphs
        if headings:  # detect heading lines IN the markdown; section level-map refines where it matches
            markdown = apply_heading_levels(markdown, page_headings.get(p.page_index, []), seen=seen_headings)
        if inline_figures and p.page_index in figs_by_page:
            markdown = interleave_figures(markdown, figs_by_page[p.page_index], blocks_by_page.get(p.page_index, ()))
        name = f"page-{p.page_index:03d}.md"
        (pages_dir / name).write_text(markdown, encoding="utf-8")
        record["markdown_file"] = f"pages/{name}"
        results.append(record)
        doc_parts.append(markdown)

    (out / "document.md").write_text("\n\n---\n\n".join(doc_parts), encoding="utf-8")
    _write_jsonl(out / "ledger.jsonl", result.ledger())
    _write_jsonl(out / "results.jsonl", results)

    if result.meta is not None:
        _write_document_json(out, result, pages_meta, blocks, tables, figures, sections, page_labels)
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
            name = f"{fig['id']}.png"
            img.crop(box).save(adir / name)
            fig["file"] = f"assets/{name}"
    finally:
        doc.close()


def _write_document_json(out: Path, result: DocumentResult, pages_meta: dict[int, dict],
                         blocks: list[dict], tables: list[dict], figures: list[dict],
                         sections: list[dict], page_labels: dict[int, str | None]) -> None:
    """Emit the R12/R13 graph: per-page reading-order ``content`` (id stream) + typed id lists, the
    document-level ``blocks``/``tables``/``figures``/``sections`` registries keyed by stable id, and
    each page's printed ``page_label``."""
    doc = result.meta.to_dict()
    doc["pages"] = [
        {
            "page_index": p.page_index, "page_number": p.page_index + 1,
            "page_label": page_labels.get(p.page_index),
            "mode": p.route, "used_vlm": p.used_vlm, "flags": list(p.flags),
            "markdown_file": f"pages/page-{p.page_index:03d}.md",
            "content": pages_meta.get(p.page_index, {}).get("content", []),
            "blocks": pages_meta.get(p.page_index, {}).get("blocks", []),
            "tables": pages_meta.get(p.page_index, {}).get("tables", []),
            "figures": pages_meta.get(p.page_index, {}).get("figures", []),
        }
        for p in result.pages if p.route != "folded"
    ]
    doc["sections"] = sections
    doc["blocks"] = blocks
    doc["tables"] = tables
    doc["figures"] = figures
    (out / "document.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_tables(out: Path, tables: list[dict]) -> None:
    if not tables:
        return
    tdir = out / "tables"
    tdir.mkdir(exist_ok=True)
    for table in tables:
        (tdir / f"{table['id']}.json").write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
        (tdir / f"{table['id']}.md").write_text(_table_md(table["cells"]), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            f.write("\n")
