from __future__ import annotations

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from parse_anything.pipeline.signals import document_signals
from parse_anything.pipeline.triage import Route, decide_route


def _make_text_pdf(path, pages: int = 1) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    for i in range(pages):
        for j in range(20):
            c.drawString(72, 720 - j * 24, f"Line {j} of page {i + 1}: plain prose paragraph text.")
        c.showPage()
    c.save()
    return str(path)


def test_document_signals_length_matches_pages(tmp_path):
    sigs = document_signals(_make_text_pdf(tmp_path / "d.pdf", pages=2))
    assert len(sigs) == 2


def test_text_only_page_has_text_no_images(tmp_path):
    s = document_signals(_make_text_pdf(tmp_path / "d.pdf", pages=1))[0]
    assert s.text_chars > 50
    assert s.image_count == 0


def test_text_only_page_routes_deterministic(tmp_path):
    # plain prose (text, no table, no image) -> skip VLM
    s = document_signals(_make_text_pdf(tmp_path / "d.pdf", pages=1))[0]
    assert decide_route(s) == Route.DETERMINISTIC
