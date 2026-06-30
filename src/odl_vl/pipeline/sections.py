"""Section hierarchy (장/절/항) + markdown heading levels (R13).

Heading levels come from the cascade authority (PDF outline / printed TOC) when present, else from
the document-invariant numbering-prefix class (``numbering.classify_numbering``). A block becomes a
heading only when it carries a recognized numbering prefix (or an authority match) AND survives a
conservative list-vs-heading guard; everything else ABSTAINS (stays a plain paragraph, no ``#``).
Abstention is a safe default -- never fabricate a tree from a signal that does not generalize.
"""
from __future__ import annotations

import difflib
import re

from .numbering import classify_numbering
from .outline import HeadingAuthority

_TERMINATORS = "。．.!?！？"          # a numbered line ending here is a sentence (body), not a heading
_CAPTION_LEAD = re.compile(r"(?i)^\s*(?:table|figure|fig\.?|表|図|그림|표)\s*\d")
_NUM_PREFIX = re.compile(r"^\s*(?:第\s*[0-9０-９一二三四五六七八九十百]+\s*[章節編部篇]|제\s*\d+\s*[장절항편부]"
                         r"|[（(]\s*[0-9０-９a-zA-Z]+\s*[）)]|[0-9０-９]+(?:[.．][0-9０-９]+)*[.．]?"
                         r"|[Ⅰ-ⅫⅠ-Ⅻ①-⑳]|chapter\s+\w+|section\s+\d+|part\s+\w+)\s*", re.IGNORECASE)


def _normalize(text: str) -> str:
    """Strip the numbering prefix + leaders, collapse whitespace, lower -- for authority matching."""
    t = _NUM_PREFIX.sub("", text.strip(), count=1)
    t = re.sub(r"[·.…‧・\s]+", " ", t).strip().lower()
    return t


def _is_list_not_heading(text: str, kind: str) -> bool:
    """Conservative guard: a numbered line that is really an enumerated body item, not a heading."""
    t = text.rstrip()
    ends_sentence = t[-1:] in _TERMINATORS
    if kind == "list item" and (ends_sentence or len(t) > 60):
        return True
    return len(t) > 120 and ends_sentence


def _authority_level(text: str, page: int, authority: HeadingAuthority, printed_to_pdf: dict[str, int]) -> int | None:
    """Match a body heading to an authority entry (resolved to its PDF page) by normalized title."""
    norm = _normalize(text)
    if not norm:
        return None
    best_ratio, best_level = 0.0, None
    for e in authority.entries:
        # resolve the entry's PDF page: outline gives page_index; printed-TOC resolves printed_page
        epage = e.page_index
        if epage is None and e.printed_page is not None:
            epage = printed_to_pdf.get(e.printed_page)
        if epage is not None and abs(epage - (page - 1)) > 1:  # constrain to the entry's own page (+-1)
            continue
        en = _normalize(e.title)
        if not en:
            continue
        if en == norm:
            return e.level
        r = difflib.SequenceMatcher(None, en, norm).ratio()
        if r > best_ratio:
            best_ratio, best_level = r, e.level
    return best_level if best_ratio >= 0.8 else None


def heading_levels(blocks: list[dict], authority: HeadingAuthority | None = None,
                   printed_to_pdf: dict[str, int] | None = None) -> dict[object, int]:
    """block id -> heading level (1-based). Only numbered/authority-matched headings; others abstain."""
    printed_to_pdf = printed_to_pdf or {}
    cand: dict[object, int] = {}
    for b in blocks:
        text = b.get("text", "")
        nc = classify_numbering(text)
        if nc is None:  # no recognized numbering prefix -> abstain (table titles / unnumbered headings)
            continue
        if _is_list_not_heading(text, b.get("type", "")):
            continue
        if _CAPTION_LEAD.match(text):  # "Table 1 ..." / "図3 ..." is a caption label, not a section
            continue
        level = _authority_level(text, b["page"], authority, printed_to_pdf) if authority is not None else None
        cand[b["id"]] = level if level is not None else nc.rank

    # Demote ENUMERATED LISTS: item-level (deepest) candidates that run back-to-back with no body
    # between them (①②③ conditions) are a list, not sections. Restricted to item level -- adjacent
    # chapter/section/subsection markers (e.g. a 節 title then its first （１）) are legitimate structure.
    out = dict(cand)
    ordered = sorted(blocks, key=lambda b: (b.get("page", 0), b.get("order", 0)))
    prev_id, prev_pos = None, -1
    for pos, b in enumerate(ordered):
        if b["id"] not in cand:
            continue
        if prev_id is not None and cand[b["id"]] == cand[prev_id] >= 4 \
                and not any(x["id"] not in cand for x in ordered[prev_pos + 1:pos]):
            out.pop(b["id"], None)
            out.pop(prev_id, None)
        prev_id, prev_pos = b["id"], pos
    return out


