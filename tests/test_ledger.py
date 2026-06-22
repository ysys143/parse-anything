from __future__ import annotations

import json
import re

from odl_vl.ledger import LedgerEvent, append_ledger_event, redacted_event


def test_redacted_event_preserves_required_ledger_fields_without_secret_values():
    # Given
    key_value = "a" * 32
    signature_value = "b" * 32
    event = LedgerEvent(
        provider="paddle",
        model_alias="PaddleOCR-VL-1.6",
        route_reason="hint:no_text_layer",
        latency_ms=125.5,
        status="ok",
        fallback=False,
        cost_estimate_usd=0.0025,
        metadata={
            "PADDLE_API_KEY": key_value,
            "job_url": f"https://provider.example/jobs/1?X-Amz-Signature={signature_value}",
            "safe_note": "queued",
        },
    )

    # When
    payload = redacted_event(event)

    # Then
    assert payload["provider"] == "paddle"
    assert payload["model_alias"] == "PaddleOCR-VL-1.6"
    assert payload["route_reason"] == "hint:no_text_layer"
    assert payload["latency_ms"] == 125.5
    assert payload["status"] == "ok"
    assert payload["fallback"] is False
    assert payload["cost_estimate_usd"] == 0.0025
    rendered = json.dumps(payload, sort_keys=True)
    assert "PADDLE_API_KEY" not in rendered
    assert key_value not in rendered
    assert "X-Amz-Signature" not in rendered
    assert "safe_note" in rendered


def test_append_ledger_event_writes_jsonl_and_redacts_token_like_values(tmp_path):
    # Given
    path = tmp_path / "ledger.jsonl"
    token_value = "c" * 32
    result_token_value = "d" * 32
    event = LedgerEvent(
        provider="gemini",
        model_alias="gemini-3.1-flash-lite",
        route_reason="hint:needs_image_description",
        latency_ms=10.0,
        status="fallback_used",
        fallback=True,
        cost_estimate_usd=None,
        metadata={
            "TOKEN": token_value,
            "result_url": f"https://provider.example/result?token={result_token_value}",
            "family": "chart_like_page",
        },
    )

    # When
    append_ledger_event(path, event)
    contents = path.read_text(encoding="utf-8")

    # Then
    records = [json.loads(line) for line in contents.splitlines()]
    assert len(records) == 1
    assert records[0]["provider"] == "gemini"
    assert records[0]["fallback"] is True
    assert "API_KEY" not in contents
    assert "TOKEN" not in contents
    assert re.search(r"[0-9a-fA-F]{32,}", contents) is None
    assert "result_url" not in contents
    assert "chart_like_page" in contents


def test_redacted_event_removes_long_non_hex_token_like_values_but_keeps_safe_text():
    # Given
    non_hex_token = "sk_live_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_"
    event = LedgerEvent(
        provider="gemini",
        model_alias="gemini-3.1-flash-lite",
        route_reason="fixture:chart_like_page expected gemini_vlm",
        latency_ms=11.0,
        status="ok",
        fallback=False,
        cost_estimate_usd=0.001,
        metadata={
            "family": "chart_like_page",
            "safe_note": "queued for fixture route",
            "opaque_id": non_hex_token,
        },
    )

    # When
    payload = redacted_event(event)
    rendered = json.dumps(payload, sort_keys=True)

    # Then
    assert non_hex_token not in rendered
    assert "[REDACTED]" in rendered
    assert "chart_like_page" in rendered
    assert "queued for fixture route" in rendered
