"""B-4 det-aug unit tests: grounding pre-hook and value-oracle guard post-hook.

Offline: a synthetic ODL runner avoids Java; reportlab makes a tiny PDF with known numbers so
the value oracle has a real text layer to gate against.
"""
from __future__ import annotations

import io

import pytest

from odl_vl_track_b.det_aug import make_grounding_hook, make_guard_hook

# Minimal ODL JSON the synthetic runner returns (2 pages, one heading each).
_ODL_JSON = {
    "number of pages": 1,
    "kids": [
        {"type": "heading", "page number": 1, "content": "Quarterly Revenue Report",
         "bounding box": [72, 700, 400, 720], "id": 1},
    ],
}


def _make_pdf() -> bytes:
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(72, 720, "Quarterly Revenue Report")
    c.drawString(72, 690, "North 12345 total 35801")
    c.showPage()
    c.save()
    return buf.getvalue()


def _write_pdf(tmp_path, data: bytes) -> str:
    p = tmp_path / "doc.pdf"
    p.write_bytes(data)
    return str(p)


def test_grounding_hook_injects_text_and_structure(tmp_path) -> None:
    pdf = _write_pdf(tmp_path, _make_pdf())
    hook = make_grounding_hook(use_odl=True, runner=lambda _p: _ODL_JSON)
    prompt, flags = hook(pdf, 0, b"", "BASE PROMPT")
    assert "BASE PROMPT" in prompt
    assert "DETERMINISTIC GROUNDING" in prompt
    assert "12345" in prompt  # pypdfium2 value authority injected verbatim
    assert "Quarterly Revenue Report" in prompt  # ODL structure outline
    assert flags == ()


def test_grounding_hook_soft_fails_without_odl(tmp_path) -> None:
    pdf = _write_pdf(tmp_path, _make_pdf())

    def boom(_p: str) -> dict:
        raise RuntimeError("java_down")

    hook = make_grounding_hook(use_odl=True, runner=boom)
    prompt, _ = hook(pdf, 0, b"", "BASE")
    # ODL parse failed -> still grounds on pypdfium2 text (no crash)
    assert "12345" in prompt
    assert "BASE" in prompt


def test_grounding_hook_caches_odl_parse(tmp_path) -> None:
    pdf = _write_pdf(tmp_path, _make_pdf())
    calls = {"n": 0}

    def counting_runner(_p: str) -> dict:
        calls["n"] += 1
        return _ODL_JSON

    hook = make_grounding_hook(use_odl=True, runner=counting_runner)
    hook(pdf, 0, b"", "BASE")
    hook(pdf, 0, b"", "BASE")
    assert calls["n"] == 1  # parsed once, cached per PDF path


def test_guard_hook_flags_unsourced_number(tmp_path) -> None:
    pdf = _write_pdf(tmp_path, _make_pdf())
    hook = make_guard_hook(min_value=100)
    # 35801 is in the text layer (sourced); 99999 is fabricated (unsourced).
    flags = hook(pdf, 0, "Revenue was 35801 but forecast 99999")
    assert "unsourced_number:99999" in flags
    assert "unsourced_number:35801" not in flags


def test_guard_hook_clean_when_all_sourced(tmp_path) -> None:
    pdf = _write_pdf(tmp_path, _make_pdf())
    hook = make_guard_hook(min_value=100)
    flags = hook(pdf, 0, "North 12345 total 35801")
    assert flags == ()
