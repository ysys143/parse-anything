"""TEDS + text-1NED scoring of Track B variants against OmniDocBench GT (image-only).

Reuses the F22 scoring approach (bench_omnidoc.py): table TEDS via apted, text via 1-NED. Scores
each variant's output Markdown (one doc{NN}.md per GT record) against the golden HTML tables and
text. This measures whether the ODL-hybrid round-trip (Track B) preserves table structure as well
as the direct-VLM path (Track A / F22).

Usage:
    python3 scripts/track_b_teds.py <gt.json> <label>=<md_dir> [<label>=<md_dir> ...]
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, ".local/scripts")  # teds.py lives with the bench scripts
from teds import teds  # noqa: E402

import Levenshtein  # noqa: E402


def norm_text(s: str) -> str:
    s = re.sub(r"!\[.*?\]\(.*?\)", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[#*`>|_\-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _md_blocks(md: str) -> list[list[str]]:
    blocks, cur = [], []
    for ln in md.split("\n"):
        if ln.strip().startswith("|"):
            cur.append(ln)
        else:
            if len(cur) >= 2:
                blocks.append(cur)
            cur = []
    if len(cur) >= 2:
        blocks.append(cur)
    return blocks


def _md_to_html(block: list[str]) -> str:
    rows = []
    for ln in block:
        if re.match(r"^\s*\|?\s*:?-{2,}", ln):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return "<table>" + "".join(rows) + "</table>"


def tables_html(md: str) -> list[str]:
    if not md:
        return []
    out = re.findall(r"<table.*?</table>", md, re.DOTALL | re.IGNORECASE)
    out += [_md_to_html(b) for b in _md_blocks(md)]
    return out


def text_score(output: str | None, gt: str) -> float | None:
    if output is None or not gt.strip():
        return None
    a, b = norm_text(output), norm_text(gt)
    m = max(len(a), len(b))
    return 1.0 - Levenshtein.distance(a, b) / m if m else 1.0


def table_score(out_html: list[str], gt_html: list[str]) -> float | None:
    if not gt_html:
        return None
    if not out_html:
        return 0.0
    return sum(max((teds(gt, oh) for oh in out_html), default=0.0) for gt in gt_html) / len(gt_html)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def main(argv: list[str]) -> int:
    gt = json.load(open(argv[0], encoding="utf-8"))
    rows = []
    for arg in argv[1:]:
        label, _, md_dir = arg.partition("=")
        teds_scores, text_scores = [], []
        for i, g in enumerate(gt):
            try:
                md = open(f"{md_dir}/doc{i:02d}.md", encoding="utf-8").read()
            except OSError:
                md = ""
            ts = table_score(tables_html(md), g["gt_tables"])
            txt = text_score(md, g["gt_text"])
            if ts is not None:
                teds_scores.append(ts)
            if txt is not None:
                text_scores.append(txt)
        rows.append((label, _mean(teds_scores), len(teds_scores), _mean(text_scores), len(text_scores)))

    w = max(len(r[0]) for r in rows)
    print("variant".ljust(w) + "   table_TEDS    (n)     text_1NED    (n)")
    print("-" * (w + 45))
    for label, td, ntd, tx, ntx in rows:
        print(f"{label.ljust(w)}   {td:8.3f}   {ntd:4d}     {tx:8.3f}   {ntx:4d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
