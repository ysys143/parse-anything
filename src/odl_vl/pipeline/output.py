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
from .sections import _assign_heading_levels, apply_heading_levels, build_sections, strip_page_furniture
from .structure import build_graph
from .textalign import common_prefix_len, norm_block


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
        cap, label = (fig.get("caption") or "").strip(), (fig.get("label") or "").strip()
        # Recover a caption the transcription dropped: a full-page figure leaves a page the VLM types as
        # empty and ODL files it under type=caption (so it never reaches the body). Emit the figure's ODL-
        # bound caption ONLY when it starts with the figure label (guards an ODL mis-binding) AND the VLM
        # has not already transcribed it -- presence by longest-common-prefix (the align primitive), robust
        # to the VLM's bold/italic rendering rather than a brittle fixed-length substring.
        cap_norm = norm_block(cap)
        already = any(common_prefix_len(cap_norm, norm_block(ln)) >= 20 for ln in lines if len(ln.strip()) >= 15)
        if cap and label and cap_norm.startswith(norm_block(label)) and not already:
            ref += "\n\n" + cap
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


_CAP_LABEL_TITLE = re.compile(
    r"^((?:S\d+\s+(?:Fig|Table)|Fig(?:ure)?\s*\d+|Table\s*\d+|図\s*\d+|表\s*\d+|그림\s*\d+|표\s*\d+)\.?\s+.*?[.．])(\s.*|)$",
    re.IGNORECASE)


_FIG_SOURCE = re.compile(r"^(https?://\S+\.g\d+)\s*$")


def _label_figure_sources(markdown: str) -> str:
    """Prefix a bare figure-source DOI line ('https://doi.org/….g007') with 'Source: ' so it reads as
    the figure's data link, not a stray URL in the body."""
    return "\n".join(f"Source: {m.group(1)}" if (m := _FIG_SOURCE.match(ln.strip())) else ln
                      for ln in markdown.split("\n"))


def _normalize_captions(markdown: str) -> str:
    """Bold every caption's label+title sentence uniformly ('**Fig 7. Title.** rest…'). The VLM renders
    some captions bold and some plain (F/S figures alike); this makes them consistent. Inline emphasis
    inside the caption body (``*toi*``) is preserved -- only the label-bold is normalized."""
    out = []
    for line in markdown.split("\n"):
        body = re.sub(r"\*\*", "", line).strip()   # drop any existing bold marks, keep single-* italics
        m = _CAP_LABEL_TITLE.match(body)
        out.append(f"**{m.group(1)}**{m.group(2)}" if m else line)
    return "\n".join(out)


_PAGE_TERMINATORS = "。．.!?！？"  # a page ending here finished its sentence; absence => mid-sentence cut
_URL_END = re.compile(r"https?://\S+$")            # a line whose tail is a URL (possibly cut mid-URL)
_URL_CONT = re.compile(r"^[A-Za-z0-9]+[./]\S*")    # a block that opens as a URL path/domain fragment


_FIG_UNIT = re.compile(r"^\s*(?:!\[|(?:\*\*)?\s*(?:Fig(?:ure)?|Table|표|그림|表|図|圖)\.?\s*\d)", re.IGNORECASE)


def _starts_figure_unit(first: str) -> bool:
    """The block opens with a figure image or a caption ('Fig 2.', 'Table 1', '図3') -- a self-contained
    unit that must not be folded into the previous page's prose."""
    return bool(_FIG_UNIT.match(first))


def _ends_with_url(line: str) -> bool:
    return bool(_URL_END.search(line.rstrip()))


def _is_url_continuation(first: str) -> bool:
    """The block opens as a bare URL fragment ('org/10.5281/zenodo…') -- i.e. a URL that wrapped across
    the page break, not prose."""
    tok = first.lstrip().split(" ", 1)[0]
    return bool(_URL_CONT.match(tok)) and ("/" in tok or "." in tok)


_FIG_IMG = re.compile(r"^!\[(Fig(?:ure)?\s*\d+|Table\s*\d+)\]", re.IGNORECASE)
_SOURCE_LINE = re.compile(r"^Source:\s*https?://")
_PAGE_MARKER = re.compile(r"^<!-- page[^>]*-->$")


def _is_figure_caption(block: str, label: str) -> bool:
    return re.match(rf"^\*?\*?\s*{re.escape(label)}\.", block.strip(), re.I) is not None


