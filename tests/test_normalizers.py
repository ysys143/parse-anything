from __future__ import annotations

import pytest

from parse_anything.ir import ProviderName
from parse_anything.normalizers import (
    decode_json_body,
    extract_gemini_text,
    normalize_deterministic,
    normalize_gemini,
    normalize_paddle,
    normalize_transcription_markdown,
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


def test_extract_gemini_text_anchors_on_candidate_part_over_stray_text():
    # Given a stray 'text' field (e.g. citation metadata) before the real content part.
    payload = {
        "promptFeedback": {"text": "stray citation text"},
        "candidates": [{"content": {"parts": [{"text": "the real answer"}]}}],
    }

    # When / Then: the model output is returned, not the stray field.
    assert extract_gemini_text(payload) == "the real answer"


def test_extract_gemini_text_returns_none_for_safety_blocked_response():
    # Given a blocked response with no candidate part but a stray 'text' elsewhere.
    payload = {"promptFeedback": {"safetyRatings": [{"text": "blocked stray text"}]}}

    # When / Then: no model output -> None (caller fails the page), not the stray text.
    assert extract_gemini_text(payload) is None


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


def test_normalize_transcription_markdown_strips_grounding_tokens_and_maps_picture():
    page = normalize_transcription_markdown(
        "<x_0.334><y_0.1469>**Header**<class_Page-header>\n\n"
        "<class_Picture>\n\n"
        "<x_0.1><y_0.2>body<class_Text>"
    )

    assert "<x_" not in page
    assert "<y_" not in page
    assert "<class_" not in page
    assert "**Header**" in page
    assert "[figure]" in page
    assert "body" in page


def test_normalize_transcription_markdown_drops_ref_det_and_frontmatter():
    page = normalize_transcription_markdown(
        "is_diagram: False\nmodel: olmocr\n\n"
        "Body text\n\n"
        "<|ref|>text<|/ref|><|det|>[[25, 0, 960, 95]]<|/det|>"
    )

    assert "is_diagram:" not in page
    assert "model:" not in page
    assert "<|ref|>" not in page
    assert "<|det|>" not in page
    assert "Body text" in page


def test_normalize_transcription_markdown_converts_html_layout_blocks():
    page = normalize_transcription_markdown(
        '<div data-bbox="22 0 960 93" data-label="Text"><p>Hello <math>x</math></p></div>'
        '<div data-bbox="10 10 50 50" data-label="Figure"><img src="fig.png"></div>'
    )

    assert "<div" not in page
    assert "data-bbox" not in page
    assert "Hello" in page
    assert "x" in page
    assert "[figure]" in page


def test_normalize_transcription_markdown_keeps_clean_markdown():
    markdown = "# Heading\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\n[figure]"

    assert normalize_transcription_markdown(markdown) == markdown
