"""Two-provider output reconciliation for det_vlm combined mode (R10).

Benchmark evidence (hard cases): a doc-specialised VLM (PaddleOCR-VL) reconstructs large/complex
tables far more completely than a general flash-lite VLM, which often abandons them. So combined
mode keeps the (grounded) Gemini text as the spine and uses Paddle's tables where they are at
least as complete -- REPLACING a Gemini table or APPENDING a table Gemini dropped entirely (the
gap the earlier replace-only reconcile missed).
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


def merge_outputs(primary_md: str, secondary_md: str) -> str:
    """Primary (Gemini, grounded) text spine; secondary (Paddle) tables when more complete --
    replacing the matching primary table or appending one the primary omitted."""
    primary_md = primary_md or ""
    p_tables = table_blocks(primary_md)
    s_tables = table_blocks(secondary_md or "")
    if not s_tables:
        return primary_md
    out = primary_md
    for i, pt in enumerate(p_tables):
        if i < len(s_tables) and _content_size(s_tables[i]) >= _content_size(pt):
            out = out.replace(pt, s_tables[i], 1)
    for st in s_tables[len(p_tables):]:   # secondary tables the primary dropped -> APPEND
        out = (out + "\n\n" + st) if out.strip() else st
    return out
