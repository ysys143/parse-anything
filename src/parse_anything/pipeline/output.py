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
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ..export import ChunkRecord, Provenance, SemanticView, StructureExport
from .frontmatter import consolidate_front_matter
from .outline import resolve_heading_authority
from .pageno import extract_printed_page_numbers, printed_to_index
from .reflow import _is_cjk, _no_fold_into, _starts_unit, reflow_markdown
from .run import DocumentResult
from .sections import _assign_heading_levels, apply_heading_levels, build_sections, strip_page_furniture
from .structure import build_graph
from .textalign import common_prefix_len, norm_block

if TYPE_CHECKING:
    from .ontology import ChunkPolicy, Ontology


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


# Cross-reference abbreviations whose trailing '.' is NOT a sentence end ('Fig. 12', 'et al. 2020',
# 'e.g. panels'): the period must be absorbed into the caption title, not treated as its terminator.
# Standard-re lookbehind must be fixed-width, so each abbreviation contributes its own (\b is zero-width).
_CAP_ABBREV = ("Fig", "Figs", "Figure", "Figures", "Eq", "Eqs", "Eqn", "Ref", "Refs",
               "Sec", "Tab", "al", "vs", "cf", "e.g", "i.e")
_ABBR_DOT = "|".join(rf"(?<=\b{re.escape(a)})[.．]" for a in _CAP_ABBREV)
_CAP_LABEL_TITLE = re.compile(
    r"^("
    r"(?:S\d+\s+(?:Fig(?:ure)?|Table)|(?:Fig(?:ure)?|Table|図|表|그림|표)\s*\d+)"  # label: 'S1 Fig' or 'Figure 3'
    r"[.:]?\s+"                            # separator after the label: '.', ':' or none, then whitespace
    rf"(?:[^.．]|[.．](?!\s|$)|{_ABBR_DOT})*[.．]?"  # title: up to the first SENTENCE period; a mid-token
    r")(.*)$",                             #   period (URL/decimal) or a known abbreviation ('Fig.') is kept
    re.IGNORECASE)


_FIG_SOURCE = re.compile(r"^(https?://\S+\.g\d+)\s*$")


def _label_figure_sources(markdown: str) -> str:
    """Prefix a bare figure-source DOI line ('https://doi.org/….g007') with 'Source: ' so it reads as
    the figure's data link, not a stray URL in the body."""
    return "\n".join(f"Source: {m.group(1)}" if (m := _FIG_SOURCE.match(ln.strip())) else ln
                      for ln in markdown.split("\n"))


def _escape_currency(markdown: str) -> str:
    """A literal currency '$' ('$10/h', '$1,000.50') is not a math delimiter -- left unescaped it opens
    a math span that swallows text (and mis-pairs every '$' downstream) until the next '$'. Escape it,
    while leaving a real math token whose digits continue into LaTeX ('$5 \\times…$', '$100\\times$')."""
    return re.sub(r"\$(\d[\d,.]*)(?![\d\s\\^_{])", r"\\$\1", markdown)


def _restore_panel_labels(markdown: str) -> str:
    """The VLM sometimes reads a figure panel label '(C)' as the copyright glyph '©'. Restore it to
    '(C)', but keep a genuine copyright notice ('© 2023 …' -- a digit/year follows) untouched."""
    return re.sub(r"©(?!\s*\d)", "(C)", markdown)


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


_IMG_WITH_TAIL = re.compile(r"^(!\[[^\]]*\]\([^)]*\))\n(?!\n)(.+)$", re.S)


def _detach_image_from_trailing_text(markdown: str) -> str:
    """interleave_figures inserts an image with a blank line before but NOT after, so the image glues to
    the text block just below it (the body paragraph that sits above the figure, between the anchor and
    the figure). Split them into separate blocks, placing that text BEFORE the image -- it belongs above
    the figure -- so the image becomes its own block and the surrounding paragraph can reflow around it."""
    blocks = re.split(r"\n\n+", markdown)
    out: list[str] = []
    for b in blocks:
        m = _IMG_WITH_TAIL.match(b)
        if m and not m.group(2).lstrip().startswith(("![", "#", "**")):
            out.append(m.group(2).strip())      # body text above the figure -> before the image
            out.append(m.group(1))              # the image, now its own block
        else:
            out.append(b)
    return "\n\n".join(out)


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
            # Scan forward for the Source, gathering any wrapped caption tail (and page markers) on the
            # way, but COMMIT them only if a Source is actually found. A caption tail wraps when the prior
            # caption part ends mid-sentence and this block opens lower case; requiring the Source as proof
            # keeps a source-less figure from eating a following body paragraph.
            scan: list[int] = []
            src: int | None = None
            last_cap = cap_idx
            j = cap_idx + 1
            while j < len(blocks) and j - cap_idx <= 5 and j not in remove:
                bs = blocks[j].strip()
                if _SOURCE_LINE.match(bs):
                    src = j
                    break
                if _PAGE_MARKER.match(bs):
                    scan.append(j)
                    j += 1
                    continue
                prev = blocks[last_cap].rstrip()
                if (prev[-1:] not in _PAGE_TERMINATORS and bs[:1].islower()
                        and not bs.startswith(("![", "#"))):
                    scan.append(j)
                    last_cap = j
                    j += 1
                    continue
                break
            if src is not None:                                # proof it is a figure unit -> commit tail+source
                for k in scan:
                    cap_parts.append(k)
                    remove.add(k)
                source = src
                remove.add(src)
        cap = " ".join(blocks[k].strip() for k in cap_parts)
        if source is not None:                                   # the Source line IS part of the caption ->
            cap = f"{cap} {blocks[source].strip()}"              # attach it to the caption, no blank line
        cap = re.sub(r"\s*<!-- page[^>]*-->\s*", " ", cap)     # drop page markers merged into the caption
        cap = re.sub(r"\s{2,}", " ", cap).strip()
        unit = b.strip()
        if cap:
            unit += "\n\n" + cap
        result[i] = unit
    return "\n\n".join(result[k] for k in range(len(result)) if k not in remove)


