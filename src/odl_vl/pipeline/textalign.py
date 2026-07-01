"""VLM<->ODL block alignment (shared primitive).

The VLM transcribes a rendered page in VISUAL order and in its own wording/formatting; ODL carries the
document's true structure (reading-order ``order``, filtered-out furniture, bound captions) but lossy
text. To let ODL structure drive the output while the VLM supplies clean text, each VLM block must be
MATCHED to its ODL block. Matching is one-to-one by longest common prefix with consumption, so sibling
blocks that share an opening ("which defines the ...") align to DISTINCT ODL blocks instead of all
colliding on the first.

Used by: the reading-order reorder (assemble.py, permute VLM blocks into ODL order), furniture-by-ODL-
absence (sections.py, a VLM line matching NO ODL block is a header/footer ODL already filtered), and
figure units (output.py, match a VLM caption line to its bound ODL caption).
"""
from __future__ import annotations

import re
from typing import NamedTuple


def norm_block(text: str) -> str:
    """Markdown-stripped, collapsed, lowercased form for aligning a VLM block to an ODL block."""
    text = re.sub(r"^[#>*\s]+", "", text)       # leading heading/quote/list markers
    text = re.sub(r"[*_`#>]", "", text)          # inline emphasis / heading marks
    return " ".join(text.split()).lower()


def common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


class Match(NamedTuple):
    idx: int            # position of the VLM block in its page
    text: str           # the raw VLM block
    norm: str           # normalized form (norm_block)
    order: int | None   # matched ODL reading-order index, or None if unmatched
    lcp: int            # longest-common-prefix length of the winning candidate (0 if none)


def align_vlm_to_odl(blocks: list[str], odl_items: list[tuple[int, str]], *,
                     min_lcp: int = 10, min_len: int = 8) -> list[Match]:
    """Align each VLM block to at most one ODL block. ``odl_items`` are ``(order, norm_text)`` pairs.
    One-to-one: an ODL block, once matched, is consumed so a later VLM block cannot re-take it. A block
    whose best longest-common-prefix is below ``min_lcp`` (equations the VLM renders as LaTeX, ODL-garbled
    or ODL-absent text such as a running header) is left unmatched (``order=None``)."""
    consumed: set[int] = set()
    out: list[Match] = []
    for i, b in enumerate(blocks):
        bn = norm_block(b)
        best_order, best_lcp = None, 0
        for order, on in odl_items:                # longest-common-prefix match among UNCONSUMED ODL blocks
            if order in consumed or len(on) < min_len:
                continue
            lcp = common_prefix_len(bn, on)
            if lcp > best_lcp:
                best_lcp, best_order = lcp, order
        if best_order is not None and best_lcp >= min_lcp:
            consumed.add(best_order)
            out.append(Match(i, b, bn, best_order, best_lcp))
        else:
            out.append(Match(i, b, bn, None, best_lcp))
    return out
