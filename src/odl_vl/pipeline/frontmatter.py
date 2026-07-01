"""Cross-page marginal-column (front-matter sidebar) consolidation.

Some layouts -- journal title pages especially -- place metadata (Citation, Copyright, Funding, Data
Availability, Abbreviations) in a NARROW column in the outer margin, running PARALLEL to and DISJOINT
from the body text column, and flowing ACROSS page boundaries. A page-by-page, VLM-visual-order assembly
scatters that column through the body and can split one of its paragraphs (a DOI URL) across the page
break. This module detects such a marginal column purely from ODL block GEOMETRY -- never content
strings, never the VLM -- collects it as one cross-page stream, stitches its wrapped paragraphs, and
emits it as a single contiguous block, so the metadata stays together instead of being separated.

The detection is deliberately conservative and fires only when a real marginal column exists: >=2 blocks
starting clearly left of the body column, the MAJORITY of them staying entirely left of it. A single-
column document, an isolated left-shifted block (a centered equation), or a wide block that merely opens
with a small negative indent (a figure caption) yields no marginal column and the whole pass is a no-op.
Nothing here is tuned to a journal: the body column edge is the document's own dominant left edge, and
"a column is >=2 stacked narrow blocks" is inherent to what a marginal column is -- not an overfit
constant. Column membership is STRUCTURE, so it is decided deterministically by geometry (run-invariant),
keeping the VLM confined to text quality.
"""
from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Protocol

from .textalign import align_vlm_to_odl, norm_block

_BODY_GAP = 10.0    # a block must start at least this far left of the body column to count as "marginal"
_MAX_WIDTH_RATIO = 0.6   # a marginal column wider than this fraction of the body column is a body column
_COVER_MIN = 0.6    # an unmatched in-between block joins the sidebar only if this fraction of its tokens
#                     appear in the sidebar's own (ODL) text -- so body prose between two sidebar fields
#                     is not swept along, while a field ODL merged into a neighbor (Academic Editor) is.
_MIN_UNMATCHED_TOKENS = 5   # ...and only if it is long enough for that coverage to be a real signal, so a
#                             short stop-word-heavy body line does not slip in on incidental overlap.

# Reused-here copies of the tiny URL predicates output.py uses to stitch a page-break-split URL. Kept
# local so this module has no import cycle with output.py.
_URL_END = re.compile(r"https?://\S+$")
_URL_CONT = re.compile(r"^[A-Za-z0-9]+[./]\S*")

# A structural block acts as a hard separator inside a page's block flow: a figure image/caption, a
# heading, a Source line, a table row, a blockquote, a page marker. The sidebar column never crosses one,
# so these bound the run of blocks that may belong to the front matter.
_STRUCT = re.compile(
    r"^(?:!\[|#{1,6}\s|Source:\s*https?://|\||>\s|<!--|"
    r"\*?\*?\s*(?:Fig(?:ure)?|Table|表|図|그림|圖)\.?\s*\d)",   # a figure/table caption, bold or plain
    re.IGNORECASE)


class _Para(Protocol):
    bbox: tuple[float, float, float, float]
    text: str
    order: int


def _body_left_edge(paras_by_page: dict[int, "tuple[_Para, ...]"]) -> float | None:
    """The document's dominant text left edge = the most common block x0 (rounded). Derived from the
    document itself, so no page-size or journal constant is baked in."""
    c: Counter[int] = Counter(round(p.bbox[0]) for paras in paras_by_page.values() for p in paras)
    return float(c.most_common(1)[0][0]) if c else None


