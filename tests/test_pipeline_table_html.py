from __future__ import annotations

from pathlib import Path

from parse_anything.pipeline.output import _table_html, _write_tables


def test_table_html_header_and_body_rows():
    cells = [[{"text": "Name"}, {"text": "Qty"}],
             [{"text": "Bolt"}, {"text": "12"}]]
    html = _table_html(cells)
    # row 0 is <th>, but all rows share ONE <tbody> (no separate <thead>) so header rowspans survive
    assert "<tbody><tr><th>Name</th><th>Qty</th></tr><tr><td>Bolt</td><td>12</td></tr></tbody>" in html
    assert "<thead>" not in html


def test_table_html_header_rowspan_survives_into_body():
    # regression: a multi-level header where a row-0 cell spans DOWN into the body. A <thead>/<tbody>
    # split would clamp the rowspan at the group boundary and shift the body row left (Q1 under Region).
    cells = [[{"text": "Region", "row_span": 2}, {"text": "Sales", "col_span": 2}],
             [{"text": "Q1"}, {"text": "Q2"}]]
    html = _table_html(cells)
    assert '<th rowspan="2">Region</th><th colspan="2">Sales</th>' in html
    assert "<tr><td>Q1</td><td>Q2</td></tr>" in html   # body row keeps both cells; Region reserves col 0
    assert "<thead>" not in html                       # single row group -> rowspan not clamped


def test_table_html_missing_text_key_does_not_crash():
    # defensive: a cell dict without "text" must render empty, not abort the whole tables/ write pass
    assert "<td></td>" in _table_html([[{"text": "H"}], [{}]])


def test_table_html_preserves_col_and_row_spans():
    # the span info the Markdown view drops must survive as colspan/rowspan; a 1x1 cell stays attr-less
    cells = [[{"text": "merged", "col_span": 2}, {"text": "solo"}],
             [{"text": "a"}, {"text": "b"}, {"text": "c"}],
             [{"text": "tall", "row_span": 2}, {"text": "x"}]]
    html = _table_html(cells)
    assert '<th colspan="2">merged</th>' in html
    assert "<th>solo</th>" in html              # 1x1 header cell -> no attrs
    assert '<td rowspan="2">tall</td>' in html
    assert html.count("colspan") == 1 and html.count("rowspan") == 1   # only the two spanning cells


def test_table_html_escapes_markup_chars():
    cells = [[{"text": "a < b & c"}], [{"text": "<script>"}]]
    html = _table_html(cells)
    assert "a &lt; b &amp; c" in html and "&lt;script&gt;" in html
    assert "<script>" not in html               # raw markup never leaks into the cell text


def test_table_html_empty_is_blank():
    assert _table_html([]) == ""


def test_write_tables_emits_html_view(tmp_path: Path):
    tables = [{"id": "t1", "cells": [[{"text": "H"}], [{"text": "v"}]]}]
    _write_tables(tmp_path, tables)
    html_file = tmp_path / "tables" / "t1.html"
    assert html_file.exists()
    assert "<th>H</th>" in html_file.read_text(encoding="utf-8")
