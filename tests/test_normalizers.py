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


def test_normalize_paddle_cleans_plain_string_markdown():
    result = {
        "layoutParsingResults": [
            {
                "markdown": (
                    "CorrectiveFeedbackCSNL\n\n"
                    "## PLOS BIOLOGY\n\n"
                    "## 6\n\n"
                    "## figure\n\n"
                    "This figure depicts an experimental timeline with fixation and feedback.\n\n"
                    "figure benefits of transparency in the peer review process; therefore, metadata follows. "
                    "Copyright: © 2023 Lee et al. Data Availability Statement: Raw data are available.\n\n"
                    "## Introduction\n\n"
                    "Perceptual decision-making means committing to a proposition about an objective world state.\n\n"
                    "### Introduction\n\n"
                    "Perceptual decision-making means committing to a proposition about an objective world state.\n\n"
                    "11. 2017年1月1日Introduction Perceptual decision-making means committing to a proposition "
                    "about an objective world state.\n\n"
                    "Copyright: © 2023 Lee et al.\n\n"
                    "Data Availability Statement: Raw data are available at https://doi.\n\n"
                    "org/10.5281/zenodo.8427373)."
                )
            }
        ]
    }

    # When
    page = normalize_paddle(result)

    # Then
    assert "CorrectiveFeedbackCSNL" not in page.markdown
    assert "PLOS BIOLOGY" not in page.markdown
    assert "## 6" not in page.markdown
    assert "## figure" not in page.markdown
    assert "This figure depicts" not in page.markdown
    assert "benefits of transparency" not in page.markdown
    assert "2017年1月1日Introduction" not in page.markdown
    assert page.markdown.count("Introduction") == 1
    assert page.markdown.count("Perceptual decision-making means") == 1
    assert "Copyright:" not in page.markdown
    assert "Data Availability Statement:" not in page.markdown
    assert "org/10.5281/zenodo" not in page.markdown


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


def test_normalize_transcription_markdown_drops_unresolved_local_image_refs():
    page = normalize_transcription_markdown(
        "Before\n\n"
        "![Diagram showing a generated crop](page_613_1042_1012_388.png)\n\n"
        "![real crop](assets/p4_1.png)\n\n"
        "After"
    )

    assert "page_613_1042_1012_388.png" not in page
    assert "![Diagram showing a generated crop]" not in page
    assert "![real crop](assets/p4_1.png)" in page
    assert "Before" in page and "After" in page


def test_normalize_transcription_markdown_drops_standalone_det_line():
    page = normalize_transcription_markdown("Body\n\n<|det|>image [800\n\nNext <|ref|>anchor")

    assert "<|det|>" not in page
    assert "<|ref|>" not in page
    assert "image [800" not in page
    assert "Body" in page
    assert "Next anchor" in page


def test_normalize_transcription_markdown_strips_plos_running_furniture():
    page = normalize_transcription_markdown(
        "PLOS BIOLOGY | Corrective feedback on perceptual decisions body starts here\n"
        "PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 7 / 32\n"
        "# 7 / 32\n"
        "<page_number>8 / 32</page_number>\n"
        "Body continues"
    )

    assert "PLOS BIOLOGY" not in page
    assert "PLOS Biology | https://doi.org" not in page
    assert "7 / 32" not in page
    assert "8 / 32" not in page
    assert "body starts here" in page
    assert "Body continues" in page


def test_normalize_transcription_markdown_strips_furniture_after_vendor_markup():
    page = normalize_transcription_markdown(
        '<div data-bbox="1 2 3 4" data-label="Page-Header">'
        "PLOS BIOLOGY _____ Corrective feedback on perceptual decisions"
        "</div>"
        '<div data-bbox="1 2 3 4" data-label="Text"><p>Body starts.</p></div>'
        "<x_0.1543><y_0.4555>"
        "PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 1 / 32"
        "<x_0.7051><y_0.4672><class_Page-footer>"
    )

    assert "PLOS BIOLOGY" not in page
    assert "PLOS Biology | https://doi.org" not in page
    assert "1 / 32" not in page
    assert "Body starts." in page


def test_normalize_transcription_markdown_strips_split_plos_furniture():
    page = normalize_transcription_markdown(
        "PLOS BIOLOGY\n"
        "Corrective feedback on perceptual decisions Here, we tested the feedback computations.\n"
        "Corrective feedback on perceptual decisions PLOS Biology | "
        "https://doi.org/10.1371/journal.pbio.3002373\n"
        "November 8, 2023 32 / 32\n"
        "32 / 32 figure\n"
        "Final paragraph."
    )

    assert "PLOS BIOLOGY" not in page
    assert "Corrective feedback on perceptual decisions" not in page
    assert "https://doi.org/10.1371/journal.pbio.3002373" not in page
    assert "32 / 32" not in page
    assert "Here, we tested the feedback computations." in page
    assert "Final paragraph." in page


def test_normalize_transcription_markdown_strips_orphan_plos_footer_stem():
    page = normalize_transcription_markdown("Body\nPLOS Biology |<br>\nNext")

    assert "PLOS Biology" not in page
    assert "Body" in page
    assert "Next" in page


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


def test_normalize_transcription_markdown_dedupes_scan_page_repeats():
    markdown = (
        "## Introduction\n\n"
        "Perceptual decision-making (PDM) means committing to a proposition about an objective world state. "
        "Decision-makers adjust future commitments based on past commitments.\n\n"
        "### Introduction\n\n"
        "Perceptual decision-making (PDM) means committing to a proposition about an objective world state. "
        "Decision-makers adjust future commitments based on past commitments."
    )

    page = normalize_transcription_markdown(markdown)

    assert page.count("Introduction") == 1
    assert page.count("Perceptual decision-making") == 1