def _consolidate_figure_units(markdown: str) -> str:
    """Regroup each figure into one contiguous unit: image, then its caption, then its Source line. The
    pieces already sit in reading order but a multi-page caption straddles the image (a head above, a
    tail below), and a body paragraph or the caption's second half can land between the image and its
    caption. Attach the caption to its image in every arrangement -- a split head+tail is merged; a
    caption found below (even past an interposed body paragraph, which is left to follow the unit) is
    pulled up. Its Source line is attached when it sits just after the caption (skipping page markers).
    Body is never consumed: only the caption/tail/source blocks move, never a plain paragraph."""
    blocks = re.split(r"\n\n+", markdown)
    remove: set[int] = set()
    result = list(blocks)
    for i, b in enumerate(blocks):
        m = _FIG_IMG.match(b.strip())
        if not m:
            continue
        label = m.group(1)
        cap_parts: list[int] = []
        source: int | None = None
        if i > 0 and (i - 1) not in remove and _is_figure_caption(blocks[i - 1], label):
            # split caption: head above the image, continuation tail below until the Source line
            cap_parts.append(i - 1)
            remove.add(i - 1)
            j = i + 1
            while j < len(blocks) and j - i <= 5 and j not in remove:
                bs = blocks[j].strip()
                if _SOURCE_LINE.match(bs):
                    source = j
                    remove.add(j)
                    break
                if bs.startswith(("![", "#")):
                    break
                cap_parts.append(j)
                remove.add(j)
                j += 1
        else:
            # caption below the image (possibly past an interposed body paragraph): find it by label
            cap_idx = None
            for j in range(i + 1, min(len(blocks), i + 7)):
                if j in remove:
                    continue
                if _is_figure_caption(blocks[j], label):
                    cap_idx = j
                    break
                if blocks[j].strip().startswith(("![", "#")):   # next figure / heading -> stop
                    break
            if cap_idx is None:                                 # no caption found -> leave figure untouched
                continue
            cap_parts.append(cap_idx)
            remove.add(cap_idx)
            j = cap_idx + 1                                     # attach the Source line, skipping page markers
            while j < len(blocks) and j - cap_idx <= 3 and j not in remove:
                if _PAGE_MARKER.match(blocks[j].strip()):
                    remove.add(j)
                    j += 1
                    continue
                if _SOURCE_LINE.match(blocks[j].strip()):
                    source = j
                    remove.add(j)
                break
        cap = " ".join(blocks[k].strip() for k in cap_parts)
        cap = re.sub(r"\s*<!-- page[^>]*-->\s*", " ", cap)     # drop page markers merged into the caption
        cap = re.sub(r"\s{2,}", " ", cap).strip()
        unit = b.strip()
        if cap:
            unit += "\n\n" + cap
        if source is not None:
            unit += "\n\n" + blocks[source].strip()
        result[i] = unit
    return "\n\n".join(result[k] for k in range(len(result)) if k not in remove)


