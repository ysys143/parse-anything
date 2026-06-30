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
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from .outline import resolve_heading_authority
from .pageno import extract_printed_page_numbers, printed_to_index
from .reflow import _is_cjk, _no_fold_into, _starts_unit, reflow_markdown
from .run import DocumentResult
from .sections import apply_heading_levels, build_sections, heading_levels, strip_page_furniture
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
        if fig.get("description"):  # a VLM text description of the chart, as a blockquote under the image
            ref += "\n\n> " + " ".join(fig["description"].split())
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


_PAGE_TERMINATORS = "。．.!?！？"  # a page ending here finished its sentence; absence => mid-sentence cut


def _assemble_document(pages: list[tuple[str | None, str]]) -> str:
    """Assemble per-page Markdown into one continuous document. The page boundary is a physical PDF
    artifact, not document structure, so a sentence wrapped across it is STITCHED back (the same
    continuation rule reflow uses within a page, plus a terminator check since the page break carries
    no blank-line signal). Each page is marked with an invisible ``<!-- page N -->`` comment (printed
    label) so provenance survives without interrupting the prose. The per-page files keep the splits."""
    out = ""
    for i, (label, md) in enumerate(pages):
        md = md.strip("\n")
        marker = f"<!-- page {label} -->" if label else ""
        if i == 0:
            out = f"{marker}\n\n{md}" if marker else md
            continue
        if not md:
            out += f"\n\n{marker}" if marker else ""
            continue
        last = out.rsplit("\n", 1)[-1]
        first = md.split("\n", 1)[0]
        rest = md[len(first):]
        stitch = bool(last) and last.rstrip()[-1:] not in _PAGE_TERMINATORS \
            and "|" not in last and "|" not in first \
            and not _no_fold_into(last) and not _starts_unit(first)
        if stitch:  # mid-sentence wrap -> join the fragments, marker invisibly between them
            sep = "" if (_is_cjk(last[-1:]) or _is_cjk(first.lstrip()[:1])) else " "
            out = f"{out}{marker}{sep}{first.lstrip()}{rest}"
        else:
            out = f"{out}\n\n{marker}\n\n{md}" if marker else f"{out}\n\n{md}"
    return out


def write_outputs(result: DocumentResult, out_dir: str | Path, *, pdf_path: str | None = None,
                  arithmetic: bool = True, inline_figures: bool = True, headings: bool = True,
                  describe_figure: "Callable[[bytes, str | None], str] | None" = None) -> None:
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
    chart_noise: dict[int, set[str]] = {}
    if result.meta is not None and result.structure is not None:
        labels_by_page = {p.page_index: p.labels for p in result.pages}
        pages_meta, blocks, tables, figures = build_graph(result.structure, labels_by_page, arithmetic=arithmetic)
        for t in tables:  # per-table view files are named by the table's graph id
            t["views"] = {"md": f"tables/{t['id']}.md", "json": f"tables/{t['id']}.json"}
        if inline_figures and pdf_path:  # R14: recover vector charts ODL's raster-figure detector misses
            from .vecfig import detect_vector_figures
            tbp = {pg.page_index: [t.bbox for t in pg.tables] for pg in result.structure.pages}
            for pi, bboxes in detect_vector_figures(pdf_path, tbp).items():
                meta = pages_meta.setdefault(pi, {"content": [], "blocks": [], "tables": [], "figures": []})
                for k, bbox in enumerate(bboxes):
                    fid = f"p{pi + 1}_vec{k}"
                    figures.append({"id": fid, "type": "figure", "page": pi + 1, "bbox": list(bbox),
                                    "order": 10_000 + k, "source": "vector", "caption_id": None,
                                    "caption": None, "label": None})
                    meta["figures"].append(fid)
                    meta["content"].append(fid)
        _write_assets(out, figures, pdf_path)  # fills each figure["file"]
        _bind_vector_captions(figures, blocks)  # 図N label + caption text (both modes)
        if describe_figure is not None:  # R14: VLM text description per cropped vector chart (det_vlm)
            for f in figures:
                if f.get("source") == "vector" and f.get("file"):
                    try:
                        desc = describe_figure((out / f["file"]).read_bytes(), f.get("caption"))
                    except Exception:  # noqa: BLE001 -- a failed description must not abort the run
                        desc = ""
                    if desc and desc.strip():
                        f["description"] = desc.strip()
        for f in figures:
            if f.get("file") and f.get("bbox"):  # only figures with a real crop can be inlined
                figs_by_page.setdefault(f["page"] - 1, []).append(f)
        blocks_by_page = {pg.page_index: pg.paragraphs for pg in result.structure.pages}
        chart_noise = _chart_internal_noise(figures, blocks_by_page)  # legend/axis/year labels to drop
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
    rendered: list[tuple[int, str]] = []     # (page_index, page-md filename) in document order
    md_by_index: dict[int, str] = {}
    for p in result.pages:
        record = {"page_index": p.page_index, "route": p.route, "used_vlm": p.used_vlm, "flags": list(p.flags)}
        if p.route == "folded":
            results.append(record)
            continue
        markdown = p.markdown
        if p.page_index in chart_noise:  # drop chart-internal legend/axis/year labels (visual-only noise)
            markdown = _suppress_chart_noise(markdown, chart_noise[p.page_index])
        markdown = reflow_markdown(markdown)  # join column-wrapped lines into flowing paragraphs
        if headings:  # detect heading lines IN the markdown; section level-map refines where it matches
            markdown = apply_heading_levels(markdown, page_headings.get(p.page_index, []))
        if inline_figures and p.page_index in figs_by_page:
            markdown = interleave_figures(markdown, figs_by_page[p.page_index], blocks_by_page.get(p.page_index, ()))
        markdown = _PLACEHOLDER_RE.sub("", markdown)  # drop bare VLM [figure]/[image] placeholders
        name = f"page-{p.page_index:03d}.md"
        md_by_index[p.page_index] = markdown
        record["markdown_file"] = f"pages/{name}"
        results.append(record)
        rendered.append((p.page_index, name))

    if headings:  # document-level: drop running headers + printed-page-number leaks (page furniture)
        md_by_index = strip_page_furniture(md_by_index, page_labels)

    for page_index, name in rendered:
        (pages_dir / name).write_text(md_by_index[page_index], encoding="utf-8")  # per-page keeps the split
    pages_doc = [(page_labels.get(pi) or str(pi + 1), md_by_index[pi]) for pi, _ in rendered]
    (out / "document.md").write_text(_assemble_document(pages_doc), encoding="utf-8")
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


