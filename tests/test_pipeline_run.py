from __future__ import annotations

import json

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from odl_vl.pipeline.run import run_document
from odl_vl.pipeline.triage import PageSignals
from odl_vl.providers import HttpResponse


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def send(self, request):
        return self.responses.pop(0)


def _gemini_ok(text: str) -> HttpResponse:
    body = json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode("utf-8")
    return HttpResponse(status_code=200, body=body)


def _text_pdf(path) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, "Quarterly notes -- plain prose paragraph text.")
    c.showPage()
    c.save()
    return str(path)


def test_text_only_page_runs_deterministic_without_vlm(tmp_path):
    res = run_document(_text_pdf(tmp_path / "d.pdf"))
    assert res.pages[0].route == "deterministic"
    assert res.pages[0].used_vlm is False
    assert "prose" in res.pages[0].markdown
    ledger = res.ledger()
    assert len(ledger) == 1
    assert ledger[0]["used_vlm"] is False and ledger[0]["flags"] == []


def test_table_route_uses_injected_vlm_client(tmp_path):
    client = _FakeClient([_gemini_ok("# From VLM")])
    res = run_document(
        _text_pdf(tmp_path / "d.pdf"),
        vlm_client=client,
        api_key="k",
        signals=[PageSignals(text_chars=100, table_rows=29, image_count=0)],
    )
    assert res.pages[0].route == "oracle_vlm"
    assert res.pages[0].used_vlm is True
    assert res.pages[0].markdown == "# From VLM"


def test_vlm_route_without_client_flags_and_degrades_to_text(tmp_path):
    res = run_document(
        _text_pdf(tmp_path / "d.pdf"),
        signals=[PageSignals(text_chars=100, table_rows=29, image_count=0)],
    )
    assert res.pages[0].used_vlm is False
    assert "vlm_unavailable" in res.pages[0].flags
    assert len(res.pages[0].markdown) > 0  # degraded to the deterministic text layer
