from __future__ import annotations

import json

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


def test_review_html_overlays_document_json_bboxes_and_links_nodes(tmp_path):
    pdf = _two_page_pdf(tmp_path / "d.pdf")
    document_json = {
        "pages": [{"page_index": 0, "content": ["b1", "f1"], "blocks": ["b1"], "tables": [], "figures": ["f1"]}],
        "blocks": [{"id": "b1", "type": "paragraph", "page": 1, "bbox": [72, 700, 260, 724], "text": "Block text"}],
        "tables": [],
        "figures": [{
            "id": "f1", "type": "figure", "page": 1, "bbox": [80, 500, 300, 620],
            "label": "Figure 1", "caption": "Figure 1. Caption", "description": "Figure description",
        }],
    }

    html = build_review_html(pdf, _result(), document_json=document_json)

    assert "data-node='b1'" in html and "href='#node-b1'" in html
    assert "data-node='f1'" in html and "href='#node-f1'" in html
    assert "id='node-b1'" in html and "Block text" in html
    assert "id='node-f1'" in html and "Figure description" in html
    assert "function highlightNode" in html


def test_write_review_loads_sibling_document_json(tmp_path):
    pdf = _two_page_pdf(tmp_path / "d.pdf")
    out = tmp_path / "review.html"
    (tmp_path / "document.json").write_text(
        json.dumps({
            "pages": [{"page_index": 0, "content": ["f1"], "blocks": [], "tables": [], "figures": ["f1"]}],
            "blocks": [],
            "tables": [],
            "figures": [{"id": "f1", "type": "figure", "page": 1, "bbox": [80, 500, 300, 620], "description": "Overlay figure"}],
        }),
        encoding="utf-8",
    )

    write_review(pdf, _result(), out)

    html = out.read_text(encoding="utf-8")
    assert "data-node='f1'" in html
    assert "Overlay figure" in html


def test_write_review_ignores_malformed_sibling_document_json(tmp_path):
    pdf = _two_page_pdf(tmp_path / "d.pdf")
    out = tmp_path / "review.html"
    (tmp_path / "document.json").write_text("{not-json", encoding="utf-8")

    write_review(pdf, _result(), out)

    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html")
    assert "data-node='" not in html