def _stitch_broken_paragraphs(markdown: str) -> str:
    """Rejoin two adjacent blocks that are one paragraph split apart -- the first ends mid-sentence, the
    second continues in lower case. Pulling a figure out from between a paragraph's two halves leaves
    such a split; this merges it. Never merges a structural block (heading, image, caption, source, list),
    a display equation, or a URL fragment, and only when the continuation opens in lower case (a new
    paragraph opens with a capital)."""
    blocks = re.split(r"\n\n+", markdown)
    out: list[str] = []
    for b in blocks:
        if out and b.strip():
            last = out[-1].rstrip()
            first = b.lstrip()
            last_line = last.rsplit("\n", 1)[-1]
            fc = first[:1]
            if (
                (fc.islower() or _is_cjk(fc))
                and last[-1:] not in _PAGE_TERMINATORS
                and "$$" not in last and not last.endswith("$") and not first.startswith("$")
                and not _is_url_continuation(first) and "-->" not in last[-24:]
                and not last_line.startswith(("![", "#", "Source:", "|", ">"))
                and not first.startswith(("![", "#", "Source:", "**", ">", "|", "<!--"))
                and not _no_fold_into(last_line) and not _starts_unit(first) and not _starts_figure_unit(first)
            ):
                sep = "" if (_is_cjk(last[-1:]) or _is_cjk(fc)) else " "
                out[-1] = f"{last}{sep}{first}"
                continue
        out.append(b)
    return "\n\n".join(out)


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
        if _ends_with_url(last):  # last line ends with a URL -> handle by URL structure, not sentence rules
            if _is_url_continuation(first):  # the URL was split across the page break -> rejoin, no space
                out = f"{out}{first.lstrip()}{rest}"
            else:  # a complete URL/DOI (e.g. a figure-source line) -> keep the next block separate
                out = f"{out}\n\n{marker}\n\n{md}" if marker else f"{out}\n\n{md}"
            continue
        stitch = bool(last) and last.rstrip()[-1:] not in _PAGE_TERMINATORS \
            and "|" not in last and "|" not in first \
            and not _no_fold_into(last) and not _starts_unit(first) \
            and not _starts_figure_unit(first)  # a caption/image opening a page is its own block
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
    style_levels: dict[str, int] = {}
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
            txt = {pg.page_index: [p.bbox for p in pg.paragraphs] for pg in result.structure.pages}
            for pi, bboxes in detect_vector_figures(pdf_path, tbp, txt).items():
                meta = pages_meta.setdefault(pi, {"content": [], "blocks": [], "tables": [], "figures": []})
                for k, bbox in enumerate(bboxes):
                    fid = f"p{pi + 1}_vec{k}"
                    figures.append({"id": fid, "type": "figure", "page": pi + 1, "bbox": list(bbox),
                                    "order": 10_000 + k, "source": "vector", "caption_id": None,
                                    "caption": None, "label": None})
                    meta["figures"].append(fid)
                    meta["content"].append(fid)
        figures = [f for f in figures if not _tiny_figure(f.get("bbox"))]  # drop hairline icons/logos
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
        _mark_chart_label_blocks(figures, blocks)  # flag the same labels in the JSON graph (filterable)
        _resolve_cross_references(blocks, tables, figures)  # in-text 表N/図N mentions -> refs edges
        if headings:  # R13 section hierarchy: cascade authority -> levels -> sections tree + md #
            page_labels = extract_printed_page_numbers(pdf_path, result.meta.n_pages) if pdf_path else {}
            authority = resolve_heading_authority(pdf_path, result.structure)
            level_map, style_levels = _assign_heading_levels(blocks, authority, printed_to_index(page_labels))
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
            markdown = apply_heading_levels(markdown, page_headings.get(p.page_index, []), style_levels=style_levels)
        if inline_figures and p.page_index in figs_by_page:
            markdown = interleave_figures(markdown, figs_by_page[p.page_index], blocks_by_page.get(p.page_index, ()))
        markdown = _PLACEHOLDER_RE.sub("", markdown)  # drop bare VLM [figure]/[image] placeholders
        name = f"page-{p.page_index:03d}.md"
        md_by_index[p.page_index] = markdown
        record["markdown_file"] = f"pages/{name}"
        results.append(record)
        rendered.append((p.page_index, name))

    if headings:  # document-level: drop running headers + printed-page-number leaks (page furniture)
        # ODL already filters running headers/footers -> a VLM line matching no ODL block is furniture.
        odl_norms_by_page = {pi: [norm_block(p.text) for p in paras] for pi, paras in blocks_by_page.items()}
        md_by_index = strip_page_furniture(md_by_index, page_labels, odl_norms_by_page)
    md_by_index = {pi: _normalize_captions(md) for pi, md in md_by_index.items()}  # uniform caption bold
    md_by_index = {pi: _label_figure_sources(md) for pi, md in md_by_index.items()}  # label figure DOIs

    for page_index, name in rendered:
        (pages_dir / name).write_text(md_by_index[page_index], encoding="utf-8")  # per-page keeps the split
    pages_doc = [(page_labels.get(pi) or str(pi + 1), md_by_index[pi]) for pi, _ in rendered]
    (out / "document.md").write_text(
        _stitch_broken_paragraphs(_consolidate_figure_units(_assemble_document(pages_doc))), encoding="utf-8")
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


def _tiny_figure(bbox) -> bool:
    """A hairline rule or a tiny icon/logo, not a content figure. Figures with no bbox (caption-only
    nodes) are kept."""
    if not bbox:
        return False
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    return w * h < 900 or min(w, h) < 12


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


_DASHES = str.maketrans("‐‑‒–—―−－", "--------")


def _ref_norm(s: str) -> str:
    """Whitespace-free, dash-unified form for matching a 表N/図N reference across column wraps."""
    return re.sub(r"\s+", "", s).translate(_DASHES)


def _resolve_cross_references(blocks: list[dict], tables: list[dict], figures: list[dict]) -> None:
    """Resolve each block's in-text 表N/図N mentions to the referenced table/figure node ids and store
    them as a ``refs`` edge -- robust to column-wrap whitespace and dash variants. A section's RELATED
    objects are then its contained content PLUS these referenced edges, both read straight from the
    graph in a single pass (no second retrieval, no regex at query time)."""
    index = [(_ref_norm(n["label"]), n["id"]) for n in (*tables, *figures) if n.get("label")]
    for b in blocks:
        norm = _ref_norm(b.get("text", ""))
        refs = [nid for lab, nid in index
                if lab and not norm.startswith(lab)  # skip a node's own leading caption
                and re.search(re.escape(lab) + r"(?!\d)", norm)]
        if refs:
            b["refs"] = sorted(set(refs))


def _mark_chart_label_blocks(figures: list[dict], blocks: list[dict]) -> None:
    """Flag graph blocks that are a chart's internal labels (legend/axis/year) with ``figure``=its id,
    so a JSON consumer can exclude them from text retrieval/embedding -- the loss-aware mirror of the
    Markdown suppression (data kept, but filterable)."""
    by_page: dict[object, list[dict]] = {}
    for b in blocks:
        by_page.setdefault(b.get("page"), []).append(b)
    for f in figures:
        if f.get("source") != "vector" or not f.get("bbox"):
            continue
        x0, y0, x1, y1 = f["bbox"]
        for b in by_page.get(f["page"], []):
            bb = b.get("bbox")
            if not bb:
                continue
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            if x0 <= cx <= x1 and y0 <= cy <= y1 and not _KEEP_IN_FIG.match(b.get("text", "")):
                b["figure"] = f["id"]


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
