"""Cross-language heading numbering classifier (R13).

Identifies the numbering-prefix CLASS of a heading line. Font size and ODL ``heading_level`` flip
between documents (measured), so the class is the signal heading DETECTION leans on. But the LEVEL a
class sits at is NOT a global constant -- only chapter > section (linguistic) and decimal DEPTH
(dot count) are document-invariant; the relative order of enumerators (（N）, ①, 가., 1)) is a
per-document convention (white paper: （N）≻①; Korean law: ①≻가.≻(1) -- the reverse). So this
returns a STRUCTURED signature; the actual level is inferred document-relative in ``sections.py``.

Signature fields:
- ``rank`` (1..4) -- the legacy fixed rank. Kept ONLY for back-compat and as the run-demote predicate
  (rank>=4 = item-level enumerated lists); it is NO LONGER the emitted heading level.
- ``style`` -- a stable identity per marker type ("chapter"/"section"/"decimal:2"/"paren"/"num_paren"
  /"circled"/"hangul_letter"/"ko_article"/...), used for sibling detection + learning the order.
- ``tier`` -- the ONLY fixed anchors: 0 = chapter family, 1 = section family, 2 = everything else.
- ``dec_depth`` -- dot-count+1 for decimals (drives depth monotonicity), else None.

``None`` = no recognized prefix (abstain) -- a safe default, never a guess.
"""
from __future__ import annotations

import re
from typing import NamedTuple


class NumberClass(NamedTuple):
    rank: int                       # 1..4 legacy fixed rank -- back-compat + run-demote predicate only
    name: str                       # legacy name ("chapter"/"section"/"subsection"/"item")
    style: str = ""                 # marker identity for sibling detection + document-relative ordering
    tier: int = 2                   # 0 chapter, 1 section, 2 other (the only document-invariant anchors)
    dec_depth: int | None = None    # decimal dot-count+1, else None


_UPPER_ROMAN = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ"
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_HANGUL_ORD = "가나다라마바사아자차카타파하"   # Korean ordinal letters (precise -- not arbitrary 가-힣)
_FW = str.maketrans("０１２３４５６７８９", "0123456789")  # fullwidth -> ascii digits

# tier 0 -- chapter family (第N章/編/部, 제N장/편/부, Chapter/Part N, uppercase Roman Ⅰ.)
_CHAPTER = re.compile(
    r"^(?:"
    r"第\s*[0-9０-９一二三四五六七八九十百]+\s*[章編部篇]"
    r"|제\s*[0-9]+\s*[장편부]"
    r"|(?:chapter|part)\s+[0-9ivxlc]+\b"
    rf"|[{_UPPER_ROMAN}]+\s*[.．、]"
    r")", re.IGNORECASE)
# tier 1 -- section family (第N節, 제N절, Section N)
_SECTION = re.compile(r"^(?:第\s*[0-9０-９一二三四五六七八九十]+\s*節|제\s*[0-9]+\s*절|section\s+[0-9]+\b)", re.IGNORECASE)
# tier 2 -- enumerators, each a distinct style; order between them is learned per document
_KO_ARTICLE = re.compile(r"^제\s*[0-9]+\s*조")              # 제N조 (Korean legal article)
_KO_SUBDIV = re.compile(r"^제\s*[0-9]+\s*[항호관목]")        # 제N항/호/관/목
_PAREN = re.compile(r"^[（(]\s*[0-9０-９]+\s*[）)]")          # （N） / (N)
_NUM_PAREN = re.compile(r"^[0-9０-９]+\)")                   # 1) 2) -- the most common KR marker
_CIRCLED_RE = re.compile(rf"^[{_CIRCLED}]")                  # ①
_LATIN_PAREN = re.compile(r"^[（(][a-zA-Z][）)]")            # (a)
_HANGUL = re.compile(rf"^[{_HANGUL_ORD}][.)．]")             # 가. 나)
# bare decimal: depth = dot count + 1. The char after the number must NOT be another digit so a chart
# axis / year sequence ("1960 1975 …") is not a heading.
_DECIMAL = re.compile(r"^([0-9０-９]+(?:[.．][0-9０-９]+)*)[.．]?\s+(?![0-9０-９])\S")


def classify_numbering(text: str) -> NumberClass | None:
    """Rank+identify a heading by its leading numbering prefix; ``None`` = no recognized prefix."""
    if not text:
        return None
    t = text.lstrip()
    if _CHAPTER.match(t):
        return NumberClass(1, "chapter", "chapter", 0)
    if _SECTION.match(t):
        return NumberClass(2, "section", "section", 1)
    if _KO_ARTICLE.match(t):
        return NumberClass(2, "section", "ko_article", 2)
    if _PAREN.match(t):
        return NumberClass(3, "subsection", "paren", 2)
    if _KO_SUBDIV.match(t):
        return NumberClass(3, "subsection", "ko_subdiv", 2)
    m = _DECIMAL.match(t)
    if m:
        depth = m.group(1).translate(_FW).count(".") + 1
        name = ("section", "subsection")[depth - 1] if depth <= 2 else "item"
        return NumberClass(min(depth + 1, 4), name, f"decimal:{depth}", 2, depth)
    if _NUM_PAREN.match(t):
        return NumberClass(3, "subsection", "num_paren", 2)
    if _CIRCLED_RE.match(t):
        return NumberClass(4, "item", "circled", 2)
    if _LATIN_PAREN.match(t):
        return NumberClass(4, "item", "latin_paren", 2)
    if _HANGUL.match(t):
        return NumberClass(4, "item", "hangul_letter", 2)
    return None
