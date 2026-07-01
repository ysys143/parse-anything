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


def level_for(sig: NumberClass, stack: list[dict]) -> int:
    """Document-relative level of a heading by its signature, given the open-ancestor ``stack`` (frames
    ``{style, level, tier, dec_depth}``). Only chapter (resets), section (nests under the nearest
    chapter) and decimal DEPTH (monotone) are fixed anchors; every other style nests one below the
    current top the first time it appears -- which LEARNS the per-document enumerator order. Mutates
    ``stack`` (pops closed ancestors); the caller pushes the new frame."""
    if sig.tier == 0:                       # chapter: resets the whole hierarchy
        stack.clear()
        return 1
    if sig.tier == 1:                       # section: nests under the nearest chapter
        while stack and stack[-1]["tier"] != 0:
            stack.pop()
        return (stack[-1]["level"] + 1) if stack else 1
    if sig.dec_depth is not None:           # decimal: exactly one below the open decimal:(d-1), gapless
        for i in range(len(stack) - 1, -1, -1):
            if stack[i]["dec_depth"] == sig.dec_depth - 1:
                del stack[i + 1:]
                return stack[i]["level"] + 1
    for i in range(len(stack) - 1, -1, -1):  # sibling: same style still open -> reuse its level
        if stack[i]["style"] == sig.style:
            lvl = stack[i]["level"]
            del stack[i:]
            return lvl
    return (stack[-1]["level"] + 1) if stack else 1   # new style -> one deeper (defines its order)


def infer_text_levels(texts: list[str]) -> list[int | None]:
    """Document-relative levels for a bare sequence of heading texts (e.g. a TOC). ``None`` where a
    text has no recognized numbering. Same nesting stack as the body inference."""
    stack: list[dict] = []
    out: list[int | None] = []
    for t in texts:
        sig = classify_numbering(t)
        if sig is None:
            out.append(None)
            continue
        lvl = level_for(sig, stack)
        out.append(lvl)
        stack.append({"style": sig.style, "level": lvl, "tier": sig.tier, "dec_depth": sig.dec_depth})
    return out
