from __future__ import annotations

import json

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from odl_vl.pipeline.run import DocumentResult, run_document
from odl_vl.providers import HttpResponse


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def send(self, request):
        return self.responses.pop(0)


def _gemini_ok(text: str) -> HttpResponse:
    return HttpResponse(status_code=200, body=json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode("utf-8"))


def _pdf(path, line: str = "hello world") -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, line)
    c.showPage()
    c.save()
    return str(path)


_ODL = {"number of pages": 1, "kids": [{"type": "paragraph", "page number": 1, "content": "odl clean text"}]}


def test_run_document_deterministic_delegates_to_assemble(tmp_path):
    # run_document is a thin mode-driven adapter over assemble (no runtime routing).
    res = run_document(_pdf(tmp_path / "d.pdf"), mode="deterministic", odl_runner=lambda _p: _ODL)
    assert isinstance(res, DocumentResult)
    assert res.pages[0].route == "deterministic" and res.pages[0].used_vlm is False
    assert "odl clean text" in res.pages[0].markdown


def test_run_document_det_vlm_uses_injected_client(tmp_path):
    client = _FakeClient([_gemini_ok("# From VLM")])
    res = run_document(_pdf(tmp_path / "d.pdf"), mode="det_vlm", vlm_client=client, api_key="k", odl_runner=lambda _p: _ODL)
    assert res.pages[0].route == "det_vlm" and res.pages[0].used_vlm is True
    assert res.pages[0].markdown == "# From VLM"


def test_ledger_shape(tmp_path):
    rows = run_document(_pdf(tmp_path / "d.pdf"), mode="deterministic", odl_runner=lambda _p: _ODL).ledger()
    assert rows[0].keys() >= {"page_index", "route", "used_vlm", "markdown_chars", "flags", "latency_ms"}
    assert rows[0]["route"] == "deterministic"
