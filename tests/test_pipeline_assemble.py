from __future__ import annotations

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from odl_vl.pipeline.assemble import _recurring_numbers, assemble_document


def _pdf(path, line: str) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, line)
    c.showPage()
    c.save()
    return str(path)


def test_recurring_numbers_excludes_header_like():
    texts = ["report 200 page one", "report 200 page two", "report 200 has 40 here"]
    rec = _recurring_numbers(texts)
    assert "200" in rec      # on every page -> running header
    assert "40" not in rec   # one page -> potential real data


def test_deterministic_mode_uses_odl_text_and_flags_dropped_numbers(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "Spec A100 40GB value 12345")
    odl_json = {  # ODL clean text dropped 40 and 12345 (kept A100 -> 100)
        "number of pages": 1,
        "kids": [{"type": "paragraph", "page number": 1, "content": "Spec A100 GB value"}],
    }
    res = assemble_document(pdf, mode="deterministic", odl_runner=lambda _p: odl_json)
    page = res.pages[0]
    assert page.route == "deterministic" and page.used_vlm is False
    assert "Spec A100 GB value" in page.markdown          # ODL clean text is the output
    assert "odl_dropped_number:40" in page.flags          # pypdfium2 completeness backstop (F17)
    assert "odl_dropped_number:12345" in page.flags


def test_deterministic_mode_renders_odl_tables(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "page")
    odl_json = {
        "number of pages": 1,
        "kids": [{
            "type": "table", "page number": 1, "bounding box": [50, 50, 400, 200],
            "number of rows": 2, "number of columns": 2,
            "rows": [
                {"type": "table row", "cells": [{"type": "table cell", "content": "H"}, {"type": "table cell", "content": "V"}]},
                {"type": "table row", "cells": [{"type": "table cell", "content": "a"}, {"type": "table cell", "content": "1"}]},
            ],
        }],
    }
    md = assemble_document(pdf, mode="deterministic", odl_runner=lambda _p: odl_json).pages[0].markdown
    assert "| H | V |" in md and "| a | 1 |" in md


def test_det_vlm_mode_not_yet_implemented(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "page")
    with pytest.raises(NotImplementedError):
        assemble_document(pdf, mode="det_vlm", odl_runner=lambda _p: {"number of pages": 1, "kids": []})