_PLACEHOLDER_RE = re.compile(r"(?im)^[ \t]*\[(?:figure|image)\][ \t]*\n?")  # bare VLM figure placeholder
_FIG_CAPTION_RE = re.compile(r"(?i)[<〈【［(]?\s*((?:図|圖|图|그림|figure|fig\.?|表|table)\s*[0-9０-９][-.‐-―−－0-9０-９]*)")
# Inside a chart's bbox, KEEP the caption + source/note lines; everything else (legend, axis ticks,
# year labels) is visual-only and meaningless to a text model -- suppress it from the prose.
_KEEP_IN_FIG = re.compile(r"(?i)^\s*(?:[<〈【［(]?\s*(?:図|圖|图|表|table|figure|fig|그림|표)\s*\d"
                          r"|備考|注記|資料|出典|出所|出處|source|note)")


def _bind_vector_captions(figures: list[dict], blocks: list[dict]) -> None:
    """Attach each vector figure's nearest 図N caption block (label + caption text) by bbox proximity."""
    caps_by_page: dict[int, list[dict]] = {}
    for b in blocks:
        if _FIG_CAPTION_RE.match(b.get("text", "")):
            caps_by_page.setdefault(b["page"], []).append(b)
    for f in figures:
        if f.get("source") != "vector" or not f.get("bbox"):
            continue
        fx0, _fy0, fx1, fy1 = f["bbox"]
        page_caps = caps_by_page.get(f["page"], [])
        caps = [b for b in page_caps if not (b["bbox"][2] < fx0 or b["bbox"][0] > fx1)] or page_caps
        if not caps:
            continue
        cap = min(caps, key=lambda b: abs((b["bbox"][1] + b["bbox"][3]) / 2 - fy1))
        m = _FIG_CAPTION_RE.match(cap["text"])
        f["label"] = m.group(1) if m else None
        f["caption"] = cap["text"]
        f["caption_id"] = cap.get("id")


def _chart_internal_noise(figures: list[dict], blocks_by_page: dict[int, tuple]) -> dict[int, set[str]]:
    """Per page, ODL paragraph texts inside a vector chart's bbox that are NOT its caption/source line
    -- legend, axis ticks, year labels: visual-only noise to drop from prose so a text/embedding model
    sees the figure's DESCRIPTION instead of a scatter of disconnected numbers and country names."""
    out: dict[int, set[str]] = {}
    for f in figures:
        if f.get("source") != "vector" or not f.get("bbox"):
            continue
        pi = f["page"] - 1
        x0, y0, x1, y1 = f["bbox"]
        for p in blocks_by_page.get(pi, ()):
            cx, cy = (p.bbox[0] + p.bbox[2]) / 2, (p.bbox[1] + p.bbox[3]) / 2
            if x0 <= cx <= x1 and y0 <= cy <= y1 and not _KEEP_IN_FIG.match(p.text):
                out.setdefault(pi, set()).add(" ".join(p.text.split()))
    return out


def _suppress_chart_noise(markdown: str, noise: set[str]) -> str:
    """Drop standalone lines whose (whitespace-normalised) text is a chart-internal noise label."""
    return "\n".join(ln for ln in markdown.split("\n") if " ".join(ln.split()) not in noise)


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
