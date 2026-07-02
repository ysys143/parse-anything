from __future__ import annotations

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from parse_anything.pipeline.crosspage import continuation_groups, continues
from parse_anything.pipeline.triage import Route


def _draw_table(c, rows, cols_x, y_start, y_step=28):
    y = y_start
    for row in rows:
        for x, cell in zip(cols_x, row):
            c.drawString(x, y, cell)
        y -= y_step


_ROWS_A = [["A1", "B1", "C1", "D1"], ["A2", "B2", "C2", "D2"], ["A3", "B3", "C3", "D3"], ["A4", "B4", "C4", "D4"]]
_ROWS_B = [["A5", "B5", "C5", "D5"], ["A6", "B6", "C6", "D6"], ["A7", "B7", "C7", "D7"], ["A8", "B8", "C8", "D8"]]


def _make_pdf(path, page2_cols):
    c = canvas.Canvas(str(path), pagesize=letter)
    _draw_table(c, _ROWS_A, [72, 180, 300, 420], y_start=300)   # table at bottom of page 1
    c.showPage()
    rows_b = [r[: len(page2_cols)] for r in _ROWS_B]
    _draw_table(c, rows_b, page2_cols, y_start=700)             # table at top of page 2
    c.showPage()
    c.save()
    return str(path)


def test_matching_columns_detected_as_continuation(tmp_path):
    pdf = _make_pdf(tmp_path / "cont.pdf", page2_cols=[72, 180, 300, 420])  # same columns
    res = continues(pdf, 0, 1)
    assert res.is_continuation is True
    assert res.column_match >= 0.7


def test_different_columns_not_continuation(tmp_path):
    pdf = _make_pdf(tmp_path / "sep.pdf", page2_cols=[110, 270])  # different, fewer columns
    res = continues(pdf, 0, 1)
    assert res.is_continuation is False
    assert res.column_match < 0.7


def test_continuation_groups_merges_matching_table_pages(tmp_path):
    pdf = _make_pdf(tmp_path / "cont.pdf", page2_cols=[72, 180, 300, 420])
    assert continuation_groups(pdf, [Route.TABLE_VLM, Route.TABLE_VLM]) == [[0, 1]]


def test_continuation_groups_keeps_separate_tables_apart(tmp_path):
    pdf = _make_pdf(tmp_path / "sep.pdf", page2_cols=[110, 270])
    assert continuation_groups(pdf, [Route.TABLE_VLM, Route.TABLE_VLM]) == [[0], [1]]


def test_continuation_groups_does_not_merge_non_table_routes(tmp_path):
    pdf = _make_pdf(tmp_path / "cont.pdf", page2_cols=[72, 180, 300, 420])
    # matching columns, but non-table routes never join a spanning-table group
    assert continuation_groups(pdf, [Route.DETERMINISTIC, Route.DETERMINISTIC]) == [[0], [1]]
