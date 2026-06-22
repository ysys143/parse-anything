from __future__ import annotations

import json

import pytest

from odl_vl.orchestrator_input import (
    DocumentInput,
    PageInput,
    load_document_input,
    parse_document_input,
)


def _valid_payload() -> dict:
    return {
        "document_id": "doc-1",
        "pages": [
            {
                "page_id": "p1",
                "page_index": 0,
                "first_pass_md": "# Title",
                "page_image": "fixtures://simple/page-0.png",
                "fixture_family": "simple_text",
            },
            {
                "page_id": "p2",
                "page_index": 1,
                "first_pass_md": "",
                "page_image": "fixtures://chart/page-0.png",
                "fixture_family": "chart_like_page",
                "intent_prompt": "Describe the chart",
                "needs_image_description": True,
                "has_text_layer": False,
            },
        ],
    }


def test_parse_document_input_returns_pages_with_defaults():
    # Given
    payload = _valid_payload()

    # When
    document = parse_document_input(payload)

    # Then
    assert isinstance(document, DocumentInput)
    assert document.document_id == "doc-1"
    assert len(document.pages) == 2
    first, second = document.pages
    assert isinstance(first, PageInput)
    assert first.has_text_layer is True
    assert first.needs_image_description is False
    assert second.intent_prompt == "Describe the chart"
    assert second.needs_image_description is True
    assert second.has_text_layer is False


def test_routing_task_maps_page_hints():
    # Given
    document = parse_document_input(_valid_payload())

    # When
    task = document.pages[1].routing_task()

    # Then
    assert task.fixture_family == "chart_like_page"
    assert task.needs_image_description is True
    assert task.has_text_layer is False


def test_load_document_input_reads_json_file(tmp_path):
    # Given
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(_valid_payload()), encoding="utf-8")

    # When
    document = load_document_input(path)

    # Then
    assert document.document_id == "doc-1"
    assert [page.fixture_family for page in document.pages] == ["simple_text", "chart_like_page"]


def test_malformed_json_raises_value_error(tmp_path):
    # Given
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    # When / Then
    with pytest.raises(ValueError, match="not valid JSON"):
        load_document_input(path)


def test_missing_required_field_raises_value_error():
    # Given
    payload = _valid_payload()
    del payload["pages"][0]["page_image"]

    # When / Then
    with pytest.raises(ValueError, match="missing required field 'page_image'"):
        parse_document_input(payload)


def test_non_integer_page_index_raises_value_error():
    # Given
    payload = _valid_payload()
    payload["pages"][0]["page_index"] = "0"

    # When / Then
    with pytest.raises(ValueError, match="page_index"):
        parse_document_input(payload)


def test_empty_pages_list_raises_value_error():
    # Given
    payload = {"document_id": "doc", "pages": []}

    # When / Then
    with pytest.raises(ValueError, match="non-empty 'pages'"):
        parse_document_input(payload)
