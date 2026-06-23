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


def test_low_quality_input_flag_is_threshold_driven(tmp_path):
    pdf = _text_pdf(tmp_path / "d.pdf")
    sig = [PageSignals(text_chars=0, table_rows=0, image_count=1)]
    # threshold so high that any render counts as low quality -> flag fires
    hi = run_document(pdf, vlm_client=_FakeClient([_gemini_ok("ok")]), api_key="k", signals=sig, min_input_quality=1e12)
    assert "low_quality_input" in hi.pages[0].flags
    # threshold 0 -> never low quality
    lo = run_document(pdf, vlm_client=_FakeClient([_gemini_ok("ok")]), api_key="k", signals=sig, min_input_quality=0.0)
    assert "low_quality_input" not in lo.pages[0].flags


def _spanning_table_pdf(path) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    cols = [72, 180, 300, 420]
    rows_a = [[f"A{i}", f"B{i}", f"C{i}", f"D{i}"] for i in range(1, 5)]
    rows_b = [[f"A{i}", f"B{i}", f"C{i}", f"D{i}"] for i in range(5, 9)]
    y = 300  # bottom region of page 1
    for row in rows_a:
        for x, cell in zip(cols, row):
            c.drawString(x, y, cell)
        y -= 28
    c.showPage()
    y = 700  # top region of page 2, same columns -> continuation
    for row in rows_b:
        for x, cell in zip(cols, row):
            c.drawString(x, y, cell)
        y -= 28
    c.showPage()
    c.save()
    return str(path)


def test_scan_legibility_gate_abstains_on_low_quality(tmp_path):
    # F6: a scan the model judges illegible -> abstain (empty + flag), not a fabricated read.
    client = _FakeClient([_gemini_ok("IMAGE_TOO_LOW_QUALITY")])
    res = run_document(
        _text_pdf(tmp_path / "d.pdf"),
        vlm_client=client,
        api_key="k",
        signals=[PageSignals(text_chars=0, table_rows=0, image_count=1)],
    )
    assert res.pages[0].route == "scan_vlm"
    assert res.pages[0].markdown == ""
    assert "illegible_low_quality" in res.pages[0].flags


def test_scan_legible_page_is_transcribed(tmp_path):
    client = _FakeClient([_gemini_ok("# Scanned content")])
    res = run_document(
        _text_pdf(tmp_path / "d.pdf"),
        vlm_client=client,
        api_key="k",
        signals=[PageSignals(text_chars=0, table_rows=0, image_count=1)],
    )
    assert res.pages[0].markdown == "# Scanned content"
    assert "illegible_low_quality" not in res.pages[0].flags


def test_continuation_pages_batched_into_one_multi_image_call(tmp_path):
    pdf = _spanning_table_pdf(tmp_path / "span.pdf")
    client = _FakeClient([_gemini_ok("MERGED SPANNING TABLE")])  # exactly ONE response available
    res = run_document(
        pdf,
        vlm_client=client,
        api_key="k",
        signals=[PageSignals(text_chars=100, table_rows=29, image_count=0)] * 2,
    )
    assert len(res.pages) == 2
    # single multi-image call merged into the start page (a second call would exhaust the fake)
    assert res.pages[0].markdown == "MERGED SPANNING TABLE"
    assert "spanning_table:0-1" in res.pages[0].flags
    assert res.pages[1].route == "folded"
    assert "folded_into:0" in res.pages[1].flags