def _can_stitch(last: str, first: str, *, cjk_ok: bool = True) -> bool:
    """Whether ``first`` continues the paragraph ``last`` was cut off in: ``last`` ends mid-sentence and
    ``first`` opens in lower case. Never fold onto or out of a structural block (heading, image, caption,
    source, list), a display equation, or a URL line -- in particular never fold body text onto a figure
    unit (which opens with an image and ends in its inline ``Source:`` DOI).

    A lower-case opener is a strong 'this is a continuation' signal in Latin scripts; CJK has no case, so
    every CJK block opens the same way and merging on that alone runs distinct items (a grid of cards, a
    list) together. ``cjk_ok`` therefore gates CJK merging: it is allowed only where a real split is
    evident (a figure floats between the halves), not for two merely adjacent CJK blocks."""
    last = last.rstrip()
    first = first.lstrip()
    if not first:
        return False
    last_line = last.rsplit("\n", 1)[-1]
    fc = first[:1]
    return (
        (fc.islower() or (cjk_ok and _is_cjk(fc)))
        and last[-1:] not in _PAGE_TERMINATORS
        and "$$" not in last and not last.endswith("$") and not first.startswith("$")
        and not _is_url_continuation(first) and "-->" not in last[-24:]
        and not last.lstrip().startswith("![")           # never fold onto a figure unit (image + caption)
        and not _ends_with_url(last_line)                 # ...or onto a line ending in a URL / figure DOI
        and not last_line.startswith(("![", "#", "Source:", "|", ">"))
        and not first.startswith(("![", "#", "Source:", "**", ">", "|", "<!--"))
        and not _no_fold_into(last_line) and not _starts_unit(first) and not _starts_figure_unit(first)
    )


def _join(last: str, first: str) -> str:
    last, first = last.rstrip(), first.lstrip()
    sep = "" if (_is_cjk(last[-1:]) or _is_cjk(first[:1])) else " "
    return f"{last}{sep}{first}"


def _is_float_block(block: str) -> bool:
    """A block that belongs to a floating figure (or the page marker beside it): an image, a figure/table
    caption, its Source line, or a ``<!-- page N -->`` marker. A run of these can sit between the two
    halves of a body paragraph the figure floats through."""
    s = block.lstrip()
    return bool(_PAGE_MARKER.match(s) or _SOURCE_LINE.match(s) or _starts_figure_unit(s))


def _stitch_broken_paragraphs(markdown: str) -> str:
    """Rejoin two blocks that are one paragraph split apart -- the first ends mid-sentence, the second
    continues in lower case. A page break, or a FIGURE that floats between the paragraph's two halves,
    causes such a split. When a run of figure/caption/source/marker blocks (containing an actual image)
    sits between the halves, the figure is a float: complete the paragraph ACROSS the run, then re-emit the
    run after the finished paragraph. Structural blocks (headings, images, captions, sources) never merge."""
    blocks = re.split(r"\n\n+", markdown)
    out: list[str] = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        # a figure floating between a paragraph's halves: skip the maximal run of float blocks; if the
        # block after it continues the paragraph in lower case, stitch across and float the run past it.
        if out and _is_float_block(b):
            j = i
            while j < len(blocks) and _is_float_block(blocks[j]):
                j += 1
            if (j < len(blocks) and any(blocks[k].lstrip().startswith("![") for k in range(i, j))
                    and _can_stitch(out[-1], blocks[j])):
                out[-1] = _join(out[-1], blocks[j])
                out.extend(blocks[i:j])                  # the figure floats past the finished paragraph
                i = j + 1
                continue
        if out and b.strip() and _can_stitch(out[-1], b, cjk_ok=False):  # adjacent blocks: no CJK merging
            out[-1] = _join(out[-1], b)
            i += 1
            continue
        out.append(b)
        i += 1
    return "\n\n".join(out)


def _assemble_document(pages: Sequence[tuple[str | None, str]]) -> str:
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


def _default_ontology():
    """The 'default' document ontology, loaded from the ontology dir bundled inside the package (ships in
    the wheel, so this works for an installed library as well as a source checkout; cwd-independent)."""
    from .ontology import bundled_ontology_root, load_ontology
    return load_ontology("default", bundled_ontology_root())


