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
from typing import TYPE_CHECKING

from .numbering import NumberClass, classify_numbering, level_for
from .outline import HeadingAuthority
from .textalign import common_prefix_len, norm_block

if TYPE_CHECKING:
    from .ontology import Ontology

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
_PAREN_ONLY = re.compile(r"[（(]\s*\d+\s*[）)][.．]?")   # '(2020).' / '(13)' -- a citation year / equation number
_EQ_TAIL = re.compile(r"\(\s*\d+\s*\)\s*$")   # a trailing display-equation number, e.g. '… (13)'
# a "word": a run of >=3 letters (Latin/accented/Hangul/Kana/CJK). A real heading always has one.
_HEADING_WORD = re.compile(r"[A-Za-zÀ-ɏ가-힣぀-ヿ一-鿿]{3,}")
# a letter bonded to a superscript digit/marker ('Latimer1∗', 'LeeID1') -- an author/affiliation line.
_AUTHOR_AFFIL = re.compile(r"[A-Za-z][0-9∗*†‡§¶]")
_NON_SECTION_ZONES = frozenset({"cover", "metadata", "furniture"})   # body sections never live here


def _looks_like_equation(text: str) -> bool:
    """A display equation or math/chart fragment ODL mis-typed as a heading: it carries an '=' or a
    trailing equation number, or has NO real word at all (bare symbols / single letters like 'A B',
    'N(0, 1)', 'Cγ = …'). Vetoes these from unnumbered-heading admission."""
    t = text.strip()
    return "=" in t or bool(_EQ_TAIL.search(t)) or not _HEADING_WORD.search(t)


def _is_prose_not_heading(text: str) -> bool:
    """A NUMBERED line that is really citation/prose, not a heading: after stripping the numbering
    marker it carries a URL/DOI/PMID, or has >=2 internal sentence boundaries (a heading is one short
    phrase). Stops a reference entry ('13. Author A, Author B. Title. Journal. Year') or a citation
    fragment ('(1):2757. https://doi.org/...') and a volume:page tail ('(3):213-224.') from being
    leveled as a section. A line carrying a table pipe ('0.3 s | 0.9 s | …') is a data row, also not a
    heading. Document-agnostic."""
    if "|" in text:  # a table data row the VLM rendered inline, not a section heading
        return True
    if _PAREN_ONLY.fullmatch(text.strip()):  # '(2020).' bare paren-number -> citation year / eq number
        return True
    rest = _NUM_PREFIX.sub("", text.strip(), count=1).lstrip()
    if not rest or rest[0] == ":":  # 'marker:digits' -> a volume:page citation, not a heading
        return True
    return bool(_CITE_RE.search(rest)) or len(_SENTENCE_BOUNDARY.findall(rest)) >= 2


def _authority_level(text: str, page: int | None, authority: HeadingAuthority, printed_to_pdf: dict[str, int]) -> int | None:
    """Match a body heading to an authority entry (resolved to its PDF page) by normalized title."""
    norm = _normalize(text)
    if not norm or page is None:
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
                           printed_to_pdf: dict[str, int] | None = None, ontology: "Ontology | None" = None,
                           font_ranks: dict[object, float | None] | None = None) -> tuple[dict[object, int], dict[str, int]]:
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

    # UNNUMBERED prose headings: ODL typed them as headings (or gave a structural role / heading_level)
    # but they carry no numbering, so the path above abstained -- leaving papers like latimer with 0
    # sections despite 38 heading blocks. Admit them via the injected ontology (proposes) + the SAME
    # conservative prose/list/caption guards (dispose), and level them by document font-size rank. Only
    # truly UNNUMBERED blocks are considered here, so numbered detection/demotion is untouched.
    if ontology is not None:
        from .ontology import node_signals as _node_signals
        opos = {b["id"]: i for i, b in enumerate(ordered)}

        def _followed_by_body(bid: object) -> bool:
            # a real section heading is followed by body prose before the next heading; a chart label or
            # figure title is surrounded by more labels/figures, so this abstains on it (safe default).
            for nb in ordered[opos[bid] + 1: opos[bid] + 9]:
                if nb.get("type") == "heading":
                    return False
                if nb.get("type") == "paragraph" and len(nb.get("text", "")) >= 60:
                    return True
            return False

        prose: list[tuple[object, str, "int | None"]] = []
        for b in ordered:
            bid, text = b["id"], b.get("text", "")
            if bid in levels or classify_numbering(text) is not None:
                continue
            if (_is_list_not_heading(text, b.get("type", "")) or _is_prose_not_heading(text)
                    or _CAPTION_LEAD.match(text) or b.get("figure") or _looks_like_equation(text)
                    or _AUTHOR_AFFIL.search(text) or b.get("zone") in _NON_SECTION_ZONES):
                continue         # chart label / equation / author-affiliation line / non-body zone
            if getattr(ontology.classify(_node_signals(b, font_ranks)), "role", None) != "heading":
                continue
            if not _followed_by_body(bid):   # structural corroboration -- a real section is followed by prose
                continue
            prose.append((bid, text, b.get("page")))
        # Nesting for an unnumbered heading comes from the document's OWN declared hierarchy -- a PDF
        # outline / printed-TOC authority entry it matches (by normalized title + page). That is reliable,
        # document-declared structure. Absent an authority match it stays FLAT (level 1): font size / ODL
        # heading_level "flip between documents" (numbering.py) and do NOT reliably encode nesting, so we
        # abstain rather than fabricate a tree from a signal that does not generalize.
        pmap = printed_to_pdf or {}
        for bid, text, page in prose:
            a = _authority_level(text, page, authority, pmap) if (authority is not None and page is not None) else None
            levels[bid] = a if a is not None else 1

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
                   "zone": n.get("zone"), "page": n.get("page"),
                   "parent": stack[-1]["id"] if stack else None, "children": [], "content": []}
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


