from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from odl_vl.pipeline.odl_extract import (
    OdlPage,
    OdlTable,
    extract,
    extract_caption_labels,
    parse_document,
    substantial_tables,
)

_SYNTH = {
    "number of pages": 2,
    "kids": [
        {"type": "heading", "page number": 1, "content": "Title"},
        {"type": "paragraph", "page number": 1, "content": "Body text here."},
        {
            "type": "table",
            "page number": 1,
            "bounding box": [50, 50, 400, 200],
            "number of rows": 2,
            "number of columns": 2,
            "rows": [
                {"type": "table row", "cells": [{"type": "table cell", "content": "A"}, {"type": "table cell", "content": "1"}]},
                {"type": "table row", "cells": [{"type": "table cell", "content": "B"}, {"type": "table cell", "content": "2"}]},
            ],
        },
        {"type": "image", "page number": 2, "bounding box": [10, 10, 200, 200], "id": "img1"},
        {"type": "paragraph", "page number": 2, "content": "Page two."},
    ],
}


def test_parse_document_text_table_image():
    doc = parse_document(_SYNTH)
    assert doc.n_pages == 2
    p0 = doc.pages[0]
    assert p0.text == "Title\nBody text here."          # reading-ordered, table cells excluded
    assert len(p0.tables) == 1
    t = p0.tables[0]
    assert (t.n_rows, t.n_cols) == (2, 2)
    assert t.cells == (("A", "1"), ("B", "2"))           # 0-based page, row-major grid
    assert t.page_index == 0
    p1 = doc.pages[1]
    assert p1.text == "Page two." and not p1.tables
    assert len(p1.images) == 1 and p1.images[0].element_id == "img1"


def test_caption_labels_attach_to_nearest_table_and_figure():
    data = {
        "number of pages": 1,
        "kids": [
            {"type": "table", "page number": 1, "bounding box": [50, 500, 400, 600], "number of rows": 1, "number of columns": 2,
             "rows": [{"type": "table row", "cells": [{"type": "table cell", "content": "H"}, {"type": "table cell", "content": "V"}]}]},
            {"type": "caption", "page number": 1, "bounding box": [50, 610, 400, 625], "content": "표 5-2 모델 및 특징"},
            {"type": "image", "page number": 1, "bounding box": [50, 100, 400, 300], "id": "i1"},
            {"type": "caption", "page number": 1, "bounding box": [50, 90, 400, 98], "content": "Figure 12 Diagram of the task"},
        ],
    }
    page = parse_document(data).pages[0]
    table = page.tables[0]
    assert table.label == "표 5-2" and table.caption is not None and "모델" in table.caption
    figure = page.images[0]
    assert figure.label == "Figure 12" and figure.kind == "figure" and "Diagram" in (figure.caption or "")


def test_paragraphs_preserved_with_kind_and_bbox():
    data = {
        "number of pages": 1,
        "kids": [
            {"type": "heading", "page number": 1, "bounding box": [10, 700, 400, 720], "content": "Title"},
            {"type": "paragraph", "page number": 1, "bounding box": [10, 650, 400, 690], "content": "Body text."},
        ],
    }
    page = parse_document(data).pages[0]
    assert len(page.paragraphs) == 2
    assert page.paragraphs[0].kind == "heading" and page.paragraphs[0].text == "Title"
    assert page.paragraphs[0].bbox == (10.0, 700.0, 400.0, 720.0)
    assert page.paragraphs[1].kind == "paragraph" and page.paragraphs[1].text == "Body text."


def test_extract_caption_labels_from_vlm_markdown():
    md = "# Title\n\nSome prose.\n\nFigure 12: Diagram of the task\n\n표 5-2 모델 및 특징\n\nAs shown in Figure 3 the result holds."
    labels = extract_caption_labels(md)
    pairs = {(lbl["kind"], lbl["label"]) for lbl in labels}
    assert ("figure", "Figure 12") in pairs       # caption line leading with the label
    assert ("table", "표 5-2") in pairs
    assert all(lbl["label"] != "Figure 3" for lbl in labels)  # inline mention is not a caption


def test_substantial_tables_drops_degenerate_slivers():
    real = OdlTable(0, 2, 2, (50, 50, 400, 200), (("A", "1"), ("B", "2")))
    sliver = OdlTable(0, 2, 2, (10.0, 10.0, 10.5, 10.2), (("", ""), ("", "")))  # 0x0pt, empty
    page = OdlPage(0, "", (real, sliver), ())
    assert substantial_tables(page) == [real]


def test_extract_uses_injected_runner():
    doc = extract("ignored.pdf", runner=lambda _p: _SYNTH)
    assert doc.n_pages == 2 and doc.pages[0].tables[0].cells[0] == ("A", "1")


def _bordered_table_pdf(path) -> str:
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    data = [["H1", "H2", "H3"], ["a", "1", "x"], ["b", "2", "y"], ["c", "3", "z"]]
    table = Table(data)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))
    doc.build([table])
    return str(path)


def test_extract_real_odl_detects_bordered_table(tmp_path):
    # integration: real ODL (Java 17) on a drawn bordered table -> one substantial table
    doc = extract(_bordered_table_pdf(tmp_path / "t.pdf"))
    subst = [t for p in doc.pages for t in substantial_tables(p)]
    assert len(subst) >= 1
    flat = " ".join(c for t in subst for row in t.cells for c in row)
    assert "H1" in flat and "a" in flat
