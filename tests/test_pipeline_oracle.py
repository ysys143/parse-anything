from __future__ import annotations

import json

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from odl_vl.pipeline.oracle import fabrication_flags
from odl_vl.pipeline.run import run_document
from odl_vl.providers import HttpResponse


def test_fabrication_flags_flags_only_unsourced_numbers():
    md = "| item | 1,234,567 | 9,999,999 |"
    assert fabrication_flags(md, ["1234567"]) == ["9999999"]


def test_fabrication_flags_min_value_skips_small_noise():
    md = "page 12 total 1,234,567"
    # "12" is below the threshold (page-number noise); only the substantial number is gated.
    assert fabrication_flags(md, ["1234567"], min_value=1000) == []
    assert fabrication_flags(md, [], min_value=1000) == ["1234567"]


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def send(self, request):
        return self.responses.pop(0)


def _gemini_ok(text: str) -> HttpResponse:
    return HttpResponse(status_code=200, body=json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode("utf-8"))


def _text_pdf(path, line: str) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, line)
    c.showPage()
    c.save()
    return str(path)


def test_run_flags_vlm_number_absent_from_text_layer(tmp_path):
    # det_vlm mode: the PDF text layer (value oracle) holds 1,234,567; the VLM also emits a
    # bogus 9,999,999 which the pypdfium2 value oracle flags.
    pdf = _text_pdf(tmp_path / "d.pdf", "authoritative value 1,234,567")
    client = _FakeClient([_gemini_ok("Value 1,234,567 and fabricated 9,999,999")])
    res = run_document(
        pdf, mode="det_vlm", vlm_client=client, api_key="k", odl_runner=lambda _p: {"number of pages": 1, "kids": []}
    )
    flags = res.pages[0].flags
    assert "unsourced_number:9999999" in flags
    assert "unsourced_number:1234567" not in flags  # grounded value is not flagged
