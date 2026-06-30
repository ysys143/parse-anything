"""B-1/B-2 unit tests: monkeypatch installs and converter construction.

Requires docling (skipped otherwise). Building the converter is offline for B-1 (remote VLM, no
local model) and for B-2 with OCR disabled (no OCR model download). No network call is made --
converters are constructed, not run.
"""
from __future__ import annotations

import pytest

from odl_vl_track_b import backend_docling as bd

_OFFICIAL_KWARGS = dict(
    force_full_page_ocr=False, disable_ocr=True, ocr_engine="easyocr", psm=None,
    ocr_lang=None, enrich_formula=False, enrich_picture_description=True,
    picture_description_prompt=None, device="auto",
)


def test_b1_default_model_tracks_repo() -> None:
    from odl_vl.providers import DEFAULT_GEMINI_MODEL

    assert bd.DEFAULT_MODEL == DEFAULT_GEMINI_MODEL  # no stale hardcoded model id


def test_install_b1_patches_and_builds() -> None:
    pytest.importorskip("docling")
    from docling.document_converter import DocumentConverter

    hs = bd.install_b1("FAKE_KEY", model="m")
    assert hs.create_converter.__module__ == "odl_vl_track_b.backend_docling"
    conv = hs.create_converter(**_OFFICIAL_KWARGS)
    assert isinstance(conv, DocumentConverter)


def test_install_b2_patches_and_builds() -> None:
    pytest.importorskip("docling")
    from docling.document_converter import DocumentConverter

    hs = bd.install_b2("FAKE_KEY", model="m")
    assert hs.create_converter.__module__ == "odl_vl_track_b.backend_docling"
    conv = hs.create_converter(disable_ocr=True, picture_description_prompt=None)
    assert isinstance(conv, DocumentConverter)


def test_b1_vlm_options_point_at_gemini() -> None:
    # The B-1 converter factory must wire the Gemini OpenAI-compatible endpoint + bearer auth.
    assert bd.GEMINI_OPENAI_URL.endswith("/openai/chat/completions")
    assert bd._gemini_headers("K") == {"Authorization": "Bearer K"}