def build_sections(blocks: list[dict], tables: list[dict], figures: list[dict],
                   level_map: dict[object, int]) -> tuple[list[dict], dict[object, object]]:
    """Nest nodes under headings into a sections[] tree by global reading order; return
    (sections, section_by_node_id). Non-heading nodes attach to the current open section."""
    nodes = sorted([*blocks, *tables, *figures], key=lambda n: (n.get("page", 0), n.get("order", 0)))
    sections: list[dict] = []
    by_id: dict[object, dict] = {}
    section_by_node: dict[object, object] = {}
    stack: list[dict] = []  # open sections, deepening by level
    seq = 0
    for n in nodes:
        nid = n["id"]
        lvl = level_map.get(nid) if n.get("type") not in ("table", "figure") else None
        if lvl is not None:  # this block opens a section
            while stack and stack[-1]["level"] >= lvl:
                stack.pop()
            seq += 1
            sec = {"id": f"sec{seq}", "heading": n.get("text", ""), "level": lvl, "block_id": nid,
                   "page": n.get("page"), "parent": stack[-1]["id"] if stack else None,
                   "children": [], "content": []}
            if stack:
                stack[-1]["children"].append(sec["id"])
            sections.append(sec)
            by_id[sec["id"]] = sec
            section_by_node[nid] = sec["id"]
            stack.append(sec)
        elif stack:  # body node -> current open section
            stack[-1]["content"].append(nid)
            section_by_node[nid] = stack[-1]["id"]
    return sections, section_by_node


def apply_heading_levels(markdown: str, page_headings: list[tuple[str, int]] | None = None, *,
                         max_level: int = 6, seen: set[str] | None = None) -> str:
    """Set ``#``*level on heading lines detected DIRECTLY in the markdown (the rendered view), so a
    running-header chapter/section line (``第1章 …``) is leveled even when the structure layer's ODL
    block text differs from the VLM's. A line's level is its section level from ``page_headings`` when
    matched, else its own numbering-class rank. Table/figure captions the VLM marked as headings are
    de-headed (a caption never outranks a chapter); enumerated ①②③ item runs with no body between
    are left as plain list items, not headings. Pass a persistent ``seen`` set across pages to
    de-head a chapter/section title that repeats verbatim (a running header) after its first use --
    subsection titles (現状/強み) legitimately recur per section, so only ranks 1-2 are deduped.
    Line count is unchanged."""
    level_of = {_normalize(t): lvl for t, lvl in (page_headings or [])}
    lines = markdown.split("\n")
    cand: list[tuple[int, int, str]] = []  # (line index, numbering rank, body text)
    for i, ln in enumerate(lines):
        is_hash = ln.lstrip().startswith("#")
        body = ln.lstrip("#").lstrip() if is_hash else ln.strip()
        if not body:
            continue
        if _CAPTION_LEAD.match(body):           # table/figure caption -> never a section heading
            if is_hash:
                lines[i] = body                 # strip the VLM's #
            continue
        nc = classify_numbering(body)
        if nc is None or body.rstrip()[-1:] in _TERMINATORS or len(body) > 120:  # not a heading line
            continue
        cand.append((i, nc.rank, body))

    cand_idx = {c[0] for c in cand}             # demote enumerated item runs (rank>=4, no body between)
    demote: set[int] = set()
    for (i0, r0, _), (i1, r1, _) in zip(cand, cand[1:]):
        if r1 == r0 >= 4 and not any(lines[k].strip() and k not in cand_idx for k in range(i0 + 1, i1)):
            demote |= {i0, i1}

    for i, rank, body in cand:
        norm = _normalize(body)
        repeated = seen is not None and rank <= 2 and norm in seen   # a running-header repeat
        if i in demote or repeated:
            lines[i] = body                     # de-head: enumerated item, or repeated running header
            continue
        if seen is not None and rank <= 2:
            seen.add(norm)
        lines[i] = "#" * min(level_of.get(norm, rank), max_level) + " " + body
    return "\n".join(lines)
