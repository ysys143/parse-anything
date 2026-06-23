"""Output assembly: per-page Markdown, document.md, ledger.jsonl, results.jsonl.

Contract: pdf-pipeline-requirements §7. Folded continuation pages contribute no separate
markdown file (their content lives in the start page's merged table) but are still recorded
in results.jsonl with their fold reference. Run artifacts are git-ignored (see .gitignore).
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .run import DocumentResult


def write_outputs(result: DocumentResult, out_dir: str | Path) -> None:
    out = Path(out_dir)
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    doc_parts: list[str] = []
    for p in result.pages:
        record = {"page_index": p.page_index, "route": p.route, "used_vlm": p.used_vlm, "flags": list(p.flags)}
        if p.route == "folded":
            results.append(record)
            continue
        name = f"page-{p.page_index:03d}.md"
        (pages_dir / name).write_text(p.markdown, encoding="utf-8")
        record["markdown_file"] = f"pages/{name}"
        results.append(record)
        doc_parts.append(p.markdown)

    (out / "document.md").write_text("\n\n---\n\n".join(doc_parts), encoding="utf-8")
    _write_jsonl(out / "ledger.jsonl", result.ledger())
    _write_jsonl(out / "results.jsonl", results)


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            f.write("\n")
