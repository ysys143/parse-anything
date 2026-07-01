from __future__ import annotations

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from odl_vl.pipeline.deterministic import number_tokens, page_text, text_char_count
from odl_vl.pipeline.guards import source_gate


def _make_pdf(path, lines) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 720
    for ln in lines:
        c.drawString(72, y, ln)
        y -= 24
    c.showPage()
    c.save()
    return str(path)


def test_number_tokens_extracts_grouped_and_plain_numbers(tmp_path):
    pdf = _make_pdf(tmp_path / "d.pdf", ["Unit 1,234,567", "Qty 3", "Total 3,703,701"])
    vals = [t.value for t in number_tokens(pdf, 0)]
    assert "1234567" in vals
    assert "3703701" in vals
    assert "3" in vals


def test_number_tokens_min_value_filter(tmp_path):
    pdf = _make_pdf(tmp_path / "d.pdf", ["small 12", "big 1,000,000"])
    vals = [t.value for t in number_tokens(pdf, 0, min_value=1000)]
    assert vals == ["1000000"]


def test_number_tokens_carry_distinct_row_positions(tmp_path):
    pdf = _make_pdf(tmp_path / "d.pdf", ["A 100", "B 200"])
    ys = {round(t.y) for t in number_tokens(pdf, 0)}
    assert len(ys) >= 2  # numbers on different rows have different y


def test_text_char_count_nonzero_for_born_digital(tmp_path):
    pdf = _make_pdf(tmp_path / "d.pdf", ["hello world"])
    assert text_char_count(pdf, 0) > 5
    assert "hello" in page_text(pdf, 0)


def test_extracted_numbers_drive_source_gate(tmp_path):
    # F8: extracted text-layer numbers are the oracle/source for the gate.
    pdf = _make_pdf(tmp_path / "d.pdf", ["price 1,234,567"])
    src = [t.value for t in number_tokens(pdf, 0)]
    assert source_gate(["1234567"], src) == []          # grounded value passes
    assert source_gate(["9999999"], src) == ["9999999"]  # fabricated value is flagged
