"""Cross-language heading numbering classifier (R13).

The ONE document-invariant heading signal is the numbering-prefix CLASS. Font size, indentation,
and ODL's ``heading_level`` all flip between documents (measured: mono white-paper headings are
SMALLER than body; a "section" is heading_level 2 in one doc, 3 in another) -- but the ordering
chapter > section > subsection > item is a property of the numbering SYSTEM, shared across CJK
government style, legal drafting, and Western academic conventions. ``classify_numbering`` returns
a rank (1 = top) for a recognized prefix, or ``None`` to ABSTAIN. Abstention is a safe default,
never a guess -- a paragraph with no recognized prefix simply stays a paragraph.

This is intentionally separate from ``reflow.py``'s ``_STARTS_UNIT``/``_HEADING_LIKE`` (which only
guard line-folding); the contracts differ, so the regexes are not shared.
"""
from __future__ import annotations

import re
from typing import NamedTuple


class NumberClass(NamedTuple):
    rank: int   # 1 = chapter (top); larger = deeper
    name: str


_UPPER_ROMAN = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ"
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_FW = str.maketrans("０１２３４５６７８９", "0123456789")  # fullwidth -> ascii digits

# rank 1 -- chapter / 장 / 編 / 部
_CHAPTER = re.compile(
    r"^(?:"
    r"第\s*[0-9０-９一二三四五六七八九十百]+\s*[章編部篇]"      # 第N章/編/部 (ja/zh)
    r"|제\s*[0-9]+\s*[장편부]"                                 # 제N장/편/부 (ko)
    r"|(?:chapter|part)\s+[0-9ivxlc]+\b"                        # Chapter N / Part N (en)
    rf"|[{_UPPER_ROMAN}]+\s*[.．、]"                            # Ⅰ. uppercase Roman = top level
    r")", re.IGNORECASE)

# rank 2 -- section / 절
_SECTION = re.compile(
    r"^(?:"
    r"第\s*[0-9０-９一二三四五六七八九十]+\s*節"               # 第N節
    r"|제\s*[0-9]+\s*절"                                       # 제N절
    r"|section\s+[0-9]+\b"                                      # Section N
    r")", re.IGNORECASE)

# rank 3 -- subsection / 항
_SUB = re.compile(
    r"^(?:"
    r"[（(]\s*[0-9０-９]+\s*[）)]"                              # （N） / (N)
    r"|제\s*[0-9]+\s*항"                                       # 제N항
    r")")

# rank 4 -- item / 목
_ITEM = re.compile(rf"^(?:[{_CIRCLED}]|[（(][a-zA-Z][）)])")    # ① / (a)

# bare decimal label: depth = dot count + 1 (1 -> section, 2 -> subsection, 3+ -> item).
# The char after the number must NOT be another digit -- "6 セメント" is a heading, "1960 1975 …"
# (a chart axis / year sequence) is not.
_DECIMAL = re.compile(r"^([0-9０-９]+(?:[.．][0-9０-９]+)*)[.．]?\s+(?![0-9０-９])\S")


def classify_numbering(text: str) -> NumberClass | None:
    """Rank a heading by its leading numbering prefix; ``None`` = no recognized prefix (abstain)."""
    if not text:
        return None
    t = text.lstrip()
    if _CHAPTER.match(t):
        return NumberClass(1, "chapter")
    if _SECTION.match(t):
        return NumberClass(2, "section")
    if _SUB.match(t):
        return NumberClass(3, "subsection")
    m = _DECIMAL.match(t)
    if m:
        depth = m.group(1).translate(_FW).count(".") + 1
        return NumberClass(min(depth + 1, 4), ("section", "subsection")[depth - 1] if depth <= 2 else "item")
    if _ITEM.match(t):
        return NumberClass(4, "item")
    return None
