from __future__ import annotations

import json

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from odl_vl.pipeline.diagnose import SourceDiagnosis, diagnose_source, prepare_bundle, sample_indices, token_divergence
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


def test_sample_indices_spread():
    assert sample_indices(1, 4) == [0]
    assert sample_indices(3, 4) == [0, 1, 2]
    idx = sample_indices(24, 4)
    assert idx[0] == 0 and idx[-1] == 23 and len(idx) == 4


def test_token_divergence():
    assert token_divergence("a b c", "a b c") == 0.0
    assert token_divergence("a b", "x y") == 1.0
    assert 0.0 < token_divergence("a b c d", "a b") < 1.0


def test_diagnose_born_digital_recommends_deterministic(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "alpha beta gamma delta epsilon zeta")
    client = _FakeClient([_gemini_ok("alpha beta gamma delta epsilon zeta")])  # faithful -> divergence 0
    odl = {"number of pages": 1, "kids": [{"type": "paragraph", "page number": 1, "content": "alpha beta"}]}
    diag = diagnose_source(pdf, vlm_client=client, api_key="k", sample_size=4, odl_runner=lambda _p: odl)
    assert isinstance(diag, SourceDiagnosis)
    assert diag.recommended_mode == "deterministic" and diag.scan_fraction == 0.0
    assert diag.mean_token_divergence == 0.0


def test_diagnose_structure_recommends_det_vlm(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "alpha beta gamma delta epsilon")
    client = _FakeClient([_gemini_ok("alpha beta gamma delta epsilon")])  # low divergence
    odl = {"number of pages": 1, "kids": [{
        "type": "table", "page number": 1, "bounding box": [50, 50, 400, 300], "number of rows": 1, "number of columns": 2,
        "rows": [{"type": "table row", "cells": [{"type": "table cell", "content": "H"}, {"type": "table cell", "content": "V"}]}],
    }]}
    diag = diagnose_source(pdf, vlm_client=client, api_key="k", odl_runner=lambda _p: odl)
    assert diag.recommended_mode == "det_vlm" and diag.pages_with_tables == 1


def test_diagnose_scan_recommends_det_vlm(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "x")  # near-empty text layer -> scan-like
    client = _FakeClient([_gemini_ok("recovered text from the scanned page image")])
    diag = diagnose_source(pdf, vlm_client=client, api_key="k", odl_runner=lambda _p: {"number of pages": 1, "kids": []})
    assert diag.recommended_mode == "det_vlm" and diag.scan_fraction == 1.0
    assert "scan" in diag.reasons[0]


def test_diagnose_requires_vlm_client(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "text")
    with pytest.raises(ValueError):
        diagnose_source(pdf, vlm_client=None)


def test_prepare_bundle_writes_review_material(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "alpha beta gamma")
    bundle = prepare_bundle(pdf, tmp_path / "bundle", sample_size=4, odl_runner=lambda _p: {"number of pages": 1, "kids": []})
    assert bundle["n_sampled"] == 1
    assert (tmp_path / "bundle" / "bundle.json").exists()
    assert (tmp_path / "bundle" / "pages" / "page-000.png").exists()
    sample = bundle["samples"][0]
    assert sample["deterministic_text"].strip() and "vlm_text" not in sample  # no client -> no VLM material


def test_prepare_bundle_includes_vlm_divergence_when_client_given(tmp_path):
    pdf = _pdf(tmp_path / "d.pdf", "alpha beta gamma")
    client = _FakeClient([_gemini_ok("alpha beta gamma delta")])
    bundle = prepare_bundle(pdf, tmp_path / "b", vlm_client=client, api_key="k", odl_runner=lambda _p: {"number of pages": 1, "kids": []})
    sample = bundle["samples"][0]
    assert sample["vlm_text"] == "alpha beta gamma delta" and "token_divergence" in sample
