from __future__ import annotations

import json

from odl_vl.ledger import LedgerEvent, append_ledger_event, event_payload


def test_event_payload_preserves_all_ledger_fields():
    # Given an event whose route_reason and metadata are non-secret operational data.
    event = LedgerEvent(
        provider="paddle",
        model_alias="PaddleOCR-VL-1.6",
        route_reason="hint:no_text_layer",
        latency_ms=125.5,
        status="ok",
        cost_estimate_usd=0.0025,
        metadata={"mode": "live", "family": "merged_table"},
    )

    # When
    payload = event_payload(event)

    # Then: every field is recorded faithfully (no scrubbing pass).
    assert payload["provider"] == "paddle"
    assert payload["model_alias"] == "PaddleOCR-VL-1.6"
    assert payload["route_reason"] == "hint:no_text_layer"
    assert payload["latency_ms"] == 125.5
    assert payload["status"] == "ok"
    assert payload["cost_estimate_usd"] == 0.0025
    assert payload["metadata"] == {"mode": "live", "family": "merged_table"}


def test_event_payload_omits_empty_metadata():
    # Given an event with no metadata.
    event = LedgerEvent(
        provider="deterministic",
        model_alias="deterministic",
        route_reason="fixture:simple_text expected deterministic_only",
        latency_ms=1.0,
        status="ok",
        cost_estimate_usd=None,
        metadata={},
    )

    # When
    payload = event_payload(event)

    # Then: an empty metadata mapping is dropped rather than written as {}.
    assert "metadata" not in payload
    assert payload["cost_estimate_usd"] is None


def test_event_payload_records_metadata_verbatim():
    # Given metadata containing a long but non-secret identifier. The ledger no longer
    # mangles long identifiers; keeping secrets out is a source + gitignore + scanner
    # responsibility, not a runtime scrubbing pass.
    document_id = "doc-" + "0123456789" * 4  # 44-char benign identifier
    event = LedgerEvent(
        provider="gemini",
        model_alias="gemini-2.5-flash",
        route_reason="fixture:chart_like_page expected gemini_vlm",
        latency_ms=10.0,
        status="ok",
        cost_estimate_usd=None,
        metadata={"document_id": document_id, "mode": "offline"},
    )

    # When
    payload = event_payload(event)

    # Then: the identifier survives intact (no [REDACTED]).
    assert payload["metadata"]["document_id"] == document_id
    assert "[REDACTED]" not in json.dumps(payload)


def test_append_ledger_event_writes_one_json_line(tmp_path):
    # Given
    path = tmp_path / "ledger.jsonl"
    event = LedgerEvent(
        provider="gemini",
        model_alias="gemini-2.5-flash",
        route_reason="hint:needs_image_description",
        latency_ms=10.0,
        status="ok",
        cost_estimate_usd=None,
        metadata={"mode": "live", "family": "chart_like_page"},
    )

    # When
    append_ledger_event(path, event)
    append_ledger_event(path, event)
    contents = path.read_text(encoding="utf-8")

    # Then: each call appends exactly one JSON object line.
    records = [json.loads(line) for line in contents.splitlines()]
    assert len(records) == 2
    assert records[0]["provider"] == "gemini"
    assert records[0]["route_reason"] == "hint:needs_image_description"
    assert records[0]["metadata"]["family"] == "chart_like_page"
