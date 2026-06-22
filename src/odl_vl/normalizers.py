from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from odl_vl.ir import NormalizedPage, ProviderName
from odl_vl.jsonsearch import find_first_string


def decode_json_body(body: bytes | str) -> Any:
    """Decode a provider response body, raising ValueError on malformed JSON."""
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    try:
        return json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"provider response is not valid JSON: {error}") from error


def try_decode_json(body: bytes | str) -> Any:
    """Best-effort JSON decode for CLI paths; returns None on malformed input.

    Library callers that need an error should use :func:`decode_json_body`.
    """
    try:
        return decode_json_body(body)
    except ValueError:
        return None


def normalize_deterministic(
    first_pass_md: str,
    *,
    ledger_fields: Mapping[str, Any] | None = None,
) -> NormalizedPage:
    return NormalizedPage(
        markdown=first_pass_md,
        provider=ProviderName.DETERMINISTIC,
        ledger_fields=dict(ledger_fields or {}),
    )


def normalize_gemini(
    text: str,
    *,
    image_description: str | None = None,
    confidence: float | None = None,
    ledger_fields: Mapping[str, Any] | None = None,
) -> NormalizedPage:
    return NormalizedPage(
        markdown=text.strip(),
        image_description=image_description,
        confidence=confidence,
        provider=ProviderName.GEMINI,
        ledger_fields=dict(ledger_fields or {}),
    )


def extract_gemini_text(payload: Any) -> str | None:
    """Walk a Gemini generateContent response for the first text part."""
    return find_first_string(payload, frozenset({"text"}))


def normalize_paddle(
    result: Any,
    *,
    ledger_fields: Mapping[str, Any] | None = None,
) -> NormalizedPage:
    fields = dict(ledger_fields or {})
    if not isinstance(result, Mapping):
        return NormalizedPage(markdown="", provider=ProviderName.PADDLE, ledger_fields=fields)

    parsing_results = result.get("layoutParsingResults")
    if not isinstance(parsing_results, list) or not parsing_results:
        return NormalizedPage(markdown="", provider=ProviderName.PADDLE, ledger_fields=fields)

    markdown_parts: list[str] = []
    image_count = 0
    confidences: list[float] = []
    for entry in parsing_results:
        if not isinstance(entry, Mapping):
            continue
        markdown = entry.get("markdown")
        if isinstance(markdown, Mapping):
            text = markdown.get("text")
            if isinstance(text, str) and text != "":
                markdown_parts.append(text)
            images = markdown.get("images")
            if isinstance(images, Mapping):
                image_count += len(images)
            elif isinstance(images, list):
                image_count += len(images)
        output_images = entry.get("outputImages")
        if isinstance(output_images, Mapping):
            image_count += len(output_images)
        elif isinstance(output_images, list):
            image_count += len(output_images)
        confidence = _coerce_float(entry.get("confidence"))
        if confidence is not None:
            confidences.append(confidence)

    top_confidence = _coerce_float(result.get("confidence"))
    if top_confidence is not None:
        confidences.append(top_confidence)

    if image_count:
        fields = {**fields, "paddle_image_count": image_count}

    return NormalizedPage(
        markdown="\n\n".join(markdown_parts),
        confidence=(sum(confidences) / len(confidences)) if confidences else None,
        provider=ProviderName.PADDLE,
        ledger_fields=fields,
    )


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