def write_outputs(result: DocumentResult, out_dir: str | Path, *, pdf_path: str | None = None,
                  arithmetic: bool = True, inline_figures: bool = True, headings: bool = True,
                  describe_figure: "Callable[[bytes, str | None], str] | None" = None,
                  ontology: "Ontology | None" = None, chunk: bool = True) -> None:
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
    slide_images: dict[int, str] = {}   # slide-deck mode: one rendered page image per page
    onto = ontology or _default_ontology()   # injected document ontology (role/zone vocabulary + rules)
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
        # A slide deck (landscape pages) is a graphic layout: keep ONE rendered image per page for a
        # consistent visual, with the VLM's text transcription alongside for search. Clearing per-figure
        # crops also means no chart-internal-text suppression, so the slide's own text survives too.
        if pdf_path and result.pages:
            import pypdfium2 as _pdfium

            from .render import render_page_png
            _doc = _pdfium.PdfDocument(pdf_path)
            try:
                sizes = [_doc[pi].get_size() for pi in range(len(_doc))]
                if sizes and sum(1 for w, h in sizes if w > h) * 2 > len(sizes):   # majority landscape
                    (out / "assets").mkdir(exist_ok=True)
                    for pi in range(len(_doc)):
                        (out / "assets" / f"slide-{pi:03d}.png").write_bytes(render_page_png(pdf_path, pi, scale=2.0))
                        slide_images[pi] = f"assets/slide-{pi:03d}.png"
            finally:
                _doc.close()
        if slide_images:
            figures = []   # the page image carries every graphic -> skip crops, classification, suppression
        # drop hairline icons/logos, and display-equation strips ODL mis-detects as raster figures. The
        # equation case is gated on the page ACTUALLY containing display math (not height alone), so a
        # thin real figure on a non-math page is never dropped -- the VLM's LaTeX already carries the math.
        math_pages = {p.page_index for p in result.pages if _page_has_math(p.markdown)}
        figures = [f for f in figures
                   if not _tiny_figure(f.get("bbox"))
                   and not (_text_line_strip(f.get("bbox")) and (f.get("page") or 0) - 1 in math_pages)]
        _write_assets(out, figures, pdf_path)  # fills each figure["file"]
        _bind_vector_captions(figures, blocks)  # 図N label + caption text (both modes)
        if describe_figure is not None:  # VLM figure judgement (det_vlm): whether a crop is meaningful
            # CONTENT (chart/diagram/photo/table) or DECORATION (icon/logo/divider/background) is a
            # semantic call, not a size one -- two same-size crops can differ -- so let the VLM decide.
            # One call per crop returns 'DECORATION' (drop it) or a description (keep; used for a vector
            # chart, which has no raster to fall back on). _tiny_figure already removed hairline noise.
            kept: list[dict] = []
            for f in figures:
                if not f.get("file"):
                    kept.append(f)
                    continue
                try:
                    verdict = describe_figure((out / f["file"]).read_bytes(), f.get("caption")).strip()
                except Exception:  # noqa: BLE001 -- a failed call must not abort the run; keep the figure
                    verdict = ""
                if verdict.upper().startswith("DECORATION"):
                    continue                                  # ornamental crop -> drop, it carries no info
                if verdict:  # FR-3.2: keep the description for ANY content figure (raster too), not just vector;
                    f["description"] = verdict  # gated below (chart_data or page text layer), never ungated
                kept.append(f)
            figures = kept
        for f in figures:
            if f.get("file") and f.get("bbox"):  # only figures with a real crop can be inlined
                figs_by_page.setdefault(f["page"] - 1, []).append(f)
        blocks_by_page = {pg.page_index: pg.paragraphs for pg in result.structure.pages}
        chart_noise = _chart_internal_noise(figures, blocks_by_page)  # drop from prose + attach as chart_data
        page_numbers = None
        if pdf_path:  # born-digital text-layer numbers to gate raster descriptions that have no chart_data
            from .deterministic import number_tokens
            desc_pages = {f["page"] - 1 for f in figures if f.get("description") and not f.get("chart_data")}
            page_numbers = {pi: [t.value for t in number_tokens(pdf_path, pi, min_value=1000)] for pi in desc_pages}
        _gate_figure_descriptions(figures, page_numbers)  # FR-3.2: oracle-gate descriptions (chart_data / text layer)
        _mark_chart_label_blocks(figures, blocks)  # flag the same labels in the JSON graph (filterable)
        _resolve_cross_references(blocks, tables, figures)  # in-text 表N/図N mentions -> refs edges
        from .ontology import compute_font_ranks, tag_nodes
        font_ranks = compute_font_ranks(blocks)
        npages = result.meta.n_pages
        tag_nodes(blocks, tables, figures, onto, font_ranks, is_landscape=bool(slide_images), n_pages=npages)  # role + zone
        if headings:  # R13 section hierarchy: cascade authority -> levels -> sections tree + md #
            page_labels = extract_printed_page_numbers(pdf_path, result.meta.n_pages) if pdf_path else {}
            authority = resolve_heading_authority(pdf_path, result.structure)
            level_map, style_levels = _assign_heading_levels(blocks, authority, printed_to_index(page_labels),
                                                             onto, font_ranks, npages)   # + unnumbered admission
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
        if p.page_index in slide_images:  # slide deck: the rendered page image heads the page, text follows
            markdown = f"![slide {p.page_index + 1}]({slide_images[p.page_index]})\n\n{markdown.lstrip()}"
        name = f"page-{p.page_index:03d}.md"
        md_by_index[p.page_index] = markdown
        record["markdown_file"] = f"pages/{name}"
        results.append(record)
        rendered.append((p.page_index, name))

    if headings:  # document-level: drop running headers + printed-page-number leaks (page furniture)
        # ODL already filters running headers/footers -> a VLM line matching no ODL block is furniture.
        odl_norms_by_page = {pi: [norm_block(p.text) for p in paras] for pi, paras in blocks_by_page.items()}
        md_by_index = strip_page_furniture(md_by_index, page_labels, odl_norms_by_page)
    md_by_index = {pi: _escape_currency(_restore_panel_labels(_normalize_captions(md)))
                   for pi, md in md_by_index.items()}  # caption bold + (C) glyph + currency $ escape
    md_by_index = {pi: _label_figure_sources(md) for pi, md in md_by_index.items()}  # label figure DOIs

    for page_index, name in rendered:
        (pages_dir / name).write_text(md_by_index[page_index], encoding="utf-8")  # per-page keeps the split
    # document.md only: consolidate a cross-page marginal front-matter column (journal metadata sidebar)
    # so it stays contiguous instead of scattered through the body and split at the page break; the
    # per-page files above keep each page's own content. A no-op when no such column is detected.
    doc_md_by_index = consolidate_front_matter(md_by_index, blocks_by_page)
    pages_doc = [(page_labels.get(pi) or str(pi + 1), doc_md_by_index[pi]) for pi, _ in rendered]
    (out / "document.md").write_text(
        _stitch_broken_paragraphs(_consolidate_figure_units(
            _detach_image_from_trailing_text(_assemble_document(pages_doc)))), encoding="utf-8")
    _write_jsonl(out / "ledger.jsonl", result.ledger())
    _write_jsonl(out / "results.jsonl", results)

    if result.meta is not None:
        _write_document_json(out, result, pages_meta, blocks, tables, figures, sections, page_labels, onto)
        sem, provmap = _write_semantic_json(out, result, pages_meta, blocks, tables, figures, sections,
                                            onto, md_by_index)   # clean layered view (semantic + provenance)
        if chunk:            # R16: build-time small-to-big chunks (index children, return the section parent)
            _write_chunks(out, build_chunks(sem, provmap, sem["document_id"], onto.chunking))
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


