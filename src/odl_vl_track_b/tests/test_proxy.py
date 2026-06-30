"""B-3 proxy unit tests: multipart parsing, DoclingDocument shaping, convert_pdf.

All offline: a fake transcriber stands in for the VLM, reportlab generates a tiny PDF (no
committed binaries, mirrors the repo's dev-dependency approach). No network, no keys.
"""
from __future__ import annotations

import io

import pytest

from odl_vl_track_b.docling_out import build_docling_document, sanitize_str, PageBlock
from odl_vl_track_b.proxy import _parse_range, convert_pdf, parse_multipart


def _make_pdf(n_pages: int = 2) -> bytes:
    reportlab = pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for i in range(n_pages):
        c.drawString(72, 720, f"Page {i + 1} value 12345")
        c.showPage()
    c.save()
    return buf.getvalue()


def _build_multipart(pdf_bytes: bytes, page_ranges: str | None, boundary: str = "testbnd") -> bytes:
    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="document.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("latin1")
    chunks = [head, pdf_bytes]
    if page_ranges is not None:
        chunks.append(
            (
                f"\r\n--{boundary}\r\n"
                'Content-Disposition: form-data; name="page_ranges"\r\n\r\n'
                f"{page_ranges}"
            ).encode("latin1")
        )
    chunks.append(f"\r\n--{boundary}--\r\n".encode("latin1"))
    return b"".join(chunks)


def test_parse_multipart_preserves_pdf_bytes() -> None:
    pdf = _make_pdf(1)
    body = _build_multipart(pdf, "1-1")
    fields = parse_multipart(body, "testbnd")
    assert fields["files"] == pdf  # byte-exact, no CRLF corruption
    assert fields["page_ranges"] == b"1-1"


def test_parse_multipart_pdf_ending_in_newline() -> None:
    # A PDF body that legitimately ends in \r\n must not be truncated by the framing strip.
    fake_pdf = b"%PDF-1.4 trailing\r\n"
    body = _build_multipart(fake_pdf, None)
    fields = parse_multipart(body, "testbnd")
    assert fields["files"] == fake_pdf
    assert "page_ranges" not in fields


def test_parse_range() -> None:
    assert _parse_range(None, 5) == (1, 5)
    assert _parse_range("2-4", 10) == (2, 4)
    assert _parse_range("3-99", 7) == (3, 7)  # clamped to total
    assert _parse_range("4", 10) == (4, 4)  # single page, no dash


def test_build_docling_document_shape() -> None:
    doc = build_docling_document([PageBlock(3, 595.0, 842.0, "# Title\nbody")])
    assert set(doc) == {"texts", "tables", "pictures", "pages"}
    (text,) = doc["texts"]
    assert text["label"] == "text"
    assert text["text"] == "# Title\nbody"
    prov = text["prov"][0]
    assert prov["page_no"] == 3
    assert prov["bbox"] == {"l": 0.0, "t": 842.0, "r": 595.0, "b": 0.0, "coord_origin": "BOTTOMLEFT"}
    assert doc["pages"]["3"]["page_dimensions"] == {"width": 595.0, "height": 842.0}


def test_sanitize_str() -> None:
    assert sanitize_str("a\x00b") == "a�b"
    assert sanitize_str("clean") == "clean"


def test_convert_pdf_success() -> None:
    pdf = _make_pdf(2)
    calls: list[str] = []

    def fake(png: bytes, prompt: str) -> str:
        assert png[:8] == b"\x89PNG\r\n\x1a\n"  # real rendered PNG
        calls.append(prompt)
        return "# Page\nvalue 12345"

    result = convert_pdf(pdf, "1-2", transcriber=fake)
    assert result["status"] == "success"
    assert result["failed_pages"] == []
    assert len(result["document"]["json_content"]["texts"]) == 2
    assert len(calls) == 2


def test_convert_pdf_partial_on_transcriber_error() -> None:
    pdf = _make_pdf(2)

    def flaky(png: bytes, prompt: str) -> str:
        if b"\x89PNG" in png[:8]:
            raise RuntimeError("vlm_boom")
        return "ok"

    result = convert_pdf(pdf, "1-2", transcriber=flaky)
    assert result["status"] == "failure"  # every page failed
    assert result["failed_pages"] == [1, 2]
    assert all(e.startswith("Page ") for e in result["errors"])


def test_convert_pdf_partial_mixed() -> None:
    pdf = _make_pdf(3)

    def second_fails(png: bytes, prompt: str) -> str:
        second_fails.n += 1  # type: ignore[attr-defined]
        if second_fails.n == 2:  # type: ignore[attr-defined]
            raise RuntimeError("boom")
        return "ok"

    second_fails.n = 0  # type: ignore[attr-defined]
    result = convert_pdf(pdf, "1-3", transcriber=second_fails)
    assert result["status"] == "partial_success"
    assert result["failed_pages"] == [2]
    assert len(result["document"]["json_content"]["texts"]) == 2
