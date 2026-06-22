from __future__ import annotations

import pytest

from odl_vl.ir import ProviderName
from odl_vl.normalizers import (
    decode_json_body,
    extract_gemini_text,
    normalize_deterministic,
    normalize_gemini,
    normalize_paddle,
)


def test_normalize_deterministic_keeps_markdown_and_provider():
    # When
    page = normalize_deterministic("# Heading\n\nbody")

    # Then
    assert page.provider is ProviderName.DETERMINISTIC
    assert page.markdown == "# Heading\n\nbody"
    assert page.confidence is None


def test_normalize_gemini_sets_provider_and_image_description():
    # When
    page = normalize_gemini("  visual summary  ", image_description="a rising line chart")

    # Then
    assert page.provider is ProviderName.GEMINI
    assert page.markdown == "visual summary"
    assert page.image_description == "a rising line chart"


def test_extract_gemini_text_walks_response_payload():
    # Given
    payload = {"candidates": [{"content": {"parts": [{"text": "extracted body"}]}}]}

    # When / Then
    assert extract_gemini_text(payload) == "extracted body"


def test_normalize_paddle_parses_layout_results_and_confidence():
    # Given
    result = {
        "layoutParsingResults": [
            {"markdown": {"text": "## Table\n\n| a | b |", "images": {"img0": "x"}}, "confidence": 0.8},
            {"markdown": {"text": "footnote"}, "confidence": 0.6},
        ]
    }

    # When
    page = normalize_paddle(result)

    # Then
    assert page.provider is ProviderName.PADDLE
    assert "## Table" in page.markdown
    assert "footnote" in page.markdown
    assert page.confidence == pytest.approx(0.7)
    assert page.ledger_fields["paddle_image_count"] == 1


def test_normalize_paddle_accepts_markdown_as_plain_string():
    # Given a Paddle response whose markdown is a plain string, not a mapping.
    result = {"layoutParsingResults": [{"markdown": "## Plain string markdown"}]}

    # When
    page = normalize_paddle(result)

    # Then
    assert page.markdown == "## Plain string markdown"


def test_normalize_paddle_empty_result_returns_empty_markdown():
    # When
    page = normalize_paddle({"layoutParsingResults": []})

    # Then
    assert page.provider is ProviderName.PADDLE
    assert page.markdown == ""
    assert page.confidence is None


def test_normalize_paddle_non_mapping_is_defensive():
    # When
    page = normalize_paddle("not a dict")

    # Then
    assert page.markdown == ""


def test_decode_json_body_raises_on_malformed_provider_json():
    # When / Then
    with pytest.raises(ValueError, match="not valid JSON"):
        decode_json_body(b"{broken")