def _text_line_strip(bbox) -> bool:
    """The SHAPE half of the display-equation test: a thin horizontal band only a text line or two tall
    (h < 40) and much wider than tall. This is a necessary but not sufficient signal -- the caller also
    requires the page to actually contain display math (``_page_has_math``) before dropping, so height is
    never the sole basis for removing a figure. Real content figures are far taller than this."""
    if not bbox:
        return False
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    return h < 40 and w > h * 3


def _page_has_math(markdown: str) -> bool:
    """The page's VLM transcription carries display math -- at least one display equation ($$...$$) or a
    dense run of inline math. On such a page a thin figure strip is a display-equation crop (redundant
    with the LaTeX); on a page with no math, the same-shaped strip is left alone."""
    if not markdown:
        return False
    inline = markdown.count("$") - 2 * markdown.count("$$")
    return markdown.count("$$") >= 2 or inline >= 8


def _bind_vector_captions(figures: list[dict], blocks: list[dict]) -> None:
    """Attach each vector figure's nearest 図N caption block (label + caption text) by bbox proximity."""
    caps_by_page: dict[int, list[dict]] = {}
    for b in blocks:
        if _FIG_CAPTION_RE.match(b.get("text", "")):
            caps_by_page.setdefault(b["page"], []).append(b)
    for f in figures:
        if f.get("source") != "vector" or not f.get("bbox"):
            continue
        fx0, _, fx1, fy1 = f["bbox"]
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
    -- legend, axis ticks, year labels. Two uses of the SAME collection: (1) returned as a per-page set
    of visual-only noise to DROP from prose (so a text/embedding model sees the figure's DESCRIPTION,
    not a scatter of disconnected numbers); (2) attached to the figure as ``chart_data`` (text + bbox)
    -- structured chart content for FR-5.5 and the value-oracle source for the description gate. Same
    tokens, no longer discarded."""
    out: dict[int, set[str]] = {}
    for f in figures:
        if f.get("source") != "vector" or not f.get("bbox"):
            continue
        pi = f["page"] - 1
        x0, y0, x1, y1 = f["bbox"]
        for p in blocks_by_page.get(pi, ()):
            cx, cy = (p.bbox[0] + p.bbox[2]) / 2, (p.bbox[1] + p.bbox[3]) / 2
            if x0 <= cx <= x1 and y0 <= cy <= y1 and not _KEEP_IN_FIG.match(p.text):
                norm = " ".join(p.text.split())
                out.setdefault(pi, set()).add(norm)
                f.setdefault("chart_data", []).append({"text": norm, "bbox": [float(v) for v in p.bbox]})
    return out


def _gate_figure_descriptions(figures: list[dict], page_numbers: "dict[int, list[str]] | None" = None) -> None:
    """Value-oracle the VLM figure description (FR-3.2 / §5-A): numbers in the prose that are absent
    from a deterministic source are fabrication-suspect and flagged onto ``description_flags`` -- never
    silently trusted. Source precedence: (1) the chart's OWN ``chart_data`` tokens (vector charts);
    (2) for a figure without chart_data (raster), the page's born-digital text-layer numbers
    (``page_numbers``) so raster descriptions are gated too. A figure with neither source is skipped
    (no deterministic source -> no gate, mirroring the transcription gate on scans)."""
    from .guards import extract_numbers
    from .oracle import fabrication_flags
    for f in figures:
        desc = f.get("description")
        if not desc:
            continue
        data = f.get("chart_data")
        if data:
            source = [n for tok in data for n in extract_numbers(tok["text"], min_value=1000)]
        elif page_numbers is not None:
            source = page_numbers.get(f["page"] - 1, [])
        else:
            continue
        flags = fabrication_flags(desc, source, min_value=1000)
        if flags:
            f["description_flags"] = [f"unsourced_number:{v}" for v in flags]


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


_SEMANTIC_CONTEXT = {"doco": "http://purl.org/spar/doco/", "deo": "http://purl.org/spar/deo/"}


def _zones_summary(blocks: list[dict], tables: list[dict], figures: list[dict]) -> list[dict]:
    """zone -> the pages it covers, ordered by first appearance (min page)."""
    zpages: dict[str, list[int]] = {}
    for n in (*blocks, *tables, *figures):
        z = n.get("zone")
        pg = n.get("page") or (n.get("pages") or [None])[0]
        if z and pg is not None and pg not in zpages.setdefault(z, []):
            zpages[z].append(pg)
    return [{"zone": z, "pages": sorted(p)} for z, p in sorted(zpages.items(), key=lambda kv: min(kv[1]))]


_DISPLAY_EQ = re.compile(r"\$\$(.+?)\$\$", re.S)   # a display equation in the VLM markdown
# a whole line that is a single $...$ (or $$...$$) math span -- a display equation the VLM wrapped in single $.
_STANDALONE_EQ = re.compile(r"^\s*\$\$?(?P<tex>.+?)\$\$?\s*$")
# math-display markers: a standalone $-line is a display equation only if it carries a relation/operator
# (or is long), so a lone inline symbol on its own line is not mistaken for one.
_MATHY = re.compile(r"=|\\leq|\\geq|\\neq|\\approx|\\sum|\\int|\\prod|\\frac|\\cdot|\\times|\\log")
# a bibliographic entry marker at the head of a reference: '[12]' / '12.' / '(12)' / '12)' / a circled digit.
# Numeric/circled markers are language-neutral, so the split works for EN/KR/JP reference lists alike.
_REF_MARKER = re.compile(r"^\s*(?:\[(\d+)\]|\((\d+)\)|(\d+)[.)]|([①-⑳]))\s+")


def _looks_like_display_latex(tex: str) -> bool:
    """A harvested standalone-$ line is a display equation only if it reads like one (a relation/operator,
    or a non-trivial length) -- keeps a lone '$x$' or '$\\theta$' line from becoming a spurious equation."""
    return bool(_MATHY.search(tex)) or len(tex) >= 15


def _display_equations_by_page(page_markdown: dict[int, str]) -> dict[int, list[str]]:
    """page_index -> [latex, ...] for the display equations in that page's VLM markdown: both ``$$...$$``
    blocks AND standalone lines that are a single ``$...$`` span (the VLM often wraps a display equation in
    single ``$``). The clean VLM LaTeX is harvested here so the equation is a first-class node even when the
    deterministic text layer only had glyph-garbled fragments of it."""
    out: dict[int, list[str]] = {}
    for pi, md in page_markdown.items():
        eqs = [m.group(1).strip() for m in _DISPLAY_EQ.finditer(md) if m.group(1).strip()]
        for line in md.splitlines():
            if "$$" in line:                                     # already captured by the block scan above
                continue
            m = _STANDALONE_EQ.match(line)
            if m:
                tex = m.group("tex").strip().rstrip(" .,;")
                if tex and _looks_like_display_latex(tex):
                    eqs.append(tex)
        if eqs:
            out[pi] = eqs
    return out


def _build_semantic(blocks: list[dict], tables: list[dict], figures: list[dict], sections: list[dict],
                    pages_content: list, meta: dict, ontology: "Ontology",
                    page_markdown: dict[int, str] | None = None) -> tuple[dict, dict]:
    """Pure builder: (semantic_doc, provenance) from the graph. The semantic view is agent-clean -- each
    node carries only id/type(role)/zone/level?/text|latex|label/... with NO geometry; bbox/order/font_size/
    regions go to the provenance map keyed by node id. Captions are promoted to first-class ``caption``
    nodes (``caption_of`` -> its figure/table, which gets a ``caption_ref``); display equations from the
    VLM markdown become ``equation`` nodes (``latex``), placed at page granularity.

    pages_content: list[(page_index, [node_id, ...])] in reading order per page.
    """
    prov: dict[object, dict] = {}

    def demote(nid: object, n: dict, keys: tuple) -> None:
        p = {k: n[k] for k in keys if n.get(k) is not None}
        if p:
            prov[nid] = {**prov.get(nid, {}), **p}

    sec_level = {s["block_id"]: s["level"] for s in sections}      # a heading node shows its section level
    nodes: list[dict] = []
    for b in blocks:
        demote(b["id"], b, ("page", "order", "bbox", "font_size"))
        node = {"id": b["id"], "type": b.get("role") or b.get("type"), "zone": b.get("zone"),
                "text": b.get("text", "")}
        if b["id"] in sec_level:
            node["level"] = sec_level[b["id"]]
        for k in ("refs", "section"):
            if b.get(k):
                node[k] = b[k]
        nodes.append(node)
    for t in tables:
        demote(t["id"], t, ("order",))
        if t.get("regions"):
            prov.setdefault(t["id"], {})["regions"] = t["regions"]
        node = {"id": t["id"], "type": t.get("role", "table"), "zone": t.get("zone"), "label": t.get("label"),
                "n_rows": t.get("n_rows"), "n_cols": t.get("n_cols"),
                "cells": [[{k: v for k, v in c.items() if k != "bbox"} for c in row] for row in t.get("cells", [])],
                "views": t.get("views")}
        for k in ("section", "refs"):
            if t.get(k):
                node[k] = t[k]
        nodes.append(node)
    # De-dup figure origins for the clean view: a VLM-reported figure (source=vlm, no raster) is dropped when
    # a raster figure (odl_image/vector) already carries the same label -- ODL didn't miss it, so the VLM node
    # is a same-page duplicate or a text-mention phantom. VLM figures with a UNIQUE label are kept (ODL genuinely
    # missed them). Layer 0 document.json keeps ALL origins (loss-aware); this is the clean projection.
    def _fig_source(f: dict) -> str:                              # unify the 3 figure origins into one source tag
        fid = str(f["id"])
        return f.get("source") or ("vlm" if "_vlm" in fid else "vector" if "_vec" in fid else "odl_image")
    raster_labels = {f.get("label") for f in figures if _fig_source(f) != "vlm" and f.get("label")}
    vlm_desc: dict = {}
    figures_kept: list = []
    for f in figures:
        if _fig_source(f) == "vlm" and f.get("label") in raster_labels:
            if f.get("description"):                              # keep the dropped VLM figure's description by
                vlm_desc.setdefault(f["label"], f["description"])  # grafting it onto the surviving raster figure
            continue
        figures_kept.append(f)
    for f in figures_kept:
        demote(f["id"], f, ("page", "order", "bbox"))
        source = _fig_source(f)
        node = {"id": f["id"], "type": f.get("role", "figure"), "zone": f.get("zone"), "label": f.get("label"),
                "kind": f.get("kind"), "source": source, "file": f.get("file")}
        desc = f.get("description") or (vlm_desc.get(f.get("label")) if source != "vlm" else None)
        if desc:
            node["description"] = desc
        if f.get("chart_data"):  # FR-5.5: structured chart content (axis/legend/value tokens + bbox)
            node["chart_data"] = f["chart_data"]
        if f.get("description_flags"):  # §5-A: numbers in the description absent from chart_data
            node["description_flags"] = f["description_flags"]
        for k in ("section", "refs"):
            if f.get(k):
                node[k] = f[k]
        nodes.append(node)

    # Caption promotion: a figure/table's caption becomes a `caption` node (re-typed existing caption block,
    # else synthesized); the figure/table references it via `caption_ref` (no duplicated caption text).
    node_by_id = {n["id"]: n for n in nodes}
    synth_caps: dict[object, str] = {}                            # host id -> synthesized caption node id
    for src in (*figures_kept, *tables):
        fid, cid, cap = src["id"], src.get("caption_id"), src.get("caption")
        host = node_by_id.get(fid)
        if cid and cid in node_by_id:                             # caption is already a block node -> re-type
            cnode = node_by_id[cid]
            cnode["type"] = "caption"
            cnode["caption_of"] = fid
            if host is not None:
                host["caption_ref"] = cid
        elif cap:                                                 # caption lived only as a field -> synthesize
            cnid = f"{fid}_cap"
            nodes.append({"id": cnid, "type": "caption", "zone": src.get("zone"), "caption_of": fid,
                          "label": src.get("label"), "text": cap})
            synth_caps[fid] = cnid
            if host is not None:
                host["caption_ref"] = cnid

    # References parsing: inside the references zone, each entry is one bibliographic reference -> re-type
    # it `reference`, lifting the leading marker ([12]/12./①) when present. Entries that begin '12.' are
    # tagged `heading` by the numbering rule, so headings are included here too; only the zone's own
    # section heading ('References'/'참고문헌') is spared. Numeric/circled markers -> language-neutral.
    section_block_ids = {s["block_id"] for s in sections}
    for n in nodes:
        if (n.get("zone") == "references" and n["id"] not in section_block_ids
                and n.get("type") in ("paragraph", "list_item", "heading")):
            n["type"] = "reference"
            m = _REF_MARKER.match(n.get("text", ""))
            if m:
                n["marker"] = next(g for g in m.groups() if g)

    # Equation promotion: extract display equations from the VLM markdown as `equation` nodes, woven into
    # the reading order at page granularity (per-node placement needs the Phase-3 prose bridge).
    from collections import Counter
    page_zone: dict[int, str] = {}
    for b in blocks:
        page_zone.setdefault(b.get("page"), []).append(b.get("zone"))  # type: ignore[arg-type]
    page_zone = {pg: (Counter(z for z in zs if z).most_common(1)[0][0] if any(zs) else ontology.default_zone)
                 for pg, zs in page_zone.items()}
    eqs_by_page = _display_equations_by_page(page_markdown) if page_markdown else {}
    eq_ids_by_page: dict[int, list[str]] = {}
    for pi, latexes in eqs_by_page.items():
        ids = []
        for k, latex in enumerate(latexes):
            nid = f"eq_p{pi + 1}_{k}"
            nodes.append({"id": nid, "type": "equation", "zone": page_zone.get(pi + 1, ontology.default_zone),
                          "display": True, "latex": latex})
            ids.append(nid)
        eq_ids_by_page[pi] = ids

    # Reading order references only ids that still exist in the nodes[] pool. It excludes `furniture`
    # (extraction noise / glyph-garbled math debris -- kept in the pool but out of the reading flow) AND ids
    # that were dropped from the pool (e.g. a de-duplicated VLM figure whose id is still in the raw page
    # content) so no dangling reference is emitted. A SYNTHESIZED caption (field-only) is woven in right
    # after its host figure/table so its text reaches the chunks.
    present_ids = {n["id"] for n in nodes}
    furniture_ids = {n["id"] for n in nodes if n.get("zone") == "furniture"}
    reading_order: list = []
    for pi, content in pages_content:
        for nid in content:
            if nid not in present_ids or nid in furniture_ids:
                continue
            reading_order.append(nid)
            cap = synth_caps.get(nid)
            if cap and cap not in furniture_ids:
                reading_order.append(cap)
        reading_order.extend(eq_ids_by_page.get(pi, []))

    sec_clean = [{"id": s["id"], "heading": s["heading"], "level": s["level"], "zone": s.get("zone"),
                  "heading_ref": s["block_id"], "parent": s["parent"], "children": s["children"],
                  "content": s["content"]} for s in sections]
    title = next((b.get("text") for b in blocks if b.get("role") == "title"), None) \
        or (meta.get("producer") or {}).get("title")
    doc = {
        "document_id": meta.get("document_id"), "content_sha256": meta.get("content_sha256"),
        "original_filename": meta.get("original_filename"), "source": meta.get("source"),
        "n_pages": meta.get("n_pages"), "mode": meta.get("mode"),
        "@context": _SEMANTIC_CONTEXT, "profile": ontology.profile_stamp(),
        "metadata": {"title": title},
        "zones": _zones_summary(blocks, tables, figures),
        "sections": sec_clean, "nodes": nodes, "reading_order": reading_order,
    }
    return doc, prov


def _write_semantic_json(out: Path, result: DocumentResult, pages_meta: dict[int, dict],
                         blocks: list[dict], tables: list[dict], figures: list[dict],
                         sections: list[dict], ontology: "Ontology",
                         page_markdown: dict[int, str] | None = None) -> tuple[dict, dict]:
    """Emit the agent-clean layered artifacts: document.semantic.json (no geometry) + a provenance sidecar;
    return the (semantic doc, provenance) so the chunker can consume them without a re-read."""
    pages_content = [(p.page_index, pages_meta.get(p.page_index, {}).get("content", []))
                     for p in result.pages if p.route != "folded"]
    doc, prov = _build_semantic(blocks, tables, figures, sections, pages_content, result.meta.to_dict(),
                                ontology, page_markdown)
    # Producer-backed seam (§5): serialize the Layer-2 artifacts THROUGH the export contracts, so the
    # bytes on disk are SemanticView/Provenance.to_dict() output (the contract is the schema authority).
    (out / "document.semantic.json").write_text(
        json.dumps(SemanticView.from_dict(doc).to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "document.provenance.json").write_text(
        json.dumps(Provenance(prov=prov, profile=ontology.profile_stamp()).to_dict(),
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return doc, prov      # return the RAW builder output so the chunker consumes it without a re-parse


# --------------------------------------------------------------------------------------------------
# Built-in chunking (R16, Phase 3): small-to-big, structure-first
# --------------------------------------------------------------------------------------------------
_CJK_TOK = re.compile(r"[぀-ヿ㐀-鿿가-힣]")   # CJK: ~1 token per char
_EQ_PAGE = re.compile(r"eq_p(\d+)_")
_SENTENCE = re.compile(r"(?<=[.!?。！？])\s+")   # sentence boundary for splitting an oversized paragraph


def _approx_tokens(text: str) -> int:
    """A tokenizer-free size estimate for chunk boundaries: CJK chars count ~1 token each; other text
    ~1.3 tokens/word. The exact tokenizer name is stored on each chunk so a consumer can re-count."""
    cjk = len(_CJK_TOK.findall(text))
    words = len(_CJK_TOK.sub(" ", text).split())
    return int(cjk + round(words * 1.3))


def _chunk_node_text(n: dict) -> str:
    """The embeddable/display text for a node: equations render their LaTeX, atomics a labelled stub."""
    t = n.get("type")
    if t == "equation":
        return n.get("latex", "")
    if t == "table":
        return f"[{n.get('label') or 'Table'}]"
    if t == "figure":
        return f"[{n.get('label') or 'Figure'}] {n.get('caption') or n.get('description') or ''}".strip()
    return n.get("text", "")


def build_chunks(sem: dict, prov: dict, doc_id: str, policy: "ChunkPolicy") -> list[dict]:
    """Small-to-big chunks from the semantic view. A PARENT chunk = one section (its heading + own
    content) or, for section-less content, a page group. CHILD chunks token-pack the parent's prose on
    node boundaries (never mid-node); atomics (table/figure/equation) are kept whole as their own child.
    Children carry the heading breadcrumb (``embedding_text``) and prev/next links; index the children,
    return the parent. Pure: (semantic doc, provenance, doc id, policy) -> chunk list."""
    from collections import Counter

    nodes = {n["id"]: n for n in sem.get("nodes", [])}
    sections = sem.get("sections", [])
    sec_by_id = {s["id"]: s for s in sections}

    node_page: dict[object, int] = {}                        # node -> page (from provenance / synthesised id)
    for nid, p in prov.items():
        pg = p.get("page") or (p["regions"][0]["page"] if p.get("regions") else None)
        if pg is not None:
            node_page[nid] = pg
    for n in sem.get("nodes", []):
        nid = n["id"]
        if nid in node_page:
            continue
        m = _EQ_PAGE.match(str(nid))
        if m:
            node_page[nid] = int(m.group(1))
        elif n.get("caption_of") in node_page:
            node_page[nid] = node_page[n["caption_of"]]

    node_section: dict[object, object] = {}
    for s in sections:
        node_section[s["heading_ref"]] = s["id"]
        for nid in s.get("content", []):
            node_section[nid] = s["id"]

    def breadcrumb(sid: object) -> list:
        out, seen = [], set()
        while sid and sid not in seen:
            seen.add(sid)
            s = sec_by_id.get(sid)
            if not s:
                break
            out.append(s["heading"])
            sid = s.get("parent")
        return list(reversed(out))

    def span(ids: list) -> list:
        ps = [node_page[i] for i in ids if i in node_page]
        return [min(ps), max(ps)] if ps else [None, None]

    def disp(ids: list) -> str:
        return "\n".join(t for t in (_chunk_node_text(nodes[i]) for i in ids) if t)

    # partition reading order into parent units (consecutive same-section, or a page group of orphans)
    units: list[tuple] = []
    for nid in sem.get("reading_order", []):
        if nid not in nodes:
            continue
        sid = node_section.get(nid)
        key = ("sec", sid) if sid else ("page", node_page.get(nid))
        if not units or units[-1][0] != key:
            units.append((key, []))
        units[-1][1].append(nid)

    chunks: list[dict] = []
    child_order: list[str] = []
    keep_atomic = set(policy.keep_atomic)
    for seq, (key, ids) in enumerate(units, 1):
        sid = key[1] if key[0] == "sec" else None
        crumb = breadcrumb(sid) if sid else []
        zc = Counter(nodes[i].get("zone") for i in ids if nodes[i].get("zone"))
        zone = zc.most_common(1)[0][0] if zc else "body"
        pid = f"c{seq:04d}p"
        pdisp = disp(ids)
        parent = {"id": pid, "level": "parent", "doc_id": doc_id,
                  "structural_type": "section" if sid else "page", "zone": zone, "heading_path": crumb,
                  "display_text": pdisp, "source_refs": {"nodes": list(ids), "pages": span(ids)},
                  "token_count": _approx_tokens(pdisp), "tokenizer": policy.tokenizer, "children": []}
        chunks.append(parent)
        buf: list = []
        cnum = 0
        prev_was_text = False

        def emit(node_ids: list, ctype: str, text: str | None = None) -> None:
            nonlocal cnum, prev_was_text
            cnum += 1
            cid = f"c{seq:04d}_{cnum}"
            t = disp(node_ids) if text is None else text
            # source_refs.{nodes,pages} is the canonical Layer-0 back-reference (§6): for an atomic child
            # the single node id in nodes[] IS the table/figure/equation ref, so no per-type ref field.
            child = {"id": cid, "level": "child", "doc_id": doc_id, "parent_id": pid, "structural_type": ctype,
                     "zone": zone, "heading_path": crumb, "display_text": t,
                     "embedding_text": (" > ".join(crumb) + "\n" + t).strip() if crumb else t,
                     "node_types": [nodes[i]["type"] for i in node_ids],
                     "source_refs": {"nodes": list(node_ids), "pages": span(node_ids)},
                     "token_count": _approx_tokens(t), "tokenizer": policy.tokenizer,
                     "prev": None, "next": None, "is_continuation": ctype == "text" and prev_was_text,
                     "atomic": ctype in keep_atomic}
            chunks.append(child)
            parent["children"].append(cid)
            child_order.append(cid)
            prev_was_text = ctype == "text"

        def emit_oversized(nid: object) -> None:                 # one paragraph over budget -> sentence windows
            win: list[str] = []
            for s in _SENTENCE.split(_chunk_node_text(nodes[nid])):
                win.append(s)
                if _approx_tokens(" ".join(win)) >= policy.child_tokens:
                    emit([nid], "text", " ".join(win))
                    win = []
            if win:
                emit([nid], "text", " ".join(win))

        for i in ids:
            if nodes[i]["type"] in keep_atomic:
                if buf:
                    emit(buf, "text")
                    buf = []
                emit([i], nodes[i]["type"])
            elif not buf and _approx_tokens(_chunk_node_text(nodes[i])) >= policy.child_tokens:
                emit_oversized(i)                                # a single paragraph exceeds the budget alone
            else:
                buf.append(i)
                if _approx_tokens(disp(buf)) >= policy.child_tokens:
                    emit(buf, "text")
                    buf = []
        if buf:
            emit(buf, "text")

    by_id = {c["id"]: c for c in chunks}                     # link leaves in reading order (prev/next)
    for a, b in zip(child_order, child_order[1:]):
        by_id[a]["next"] = b
        by_id[b]["prev"] = a
    return chunks


def _write_chunks(out: Path, chunks: list[dict]) -> None:
    # Producer-backed seam (§5): the bytes written are ChunkRecord.to_dict() output, so the export
    # contract is the emission's schema authority (round-trip == schema-regression guard).
    with (out / "document.chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(ChunkRecord.from_dict(c).to_dict(), ensure_ascii=False) + "\n")


def _write_document_json(out: Path, result: DocumentResult, pages_meta: dict[int, dict],
                         blocks: list[dict], tables: list[dict], figures: list[dict],
                         sections: list[dict], page_labels: dict[int, str | None],
                         ontology: "Ontology | None" = None) -> None:
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
    # Layer 0 is the byte-compatible extraction graph: role/zone (Layer 1) and heading_level/odl_role
    # (transient admission signals) are NOT inlined on nodes -- they live in a non-destructive `roles`
    # overlay keyed by node id (integration-plan §3-①). Serialize stripped COPIES so the shared node
    # dicts (also consumed by the semantic view / chunker) are not mutated.
    def _l0(n: dict) -> dict:
        return {k: v for k, v in n.items() if k not in ("role", "zone", "heading_level", "odl_role")}
    doc["sections"] = [_l0(s) for s in sections]
    doc["blocks"] = [_l0(b) for b in blocks]
    doc["tables"] = [_l0(t) for t in tables]
    doc["figures"] = [_l0(f) for f in figures]
    if ontology is not None:   # additive top-level: injected ontology + Layer-1 role overlay + zone summary
        doc["@context"] = _SEMANTIC_CONTEXT
        doc["ontology"] = ontology.profile_stamp()
        doc["roles"] = {n["id"]: {"role": n["role"], "confidence": 1.0, "by": "ontology"}
                        for n in (*blocks, *tables, *figures) if n.get("role")}
        doc["zones"] = _zones_summary(blocks, tables, figures)
    (out / "document.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    if ontology is not None:
        # Producer-backed seam (§5): a typed, contract-tagged structure view of the (loss-aware) document.json,
        # giving StructureExport a live producer. Lossy-by-design -- keys outside the dataclasses are dropped
        # here but preserved in document.json (the source of truth). from_dict consumes the flat doc directly.
        (out / "document.structure.json").write_text(
            json.dumps(StructureExport.from_dict(doc).to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


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
