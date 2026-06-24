"""Two-provider output reconciliation for det_vlm combined mode (R10).

Benchmark evidence (hard cases): a doc-specialised VLM (PaddleOCR-VL) reconstructs large/complex
tables far more completely than a general flash-lite VLM, which often abandons them -- but Paddle
is also stronger at dense TEXT, so a fixed "Gemini text + Paddle tables" merge dropped combined
below Paddle-alone (F22). Combined is now SYMMETRIC best-of-both: the text spine comes from
whichever output has the richer non-table text, and each table takes the more-complete of the two
-- REPLACING or APPENDING. Neither provider's strength is discarded by a fixed role.
"""
from __future__ import annotations

import re

_HTML_TABLE = re.compile(r"<table.*?</table>", re.DOTALL | re.IGNORECASE)


def table_blocks(md: str) -> list[str]:
    """Every table in a Markdown string as a text block -- raw <table> HTML + pipe `|` tables."""
    if not md:
        return []
    blocks = _HTML_TABLE.findall(md)
    cur: list[str] = []
    for line in md.split("\n"):
        if line.strip().startswith("|"):
            cur.append(line)
        else:
            if len(cur) >= 2:
                blocks.append("\n".join(cur))
            cur = []
    if len(cur) >= 2:
        blocks.append("\n".join(cur))
    return blocks


def _content_size(block: str) -> int:
    """Format-agnostic completeness proxy: actual cell-TEXT length (HTML tags + markdown table
    punctuation stripped). A full 16-col HTML table beats a flat-markdown table that compressed
    or dropped columns -- unlike raw cell counts, which mis-rank colspan/rowspan HTML."""
    text = re.sub(r"<[^>]+>", " ", block)        # strip HTML tags
    text = re.sub(r"[|:\-]+", " ", text)          # strip markdown table punctuation
    return len(re.sub(r"\s+", "", text))


def _text_size(md: str) -> int:
    """Out-of-table text content size (so a big table doesn't decide the text spine)."""
    body = md
    for t in table_blocks(md):
        body = body.replace(t, " ", 1)
    return len(re.sub(r"<[^>]+>|[|:\-]|\s", "", body))


def merge_outputs(primary_md: str, secondary_md: str) -> str:
    """Best-of-both: the spine (text) comes from whichever output has the richer non-table text,
    and each table takes the more-complete of the two -- replacing or appending. Symmetric, so a
    strong provider's text is never lost by forcing the weaker one as the spine (F22 fix: combined
    text used to drop below Paddle because Gemini was always the spine)."""
    primary_md, secondary_md = primary_md or "", secondary_md or ""
    spine, other = ((primary_md, secondary_md) if _text_size(primary_md) >= _text_size(secondary_md)
                    else (secondary_md, primary_md))
    s_tables, o_tables = table_blocks(spine), table_blocks(other)
    out = spine
    for i, st in enumerate(s_tables):
        if i < len(o_tables) and _content_size(o_tables[i]) > _content_size(st):
            out = out.replace(st, o_tables[i], 1)
    for ot in o_tables[len(s_tables):]:   # tables the spine dropped -> APPEND
        out = (out + "\n\n" + ot) if out.strip() else ot
    return out
