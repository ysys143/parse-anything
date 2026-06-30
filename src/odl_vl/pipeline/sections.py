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
from collections import Counter

from .numbering import NumberClass, classify_numbering, level_for
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


_CITE_RE = re.compile(r"https?://|www\.|doi\.org|\bdoi:\s|\bPMID\b", re.IGNORECASE)
_SENTENCE_BOUNDARY = re.compile(r"[.!?。][\s　]")


def _is_prose_not_heading(text: str) -> bool:
    """A NUMBERED line that is really citation/prose, not a heading: after stripping the numbering
    marker it carries a URL/DOI/PMID, or has >=2 internal sentence boundaries (a heading is one short
    phrase). Stops a reference entry ('13. Author A, Author B. Title. Journal. Year') or a citation
    fragment ('(1):2757. https://doi.org/...') and a volume:page tail ('(3):213-224.') from being
    leveled as a section. Document-agnostic."""
    rest = _NUM_PREFIX.sub("", text.strip(), count=1).lstrip()
    if not rest or rest[0] == ":":  # 'marker:digits' -> a volume:page citation, not a heading
        return True
    return bool(_CITE_RE.search(rest)) or len(_SENTENCE_BOUNDARY.findall(rest)) >= 2


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


def _assign_heading_levels(blocks: list[dict], authority: HeadingAuthority | None = None,
                           printed_to_pdf: dict[str, int] | None = None) -> tuple[dict[object, int], dict[str, int]]:
    """(block id -> level, style -> first level). Levels are DOCUMENT-RELATIVE: detection/abstain/
    run-demote are unchanged (they key on rank); a reading-order nesting stack owns the level."""
    printed_to_pdf = printed_to_pdf or {}
    cand: dict[object, NumberClass] = {}   # id -> NumberClass (survivors of abstain/list/caption)
    meta: dict[object, tuple] = {}         # id -> (text, page)
    for b in blocks:
        text = b.get("text", "")
        nc = classify_numbering(text)
        if nc is None or _is_list_not_heading(text, b.get("type", "")) or _is_prose_not_heading(text) \
                or _CAPTION_LEAD.match(text):
            continue
        cand[b["id"]] = nc
        meta[b["id"]] = (text, b.get("page"))

    ordered = sorted(blocks, key=lambda b: (b.get("page", 0), b.get("order", 0)))
    # Demote ENUMERATED LISTS (unchanged): item-level (rank>=4) candidates back-to-back with no body
    # between them are a list, not sections. Collect then remove (don't mutate cand mid-scan, else the
    # next iteration's cand[prev_id] / membership checks break). Done before inference.
    demoted: set[object] = set()
    prev_id, prev_pos = None, -1
    for pos, b in enumerate(ordered):
        if b["id"] not in cand:
            continue
        if prev_id is not None and cand[b["id"]].rank == cand[prev_id].rank >= 4 \
                and not any(x["id"] not in cand for x in ordered[prev_pos + 1:pos]):
            demoted |= {b["id"], prev_id}
        prev_id, prev_pos = b["id"], pos
    for d in demoted:
        cand.pop(d, None)

    levels: dict[object, int] = {}
    style_levels: dict[str, int] = {}
    stack: list[dict] = []                  # frames: {style, level, tier, dec_depth}
    for b in ordered:                       # global reading order
        if b["id"] not in cand:
            continue
        sig = cand[b["id"]]
        text, page = meta[b["id"]]
        a = _authority_level(text, page, authority, printed_to_pdf) if authority is not None else None
        if a is not None:                   # TOC/outline override: reconcile stack to its level
            while stack and stack[-1]["level"] >= a:
                stack.pop()
            lvl = a
        else:
            lvl = level_for(sig, stack)
        levels[b["id"]] = lvl
        style_levels.setdefault(sig.style, lvl)
        stack.append({"style": sig.style, "level": lvl, "tier": sig.tier, "dec_depth": sig.dec_depth})
    return levels, style_levels


def heading_levels(blocks: list[dict], authority: HeadingAuthority | None = None,
                   printed_to_pdf: dict[str, int] | None = None) -> dict[object, int]:
    """block id -> document-relative heading level. Thin wrapper over ``_assign_heading_levels``."""
    return _assign_heading_levels(blocks, authority, printed_to_pdf)[0]


