"""Reflow column-wrapped Markdown into flowing paragraphs.

A VLM transcribing a narrow-column page mirrors the page's physical line wraps, so a sentence
broken across lines for column width comes out with hard newlines mid-sentence (``...の売上高\\n合計。``).
Asking the model to reflow competes with "verbatim / preserve reading order" and is ignored, so we
do it deterministically: join a line onto the previous one UNLESS it begins a real structural unit
(heading, table row, list item, label, figure, blockquote, code fence). For scripts without
inter-word spaces (CJK) we join with no space; otherwise with one. Only the layout wrap is dropped,
never a character -- tables, headings and list structure are preserved untouched.
"""
from __future__ import annotations

import re

_WS = " \t　"  # incl. fullwidth space (leading indent on CJK continuation/list lines)

# A line that STARTS a new structural unit must not be folded into the previous line.
_STARTS_UNIT = re.compile(
    r"(?:"
    r"#|"                       # heading
    r"\||"                      # table row
    r">|"                       # blockquote
    r"```|"                     # code fence
    r"!\[|"                     # image
    r"\[figure\]|"              # figure placeholder
    r"[-*+]\s|"                 # markdown bullet
    r"\d+(?:\.\d+)*[.)]\s|"     # numbered / hierarchical list item: '3. ', '3.1. ', '4.2. ' (TOC entries)
    r"[０-９]+[.．｡)）]|"   # fullwidth numbered list  １． ２）
    r"（[0-9０-９]+）|"          # （１） section marker
    r"[①-⑳]|"          # circled numbers ①-⑳
    r"[・▪◦‣•]|"          # bullets ・ ▪ ◦ ‣ •
    r"[^\s：:]{1,8}[：:]\s*\S"            # short label:  備考： 資料： Note:
    r")"
)
# A line we must never append a continuation onto (its own block stays intact).
_NO_FOLD_INTO = ("#", "|", ">", "```", "![", "[figure]")
# Short heading-like labels (#, （１）, ①) head their own block: body must NOT fold into them. A
# numbered/bulleted LIST item is NOT heading-like, so its own wrapped continuation still folds in.
_HEADING_LIKE = re.compile(r"(?:#|（[0-9０-９]+）|[①-⑳])")


def _starts_unit(line: str) -> bool:
    return bool(_STARTS_UNIT.match(line.lstrip(_WS)))


def _no_fold_into(line: str) -> bool:
    s = line.lstrip(_WS)
    return s.startswith(_NO_FOLD_INTO) or bool(_HEADING_LIKE.match(s))


def _is_cjk(ch: str) -> bool:
    return bool(ch) and (
        "぀" <= ch <= "ヿ"      # hiragana + katakana
        or "㐀" <= ch <= "鿿"   # CJK ideographs
        or "가" <= ch <= "힣"   # hangul syllables
        or "＀" <= ch <= "￯"   # fullwidth / halfwidth forms
    )


def reflow_markdown(md: str) -> str:
    """Join column-wrapped lines into flowing paragraphs; preserve tables, headings, lists, code."""
    out: list[str] = []
    in_code = False
    for raw in md.split("\n"):
        line = raw.rstrip()
        if line.lstrip(_WS).startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:  # never reflow fenced code-block contents
            out.append(line)
            continue
        if not line.strip():
            out.append("")  # blank line = hard paragraph break
            continue
        prev = out[-1] if out else ""
        # a pipe anywhere marks a table row (GFM allows no leading pipe) -- never fold it either way
        if prev and "|" not in prev and "|" not in line and not _no_fold_into(prev) and not _starts_unit(line):
            cur = line.lstrip(_WS)
            sep = "" if (_is_cjk(prev[-1]) or _is_cjk(cur[0])) else " "
            out[-1] = prev + sep + cur
        else:
            out.append(line)
    return "\n".join(out)
