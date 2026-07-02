from __future__ import annotations

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from parse_anything.pipeline.review import build_review_html, write_review
from parse_anything.pipeline.run import DocumentResult, PageOutcome


def _two_page_pdf(path) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, "Page one content.")
    c.showPage()
    c.drawString(72, 720, "Page two content.")
    c.showPage()
    c.save()
    return str(path)


def _result() -> DocumentResult:
    return DocumentResult(
        (
            PageOutcome(0, "table_vlm", True, "# Table\n\n| a | 1 |", 10.0, ("unsourced_number:9999999",)),
            PageOutcome(1, "deterministic", False, "plain text page", 1.0, ()),
        )
    )


def test_review_html_surfaces_flags_images_and_markdown(tmp_path):
    html = build_review_html(_two_page_pdf(tmp_path / "d.pdf"), _result())
    assert "unsourced_number:9999999" in html          # flag surfaced
    assert "data:image/png;base64," in html            # page image embedded
    assert "flagged" in html                           # page 0 marked for review
    assert "Table" in html and "plain text page" in html


def test_write_review_writes_html_file(tmp_path):
    out = tmp_path / "review.html"
    write_review(_two_page_pdf(tmp_path / "d.pdf"), _result(), out)
    assert out.read_text(encoding="utf-8").startswith("<!doctype html")