def build_sections(blocks: list[dict], tables: list[dict], figures: list[dict],
                   level_map: dict[object, int]) -> tuple[list[dict], dict[object, object]]:
    """Nest nodes under headings into a sections[] tree by global reading order; return
    (sections, section_by_node_id). Non-heading nodes attach to the current open section."""
    # tables carry a `pages` LIST (cross-page), blocks/figures a `page` scalar -- normalise for ordering,
    # else every table sorts to page 0 (before any heading) and never attaches to its section.
    def _page(n: dict) -> int:
        return n.get("page") or (n.get("pages") or [0])[0]
    nodes = sorted([*blocks, *tables, *figures], key=lambda n: (_page(n), n.get("order", 0)))
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
                         max_level: int = 6, style_levels: dict[str, int] | None = None) -> str:
    """Set ``#``*level on heading lines detected DIRECTLY in the markdown (the rendered view), so a
    running-header chapter/section line (``第1章 …``) is leveled even when the structure layer's ODL
    block text differs from the VLM's. A line's level is its section level from ``page_headings`` if
    matched, else the document-learned ``style_levels[style]`` (same document-relative scale, NOT the
    dead absolute rank), else a minimal ``tier+1`` default. Table/figure captions the VLM marked as
    headings are de-headed; enumerated ①②③ item runs with no body between are left as plain list
    items. Line count is unchanged."""
    level_of = {_normalize(t): lvl for t, lvl in (page_headings or [])}
    style_levels = style_levels or {}
    lines = markdown.split("\n")
    cand: list[tuple[int, NumberClass, str]] = []  # (line index, NumberClass, body text)
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
        if nc is None or body.rstrip()[-1:] in _TERMINATORS or len(body) > 120 \
                or _is_prose_not_heading(body):  # not a heading line (sentence / reference / citation)
            continue
        cand.append((i, nc, body))

    cand_idx = {c[0] for c in cand}             # demote enumerated item runs (rank>=4, no body between)
    demote: set[int] = set()
    for (i0, n0, _), (i1, n1, _) in zip(cand, cand[1:]):
        if n1.rank == n0.rank >= 4 and not any(lines[k].strip() and k not in cand_idx for k in range(i0 + 1, i1)):
            demote |= {i0, i1}

    for i, nc, body in cand:
        if i in demote:
            lines[i] = body                     # enumerated list item -> plain
            continue
        lvl = level_of.get(_normalize(body)) or style_levels.get(nc.style) or (nc.tier + 1)
        lines[i] = "#" * min(lvl, max_level) + " " + body
    return "\n".join(lines)


_HEADING_LINE = re.compile(r"^(#{1,2}) +(.*)")  # only chapter(#)/section(##) -- subsections recur legitimately


def _num_key(text: str) -> str:
    """The leading numbering token (第1章 / 6 / Ⅰ) as a whitespace-free key. Keying on the NUMBER, not
    the title, makes running-header detection robust to the VLM transcribing the same header
    differently across pages -- or merging two of them onto one line (第1章…第4節…)."""
    m = _NUM_PREFIX.match(text)
    return re.sub(r"\s+", "", m.group(0)) if m else _normalize(text)


def strip_page_furniture(markdowns: dict[int, str], page_labels: dict[int, str | None]) -> dict[int, str]:
    """Drop page furniture the VLM transcribed as content: a chapter/section heading (``#``/``##``)
    whose leading number recurs on >=2 pages is a running header, not a real boundary (it would
    fabricate a chapter break on every page); a bare line equal to a page's printed number is a
    footer leak. Both are removed -- the genuine hierarchy still lives in ``sections[]`` and in the
    one-off section headings. Subsection/item headings (``###``+) are never touched (現状/強み recur)."""
    counts: Counter[str] = Counter()
    for md in markdowns.values():
        on_page = {_num_key(m.group(2)) for ln in md.split("\n") if (m := _HEADING_LINE.match(ln))}
        counts.update(on_page)
    running = {k for k, c in counts.items() if c >= 2}
    out: dict[int, str] = {}
    for idx, md in markdowns.items():
        label = page_labels.get(idx)
        kept = [
            ln for ln in md.split("\n")
            if not ((m := _HEADING_LINE.match(ln)) and _num_key(m.group(2)) in running)
            and not (label is not None and ln.strip() == label)
        ]
        out[idx] = re.sub(r"\n{3,}", "\n\n", "\n".join(kept))  # collapse the blanks a removed line leaves
    return out
