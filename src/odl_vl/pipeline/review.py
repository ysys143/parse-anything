"""Domain-adaptation review harness: a side-by-side HTML view of a run.

Contract: processing-tiers R-A2 (source vs extraction side by side) and R-A3 (surface only
the risky items -- flagged pages). This is the tool that makes per-domain measurement and
human verification cheap; the human reviews flagged pages, not everything, and those verdicts
become the domain golden set (R-A5).

It renders each non-folded page image (base64) next to its extracted Markdown and its guard
flags; flagged pages are marked so a reviewer can jump straight to them.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path

from .render import render_page_png
from .run import DocumentResult


def build_review_html(pdf_path: str, result: DocumentResult, *, scale: float = 1.5) -> str:
    flagged = sum(1 for p in result.pages if p.flags and p.route != "folded")
    parts = [
        "<!doctype html><meta charset='utf-8'><title>ODL-VL review</title>",
        "<style>body{font-family:sans-serif;margin:1rem}.pg{display:flex;gap:1rem;border-top:1px solid #ccc;padding:1rem 0}"
        ".pg img{max-width:48%;border:1px solid #ddd}.col{flex:1}.flag{background:#fee;color:#900;padding:2px 6px;border-radius:4px;margin:2px;display:inline-block}"
        "pre{white-space:pre-wrap;background:#f6f6f6;padding:.5rem;max-height:60vh;overflow:auto}.flagged{outline:3px solid #f33}</style>",
        f"<h1>Review — {html.escape(Path(pdf_path).name)}</h1>",
        f"<p>{len(result.pages)} pages, {flagged} flagged for review.</p>",
    ]
    for p in result.pages:
        if p.route == "folded":
            parts.append(f"<div class='pg'><div class='col'>page {p.page_index}: folded into the spanning table</div></div>")
            continue
        img_b64 = base64.b64encode(render_page_png(pdf_path, p.page_index, scale=scale)).decode("ascii")
        flag_html = "".join(f"<span class='flag'>{html.escape(f)}</span>" for f in p.flags) or "<em>no flags</em>"
        cls = " flagged" if p.flags else ""
        parts.append(
            f"<div class='pg{cls}'>"
            f"<img src='data:image/png;base64,{img_b64}' alt='page {p.page_index}'>"
            f"<div class='col'><b>page {p.page_index}</b> — route={html.escape(p.route)} "
            f"vlm={p.used_vlm}<div>{flag_html}</div><pre>{html.escape(p.markdown)}</pre></div></div>"
        )
    return "".join(parts)


def write_review(pdf_path: str, result: DocumentResult, out_path: str | Path, *, scale: float = 1.5) -> None:
    Path(out_path).write_text(build_review_html(pdf_path, result, scale=scale), encoding="utf-8")
