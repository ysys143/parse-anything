from __future__ import annotations

import json

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from odl_vl.pipeline.assemble import _recurring_numbers, assemble_document
from odl_vl.providers import HttpResponse


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def send(self, request):
        return self.responses.pop(0)


def _gemini_ok(text: str) -> HttpResponse:
    return HttpResponse(status_code=200, body=json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode("utf-8"))


def _pdf(path, line: str) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, line)
    c.showPage()
    c.save()
    return str(path)


def _blank_pdf(path) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)  # no text -> empty text layer (scan-like)
    c.showPage()
    c.save()
    return str(path)


def test_det_vlm_scan_double_pass_flags_disagreements(tmp_path):
    pdf = _blank_pdf(tmp_path / "scan.pdf")
    client = _FakeClient([_gemini_ok("recovered value 12345 here")])
    second = lambda _png: "recovered value 99999 here"  # disagreeing second provider  # noqa: E731
    res = assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", second_pass=second,
                            odl_runner=lambda _p: {"number of pages": 1, "kids": []})
    flags = res.pages[0].flags
    assert "dual_pass_disagree:12345" in flags and "dual_pass_disagree:99999" in flags


def test_det_vlm_no_double_pass_on_born_digital(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "value 12345")  # has a text layer -> oracle exists, no double-pass
    client = _FakeClient([_gemini_ok("value 12345")])
    called = []
    second = lambda _png: called.append(1) or "value 99999"  # noqa: E731
    assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", second_pass=second,
                      odl_runner=lambda _p: {"number of pages": 1, "kids": []})
    assert called == []   # born-digital -> second provider not invoked


class _CaptureClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def test_det_vlm_grounding_default_injects_deterministic_text(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "authoritative value 1,234,567")
    client = _CaptureClient([_gemini_ok("ok")])
    odl = {"number of pages": 1, "kids": [{"type": "paragraph", "page number": 1, "content": "Title"}]}
    assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", odl_runner=lambda _p: odl)
    body = client.requests[0].body.decode("utf-8")
    assert "1,234,567" in body and "NEVER alter a number" in body   # grounding on by default


def test_det_vlm_no_ground_option_is_image_only(tmp_path):
    from odl_vl.pipeline.assemble import DetVlmOptions

    pdf = _pdf(tmp_path / "d.pdf", "authoritative value 1,234,567")
    client = _CaptureClient([_gemini_ok("ok")])
    assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", options=DetVlmOptions(ground=False),
                      odl_runner=lambda _p: {"number of pages": 1, "kids": []})
    body = client.requests[0].body.decode("utf-8")
    assert "NEVER alter a number" not in body   # --no-ground -> no grounding block


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


def test_det_vlm_mode_uses_vlm_and_gates_numbers(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "authoritative value 1,234,567")  # pypdfium2 source
    odl_json = {"number of pages": 1, "kids": [{"type": "paragraph", "page number": 1, "content": "text"}]}
    client = _FakeClient([_gemini_ok("Value 1,234,567 and fabricated 9,999,999")])
    res = assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", odl_runner=lambda _p: odl_json)
    page = res.pages[0]
    assert page.route == "det_vlm" and page.used_vlm is True
    assert page.markdown == "Value 1,234,567 and fabricated 9,999,999"   # VLM is the output
    assert "unsourced_number:9999999" in page.flags                       # value oracle (pypdfium2) gates VLM
    assert "unsourced_number:1234567" not in page.flags


def test_det_vlm_without_client_degrades_to_deterministic(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "page text")
    odl_json = {"number of pages": 1, "kids": [{"type": "paragraph", "page number": 1, "content": "odl clean text"}]}
    res = assemble_document(pdf, mode="det_vlm", vlm_client=None, odl_runner=lambda _p: odl_json)
    page = res.pages[0]
    assert page.used_vlm is False and "vlm_unavailable" in page.flags
    assert "odl clean text" in page.markdown   # degrades to deterministic (ODL text), never dropped


def test_det_vlm_illegible_scan_abstains(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "page")
    client = _FakeClient([_gemini_ok("IMAGE_TOO_LOW_QUALITY")])
    res = assemble_document(pdf, mode="det_vlm", vlm_client=client, api_key="k", odl_runner=lambda _p: {"number of pages": 1, "kids": []})
    page = res.pages[0]
    assert page.markdown == "" and "illegible_low_quality" in page.flags
