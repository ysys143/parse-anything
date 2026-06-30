"""R12 graph serialization.

Turns the ODL structure into an id-keyed **property graph**: a single reading-order ``content``
stream per page (blocks + tables + figures interleaved, by ODL DFS order) plus global registries
``blocks``/``tables``/``figures`` whose nodes are keyed by the stable ODL element id and carry
``page`` (and ``caption_id``) back-references. This makes the JSON map straight to nodes+edges and
answers bidirectional queries -- page->content, table->pages->co-located text, figure(caption)->
page->body, plus the global table/figure lists. A page-spanning table is ONE node with ``pages:[…]``
that appears in each spanned page's content stream (at that segment's reading-order position).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .arithmetic import check_table_arithmetic as _check_arithmetic
from .odl_extract import OdlDocument, OdlParagraph, OdlTable, substantial_tables
from .reflow import _is_cjk, _starts_unit

_BODY_KINDS = frozenset({"paragraph", "text block"})
# A block ending in one of these is a complete unit; ending elsewhere means the next block continues it.
_TERMINATORS = "。．.!?！？:：；;)）」』】》〉…"


def _continues(prev: OdlParagraph, p: OdlParagraph) -> bool:
    """Is ``p`` the tail end of ``prev`` -- one paragraph ODL split at a column/line wrap? Text alone
    can't tell a wrap-split from two distinct unpunctuated labels (both lack a terminator), so we also
    require GEOMETRY: same column (x-overlap) and ``p`` sitting directly below ``prev`` within one
    line of spacing. The gap bound is font-relative (a typographic constant), not tuned to a layout."""
    if prev.kind not in _BODY_KINDS or p.kind not in _BODY_KINDS:
        return False
    if _starts_unit(prev.text) or _starts_unit(p.text):       # heading/list/label on either side
        return False
    tail = prev.text.rstrip()[-1:]
    if not tail or tail in _TERMINATORS:                       # prev is already a complete sentence
        return False
    if min(prev.bbox[2], p.bbox[2]) - max(prev.bbox[0], p.bbox[0]) <= 0:  # different columns
        return False
    line_h = (prev.font_size or (prev.bbox[3] - prev.bbox[1])) * 1.6
    gap = prev.bbox[1] - p.bbox[3]                              # prev bottom - next top (origin bottom-left)
    return -2.0 <= gap <= line_h                               # next sits just below prev


def _merge_blocks(paragraphs: tuple[OdlParagraph, ...]) -> list[OdlParagraph]:
    """Stitch ODL column/line-wrap paragraph splits back together (see ``_continues``). Reuses
    reflow's language-agnostic structural detection + a font-relative geometric gap -- no
    document-specific pattern -- and is cross-validated to not over-merge distinct labels/headings."""
    out: list[OdlParagraph] = []
    for p in paragraphs:
        if out and _continues(out[-1], p):
            prev = out[-1]
            sep = "" if (_is_cjk(prev.text[-1]) or _is_cjk(p.text[:1])) else " "
            bbox = (min(prev.bbox[0], p.bbox[0]), min(prev.bbox[1], p.bbox[1]),
                    max(prev.bbox[2], p.bbox[2]), max(prev.bbox[3], p.bbox[3]))
            out[-1] = replace(prev, text=prev.text + sep + p.text, bbox=bbox)
        else:
            out.append(p)
    return out


def _is_continuation(t: OdlTable, by_id: dict) -> bool:
    """True only when ``previous_table_id`` links ACROSS a page break. ODL's "previous table id"
    is a generic reading-order pointer: a form with several distinct tables on ONE page links them
    1->2->3 though they are NOT one table. A real spanning continuation is always on a later page."""
    prev = by_id.get(t.previous_table_id) if t.previous_table_id is not None else None
    return prev is not None and t.page_index != prev.page_index


def table_chains(tables: list[OdlTable]) -> list[list[OdlTable]]:
    """Group OdlTables into page-spanning chains via ODL ``previous_table_id`` -> ``table_id``,
    counting a link only when it crosses a page break (see ``_is_continuation``)."""
    by_id = {t.table_id: t for t in tables if t.table_id is not None}
    next_of = {t.previous_table_id: t for t in tables if _is_continuation(t, by_id)}
    is_continuation = {t.table_id for t in tables if _is_continuation(t, by_id)}
    chains: list[list[OdlTable]] = []
    for t in tables:
        if t.table_id in is_continuation:
            continue
        chain = [t]
        cur = t
        while cur.table_id is not None and cur.table_id in next_of:
            cur = next_of[cur.table_id]
            chain.append(cur)
        chains.append(chain)
    return chains


def _rich_cells(cells: tuple, boxes: tuple, spans: tuple) -> list[list[dict]]:
    """Row-major cells as {text, bbox, [row_span, col_span]} -- spans only emitted when > 1."""
    out: list[list[dict]] = []
    for i, row in enumerate(cells):
        rr: list[dict] = []
        for j, text in enumerate(row):
            box = boxes[i][j] if i < len(boxes) and j < len(boxes[i]) else None
            span = spans[i][j] if i < len(spans) and j < len(spans[i]) else None
            cell: dict = {"text": text, "bbox": list(box) if box else None}
            if span and (span[0] != 1 or span[1] != 1):
                cell["row_span"], cell["col_span"] = span[0], span[1]
            rr.append(cell)
        out.append(rr)
    return out


def build_graph(structure: OdlDocument, labels_by_page: dict[int, tuple[dict, ...]], *, arithmetic: bool = True):
    """Build the graph: returns (pages_meta, blocks, tables, figures).

    pages_meta: {page_index: {content:[id...], blocks:[id...], tables:[id...], figures:[id...]}}.
    Each registry entry is a node keyed by ``id`` (ODL element id; synthetic for VLM-only figures).
    """
    pages: dict[int, dict] = defaultdict(lambda: {"content": [], "blocks": [], "tables": [], "figures": []})
    placement: dict[int, list[tuple[int, object]]] = defaultdict(list)  # page -> [(order, id)]
    blocks: list[dict] = []
    tables: list[dict] = []
    figures: list[dict] = []

    # ---- blocks (text chunks) ----
    # ODL element ids are unique only WITHIN a page (they collide across pages), so every graph
    # node id is namespaced by page -> "p{page}_{odl_id}", globally unique and stable.
    for page in structure.pages:
        pi = page.page_index
        for p in _merge_blocks(page.paragraphs):  # stitch ODL column-wrap paragraph splits
            bid: object = f"p{pi + 1}_{p.element_id}" if p.element_id is not None else f"p{pi + 1}_b{p.order}"
            node = {"id": bid, "type": p.kind, "page": pi + 1, "order": p.order,
                    "bbox": list(p.bbox), "text": p.text}
            if p.font_size:
                node["font_size"] = round(float(p.font_size), 2)
            blocks.append(node)
            pages[pi]["blocks"].append(bid)
            placement[pi].append((p.order, bid))

    # ---- tables (one node per page-spanning chain) ----
    all_tables = [t for page in structure.pages for t in substantial_tables(page)]
    for chain in table_chains(all_tables):
        head = chain[0]
        hp = head.page_index + 1
        tid: object = f"p{hp}_{head.table_id}" if head.table_id is not None else f"p{hp}_t{head.order}"
        source_pages: list[int] = []
        regions: list[dict] = []
        cells: list = []
        boxes: list = []
        spans: list = []
        for seg in chain:
            p1 = seg.page_index + 1
            if p1 not in source_pages:
                source_pages.append(p1)
            regions.append({"page": p1, "bbox": list(seg.bbox)})
            cells.extend(seg.cells)
            boxes.extend(seg.cell_boxes)
            spans.extend(seg.cell_spans)
            pages[seg.page_index]["tables"].append(tid)
            placement[seg.page_index].append((seg.order, tid))  # appears in each spanned page's stream
        label, caption = head.label, head.caption
        caption_id = f"p{hp}_{head.caption_id}" if head.caption_id is not None else None
        if label is None:  # ODL missed the caption -> backfill from a VLM-read one on the head page
            vlm_t = [lbl for lbl in labels_by_page.get(head.page_index, ()) if lbl["kind"] == "table"]
            if vlm_t:
                label, caption = vlm_t[0]["label"], vlm_t[0]["caption"]
        tables.append({
            "id": tid, "type": "table", "pages": source_pages, "order": head.order,
            "label": label, "caption": caption, "caption_id": caption_id,
            "n_rows": sum(t.n_rows for t in chain), "n_cols": head.n_cols,
            "cells": _rich_cells(tuple(cells), tuple(boxes), tuple(spans)),
            "regions": regions, "continued": len(chain) > 1,
            "arithmetic": _check_arithmetic(cells) if arithmetic else None,
        })

    # ---- figures ----
    vlm_seq = 0
    for page in structure.pages:
        pi = page.page_index
        vlm_figs = [lbl for lbl in labels_by_page.get(pi, ()) if lbl["kind"] == "figure"]
        for im in page.images:
            fid: object = f"p{pi + 1}_{im.element_id}" if im.element_id is not None else f"p{pi + 1}_f{im.order}"
            label, caption = im.label, im.caption
            if label is None and vlm_figs:
                v = vlm_figs.pop(0)
                label, caption = v["label"], v["caption"]
            figures.append({
                "id": fid, "type": "figure", "page": pi + 1, "order": im.order,
                "label": label, "caption": caption,
                "caption_id": f"p{pi + 1}_{im.caption_id}" if im.caption_id is not None else None,
                "bbox": list(im.bbox), "file": None, "kind": im.kind,
            })
            pages[pi]["figures"].append(fid)
            placement[pi].append((im.order, fid))
        for v in vlm_figs:  # VLM-detected figure ODL missed entirely (no bbox/order) -> synthetic id, tail
            vlm_seq += 1
            fid = f"p{pi + 1}_vlm{vlm_seq}"
            figures.append({
                "id": fid, "type": "figure", "page": pi + 1, "order": 10**9,
                "label": v["label"], "caption": v["caption"], "caption_id": None,
                "bbox": None, "file": None, "kind": "figure",
            })
            pages[pi]["figures"].append(fid)
            placement[pi].append((10**9, fid))

    # ---- per-page reading-order content stream ----
    for pi, items in placement.items():
        pages[pi]["content"] = [eid for _, eid in sorted(items, key=lambda x: x[0])]
    return dict(pages), blocks, tables, figures
