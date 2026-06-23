from __future__ import annotations

import json

from odl_vl.pipeline.output import write_outputs
from odl_vl.pipeline.run import DocumentResult, PageOutcome


def _result() -> DocumentResult:
    return DocumentResult(
        (
            PageOutcome(0, "table_vlm", True, "# Page 0\n\n| a | 1 |", 12.0, ("spanning_table:0-1",)),
            PageOutcome(1, "folded", False, "", 0.0, ("folded_into:0",)),
            PageOutcome(2, "deterministic", False, "plain text page", 1.0, ()),
        )
    )


def test_write_outputs_creates_pages_doc_and_jsonl(tmp_path):
    write_outputs(_result(), tmp_path)
    # per-page markdown only for non-folded pages
    assert (tmp_path / "pages" / "page-000.md").read_text(encoding="utf-8").startswith("# Page 0")
    assert (tmp_path / "pages" / "page-002.md").exists()
    assert not (tmp_path / "pages" / "page-001.md").exists()  # folded -> no file
    # document assembly excludes folded pages
    doc = (tmp_path / "document.md").read_text(encoding="utf-8")
    assert "# Page 0" in doc and "plain text page" in doc


def test_results_jsonl_records_every_page_including_folded(tmp_path):
    write_outputs(_result(), tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "results.jsonl").read_text().splitlines()]
    assert [r["page_index"] for r in rows] == [0, 1, 2]
    folded = next(r for r in rows if r["page_index"] == 1)
    assert folded["route"] == "folded" and "folded_into:0" in folded["flags"]
    assert "markdown_file" not in folded


def test_ledger_jsonl_has_one_row_per_page(tmp_path):
    write_outputs(_result(), tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    assert rows[0]["route"] == "table_vlm" and rows[0]["used_vlm"] is True