_DIGIT_RUN = re.compile(r"\d+")
_PUNCT = re.compile(r"[\W_]+")  # punctuation, separators AND underscores (rule-glyph '____' variants)


def _line_key(line: str) -> str:
    """Lowercased, punctuation-stripped, digit-masked, whitespace-collapsed form so a running header/
    footer matches across pages despite a changing page number ('30 / 32') AND transcription variants
    of the same furniture ('PLOS BIOLOGY | Corrective…' vs 'PLOS BIOLOGY Corrective…')."""
    return " ".join(_DIGIT_RUN.sub("#", _PUNCT.sub(" ", line.lower())).split())


def _furniture_candidate(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith(("#", "|", ">", "![", "<!--"))


def _absent_from_odl(line: str, odl_norms: list[str], min_lcp: int = 10) -> bool:
    """True when the line shares NO long prefix with any ODL block on the page -- i.e. ODL did not keep
    it as content. ODL filters running headers/footers upstream, so furniture is ODL-absent while genuine
    body always has a matching ODL block."""
    ln = norm_block(line)
    return not any(common_prefix_len(ln, on) >= min_lcp for on in odl_norms if len(on) >= 8)


def strip_page_furniture(markdowns: dict[int, str], page_labels: dict[int, str | None],
                         odl_norms_by_page: dict[int, list[str]] | None = None) -> dict[int, str]:
    """Drop page furniture the VLM re-typed as content, using ODL's own header/footer filtering as the
    signal rather than a tuned recurrence fraction. ODL excludes running headers/footers from its blocks,
    so a line that (a) matches NO ODL block on its page (ODL-ABSENT) and (b) recurs on >=2 pages is a
    running header/footer -- removed. Genuine body always has a matching ODL block, so it is never a
    candidate; the recurrence floor is thus the minimal 2, with no page-fraction threshold. A ``#``/``##``
    heading is dropped only when it is ALSO ODL-absent (so a real recurring subsection like ``## 7 工作機械``
    that ODL kept is protected by construction). A bare printed-page-number line is dropped via the label.
    Without ODL (``odl_norms_by_page`` empty) only the page-number line is touched -- conservative, since
    no furniture signal is available. Subsection/item headings (``###``+) and one-off lines are untouched."""
    odl_norms_by_page = odl_norms_by_page or {}

    def absent(line: str, idx: int) -> bool:
        return bool(odl_norms_by_page) and _absent_from_odl(line, odl_norms_by_page.get(idx, []))

    head_counts: Counter[str] = Counter()
    line_counts: Counter[str] = Counter()
    for idx, md in markdowns.items():
        heads, lines = set(), set()
        for ln in md.split("\n"):
            if (m := _HEADING_LINE.match(ln)) and absent(ln, idx):
                heads.add(_num_key(m.group(2)))
            elif _furniture_candidate(ln) and absent(ln, idx):
                lines.add(_line_key(ln))
        head_counts.update(heads)
        line_counts.update(lines)
    running_heads = {k for k, c in head_counts.items() if c >= 2}  # ODL-absent heading recurring = running header
    running_lines = {k for k, c in line_counts.items() if c >= 2}  # ODL-absent line recurring = furniture
    out: dict[int, str] = {}
    for idx, md in markdowns.items():
        label = page_labels.get(idx)
        kept: list[str] = []
        for ln in md.split("\n"):
            if (m := _HEADING_LINE.match(ln)) and _num_key(m.group(2)) in running_heads and absent(ln, idx):
                continue
            if label is not None and ln.strip() == label:
                continue
            if _furniture_candidate(ln) and _line_key(ln) in running_lines and absent(ln, idx):
                continue
            kept.append(ln)
        out[idx] = re.sub(r"\n{3,}", "\n\n", "\n".join(kept))  # collapse the blanks a removed line leaves
    return out
