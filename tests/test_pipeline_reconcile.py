from __future__ import annotations

from odl_vl.pipeline.reconcile import merge_outputs, table_blocks


def test_table_blocks_finds_markdown_and_html():
    md = "x\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\n<table><tr><td>c</td></tr></table>"
    blocks = table_blocks(md)
    assert len(blocks) == 2


def test_merge_replaces_with_more_complete_secondary_table():
    gemini = "# Title\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nfooter"
    paddle = "| a | b | c |\n| --- | --- | --- |\n| 1 | 2 | 3 |"   # one extra column
    out = merge_outputs(gemini, paddle)
    assert "| c |" in out and "Title" in out and "footer" in out   # spine kept, table upgraded


def test_merge_appends_table_primary_dropped():
    gemini = "# Title\n\nlong narrative text, the model abandoned the table"
    paddle = "| x | y |\n| --- | --- |\n| 1 | 2 |"
    out = merge_outputs(gemini, paddle)
    assert "| x | y |" in out and "Title" in out                   # paddle table appended, not lost


def test_merge_noop_when_secondary_has_no_table():
    assert merge_outputs("just text", "also just text") == "just text"
