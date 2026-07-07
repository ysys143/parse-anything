from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from typing import Any

from parse_anything.ir import NormalizedPage, ProviderName

_COORD_TOKEN_RE = re.compile(r"<[xy]_-?\d+(?:\.\d+)?>", re.IGNORECASE)
_CLASS_FIGURE_RE = re.compile(r"<class_(?:Picture|Figure|Image|Diagram)>", re.IGNORECASE)
_CLASS_TOKEN_RE = re.compile(r"<class_[^>]+>", re.IGNORECASE)
_REF_TOKEN_RE = re.compile(r"<\|ref\|>.*?<\|/ref\|>", re.IGNORECASE | re.DOTALL)
_DET_TOKEN_RE = re.compile(r"<\|det\|>.*?<\|/det\|>", re.IGNORECASE | re.DOTALL)
_HTML_LAYOUT_HINT_RE = re.compile(
    r"</?(?:div|p|header|footer|section|article|main|aside|figure|figcaption|table|thead|tbody|tr|td|th|ul|ol|li|h[1-6]|img|math)\b",
    re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAGS = r"div|p|header|footer|section|article|main|aside|figure|figcaption|table|thead|tbody|tr|td|th|ul|ol|li|h[1-6]"
_BLOCK_END_RE = re.compile(rf"</(?:{_BLOCK_TAGS})>", re.IGNORECASE)
_BLOCK_START_RE = re.compile(rf"<(?:{_BLOCK_TAGS})\b[^>]*>", re.IGNORECASE)
_DISPLAY_MATH_RE = re.compile(r"<math\b[^>]*display=[\"']block[\"'][^>]*>(.*?)</math>", re.IGNORECASE | re.DOTALL)
_INLINE_MATH_RE = re.compile(r"<math\b[^>]*>(.*?)</math>", re.IGNORECASE | re.DOTALL)
_FRONTMATTER_LINE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:\s*.*$")


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


def normalize_transcription_markdown(markdown: str) -> str:
    text = _drop_yaml_frontmatter(markdown.strip())
    text = _REF_TOKEN_RE.sub("", text)
    text = _DET_TOKEN_RE.sub("", text)
    text = _CLASS_FIGURE_RE.sub("\n[figure]\n", text)
    text = _COORD_TOKEN_RE.sub("", text)
    text = _CLASS_TOKEN_RE.sub("", text)
    if "data-bbox" in text.lower() or _HTML_LAYOUT_HINT_RE.search(text):
        text = _html_layout_to_markdown(text)
    return _squash_blank_lines(text)


def _drop_yaml_frontmatter(markdown: str) -> str:
    lines = markdown.splitlines()
    if not lines:
        return markdown
    first_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_index is None:
        return ""
    first = lines[first_index].strip()
    if first == "---":
        for index in range(first_index + 1, len(lines)):
            if lines[index].strip() == "---":
                return "\n".join(lines[index + 1 :]).lstrip()
        return markdown
    if not first.lower().startswith("is_diagram:"):
        return markdown
    index = first_index
    while index < len(lines) and (not lines[index].strip() or _FRONTMATTER_LINE_RE.match(lines[index].strip())):
        index += 1
    return "\n".join(lines[index:]).lstrip()


def _html_layout_to_markdown(markdown: str) -> str:
    text = re.sub(r"<img\b[^>]*>", "\n[figure]\n", markdown, flags=re.IGNORECASE)
    text = _DISPLAY_MATH_RE.sub(lambda match: f"\n$${html.unescape(match.group(1)).strip()}$$\n", text)
    text = _INLINE_MATH_RE.sub(lambda match: html.unescape(match.group(1)).strip(), text)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _BLOCK_START_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    return html.unescape(text)


def _squash_blank_lines(markdown: str) -> str:
    lines = [line.rstrip() for line in markdown.splitlines()]
    out: list[str] = []
    blank = False
    for line in lines:
        if line.strip():
            out.append(line.strip())
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip()


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
    """Return the model's text from a Gemini generateContent response, or None.

    Only reads candidates[].content.parts[].text. A safety-blocked / empty response
    (no candidate part) returns None so the caller can fail the page, rather than
    surfacing a stray 'text' field from a citation/safety block as model output.
    """
    if isinstance(payload, Mapping):
        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    continue
                content = candidate.get("content")
                if not isinstance(content, Mapping):
                    continue
                parts = content.get("parts")
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    if isinstance(part, Mapping):
                        text = part.get("text")
                        if isinstance(text, str) and text != "":
                            return text
    return None


def normalize_paddle(
    result: Any,
    *,
    ledger_fields: Mapping[str, Any] | None = None,
) -> NormalizedPage:
    fields = dict(ledger_fields or {})
    if not isinstance(result, Mapping):
        return NormalizedPage(markdown="", provider=ProviderName.PADDLE, ledger_fields=fields)

    # Unwrap a {"result": {...}} envelope so callers can pass the raw response body.
    if "layoutParsingResults" not in result:
        inner = result.get("result")
        if isinstance(inner, Mapping) and "layoutParsingResults" in inner:
            result = inner

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
        if isinstance(markdown, str):
            # Some PaddleOCR responses return markdown as a plain string.
            if markdown != "":
                markdown_parts.append(markdown)
        elif isinstance(markdown, Mapping):
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

    if image_count:
        fields = {**fields, "paddle_image_count": image_count}

    # Prefer the page-level confidence; otherwise average the per-entry ones. The two
    # are not mixed, since they can be on different scales.
    top_confidence = _coerce_float(result.get("confidence"))
    if top_confidence is not None:
        page_confidence: float | None = top_confidence
    elif confidences:
        page_confidence = sum(confidences) / len(confidences)
    else:
        page_confidence = None

    return NormalizedPage(
        markdown="\n\n".join(markdown_parts),
        confidence=page_confidence,
        provider=ProviderName.PADDLE,
        ledger_fields=fields,
    )


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