def marginal_paragraphs(paras_by_page: dict[int, "tuple[_Para, ...]"], *,
                        min_col: int = 2) -> tuple[dict[int, list], float | None]:
    """{page_index: [paragraphs...]} (reading order) for pages carrying a marginal outer-margin column.

    A page qualifies when >=``min_col`` of its paragraphs START clearly left of the body column
    (``x0 < body - _BODY_GAP``) AND the MAJORITY of those stay entirely left of it (``x1 < body``) -- a
    narrow sidebar, not a wide body block (figure caption, centered equation) that merely begins with a
    small negative indent. Returns ({}, body) when there is no such column anywhere (the common case)."""
    body = _body_left_edge(paras_by_page)
    out: dict[int, list] = {}
    if body is None:
        return out, body
    for pi, paras in paras_by_page.items():
        left = [p for p in paras if p.bbox[0] < body - _BODY_GAP]
        if len(left) >= min_col and sum(1 for p in left if p.bbox[2] < body) * 2 >= len(left):
            out[pi] = sorted(left, key=lambda p: (p.order < 0, p.order))  # unassigned order (-1) sorts last
    if not out:
        return out, body
    # A sidebar is NARROW; a body text column is wide. If the detected column is about as wide as the body
    # column, it is a body column (e.g. the left column of a two-column body whose x0 the mode happened to
    # miss), not front matter -- refuse. Median widths shrug off a single polluted bbox.
    body_w = median([p.bbox[2] - p.bbox[0] for ps in paras_by_page.values()
                     for p in ps if round(p.bbox[0]) == round(body)] or [0.0])
    marg_w = median([p.bbox[2] - p.bbox[0] for ps in out.values() for p in ps])
    if body_w and marg_w >= body_w * _MAX_WIDTH_RATIO:
        return {}, body
    # A front-matter sidebar is LOCALIZED to the opening. A narrow column present on the MAJORITY of pages
    # is instead a recurring body furniture column (e.g. manuscript line numbers), not front matter.
    if len(out) > max(2, len(paras_by_page) // 2):
        return {}, body
    return out, body


def _belongs_to_sidebar(block: str, pool: set[str]) -> bool:
    """Whether an UNMATCHED in-between block is really part of the sidebar: enough of its tokens appear in
    the sidebar's own ODL vocabulary (``pool``), AND it is long enough for that fraction to be a real
    signal rather than incidental overlap of a short stop-word-heavy body line."""
    toks = norm_block(block).split()
    if len(toks) < _MIN_UNMATCHED_TOKENS:
        return False
    return sum(1 for t in toks if t in pool) / len(toks) >= _COVER_MIN


def _pull_indices(blocks: list[str], matched: set[int], pool: set[str]) -> list[int]:
    """Indices to relocate into the front matter. Structural blocks split the page into segments; within
    each segment the inclusive range from the FIRST to the LAST matched block is examined. A matched block
    is always pulled; an UNMATCHED block in that range is pulled only if its tokens are largely covered by
    the sidebar's own ODL text (``pool``) -- so a metadata field ODL merged into a neighbor (unmatched, but
    its words ARE in the sidebar text, e.g. 'Academic Editor') comes along, while a body paragraph the VLM
    happened to place between two sidebar fields (words NOT in the sidebar text) is left in the body."""
    struct = [i for i, b in enumerate(blocks) if _STRUCT.match(b.strip())]
    bounds = [-1, *struct, len(blocks)]
    pull: list[int] = []
    for a, b in zip(bounds, bounds[1:]):
        ms = [i for i in range(a + 1, b) if i in matched]
        if ms:
            pull.extend(i for i in range(ms[0], ms[-1] + 1)
                        if i in matched or _belongs_to_sidebar(blocks[i], pool))
    return pull


def _stitch_stream(items: list[str]) -> list[str]:
    """Rejoin ONLY a URL that was cut mid-token across the page break: the previous block ends in a URL
    whose last character is '.' or '/' (an incomplete host/path, e.g. '...(https://doi.') and the next
    opens as a bare path fragment ('org/...zenodo'). The halves rejoin with no space. This is deliberately
    narrow: distinct metadata fields are never merged, and a complete-looking URL ('.../repo') is not glued
    to whatever follows (which would corrupt both texts). Everything else stays a separate block."""
    out: list[str] = []
    for text in items:
        text = text.strip()
        if not text:
            continue
        if out:
            prev_tail = out[-1].rsplit("\n", 1)[-1].rstrip()
            head = text.lstrip()
            tok = head.split(" ", 1)[0]
            if (_URL_END.search(prev_tail) and prev_tail[-1:] in "./"
                    and _URL_CONT.match(tok) and ("/" in tok or "." in tok)):
                out[-1] = f"{out[-1].rstrip()}{head}"
                continue
        out.append(text)
    return out


def _insert_front_matter(md: str, block: str) -> str:
    """Place the consolidated front-matter block right before the first section heading that follows the
    document title (so it sits after the title/authors, before Abstract). Falls back to prepending when
    there is no title heading."""
    blocks = re.split(r"\n\n+", md.strip())
    if not blocks:
        return block
    title_i = next((i for i, b in enumerate(blocks) if b.lstrip().startswith("#")), None)
    if title_i is None:                       # no '#' title (VLM may render it bold/plain): place the block
        blocks.insert(1, block)               # AFTER the first block (the title candidate), never above it
        return "\n\n".join(blocks)
    insert_i = next((j for j in range(title_i + 1, len(blocks)) if blocks[j].lstrip().startswith("#")),
                    len(blocks))
    blocks.insert(insert_i, block)
    return "\n\n".join(blocks)


def consolidate_front_matter(md_by_index: dict[int, str],
                             paras_by_page: dict[int, "tuple[_Para, ...]"]) -> dict[int, str]:
    """Return a COPY of ``md_by_index`` with the marginal front-matter column consolidated for the
    assembled document. The scattered sidebar blocks are removed from every page's body flow, stitched
    into one cross-page stream, and inserted as a single contiguous block into the first page, before its
    first post-title heading. A no-op (returns an equal copy) when no marginal column is detected.

    ``md_by_index`` itself is left untouched, so the per-page files keep each page's own content; only
    the document.md assembly consumes the consolidated result."""
    result = dict(md_by_index)
    marginal, _ = marginal_paragraphs(paras_by_page)
    if not marginal:
        return result

    stream: list[str] = []                        # sidebar blocks in document reading order (page, idx)
    for pi in sorted(marginal):
        md = result.get(pi)
        if md is None:
            continue
        blocks = re.split(r"\n\n+", md.strip())
        odl_items = [(p.order, norm_block(p.text)) for p in marginal[pi] if p.order >= 0]
        matched = {m.idx for m in align_vlm_to_odl(blocks, odl_items) if m.order is not None}
        if not matched:
            continue
        pool = {t for p in marginal[pi] for t in norm_block(p.text).split()}  # the sidebar's own vocabulary
        pull = _pull_indices(blocks, matched, pool)
        if not pull:
            continue
        pulled = set(pull)
        stream.extend(blocks[i] for i in pull)   # pull preserves this page's block order
        result[pi] = "\n\n".join(b for i, b in enumerate(blocks) if i not in pulled)

    if not stream:
        return dict(md_by_index)                 # nothing actually relocated -> leave the document as-is
    block = "\n\n".join(_stitch_stream(stream))
    first = min(md_by_index)                      # the document's first page carries the title
    result[first] = _insert_front_matter(result[first], block)
    return result
