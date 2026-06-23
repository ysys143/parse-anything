from __future__ import annotations

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from odl_vl.pipeline.docmeta import build_meta, document_id


def _pdf(path, line: str) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, line)
    c.showPage()
    c.save()
    return str(path)


def test_document_id_is_deterministic_content_hash(tmp_path):
    # The id is a hash of the exact PDF *bytes*: re-processing the same file is idempotent
    # (same id/folder), and a different file gets a different id.
    a = _pdf(tmp_path / "a.pdf", "content one")
    c = _pdf(tmp_path / "c.pdf", "content two")
    short_a, full_a = document_id(a)
    assert len(short_a) == 16 and full_a.startswith(short_a)
    assert document_id(a)[0] == short_a            # same file re-hashed -> same id (idempotent)
    assert document_id(c)[0] != short_a            # different file -> different id


def test_build_meta_captures_provenance(tmp_path):
    pdf = _pdf(tmp_path / "doc.pdf", "hello")
    meta = build_meta(pdf, source_id="csnl", external_id="ext-9", mode="deterministic", n_pages=1)
    assert meta.document_id == document_id(pdf)[0]
    assert meta.original_filename == "doc.pdf"
    assert meta.source_id == "csnl" and meta.external_id == "ext-9"
    assert meta.mode == "deterministic" and meta.n_pages == 1
    d = meta.to_dict()
    assert d["source"] == {"source_id": "csnl", "ingested_from": pdf}
    assert d["external_id"] == "ext-9" and isinstance(d["producer"], dict)
    assert d["diagnostic"]["tier"] == "cli"
