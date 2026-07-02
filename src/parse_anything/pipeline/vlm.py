"""VLM transcription wrapper (reuses parse_anything.providers; injectable client).

Evidence: docs/measurement-findings.md F3 (image-only baseline), F9 (multi-image for
page-spanning tables). Contract: pdf-pipeline-requirements §5.

The ``client`` is any object with ``send(HttpRequest) -> HttpResponse`` (the live
ProviderHttpClient in real runs, a fake in tests) so the pipeline stays testable without
network or keys. Errors surface as opaque codes (no URL/key text) per the security posture.
"""
from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from typing import Any

from parse_anything.normalizers import extract_gemini_text, try_decode_json
from parse_anything.providers import (
    GeminiGenerateContentRequest,
    GeminiInlineImage,
    HttpRequest,
    build_gemini_generate_content_request,
    is_success_status,
)


class VlmError(RuntimeError):
    """Opaque VLM failure (e.g. gemini_http_429, gemini_empty_text)."""


def transcribe_image(image_png: bytes, prompt: str, *, api_key: str, client: Any, mime: str = "image/png") -> str:
    request = build_gemini_generate_content_request(
        GeminiGenerateContentRequest(
            api_key=api_key, prompt=prompt, image=GeminiInlineImage(mime_type=mime, data=image_png)
        )
    )
    return _send(client, request)


def transcribe_images(images: Sequence[bytes], prompt: str, *, api_key: str, client: Any) -> str:
    """Send multiple page images in ONE request (page-spanning table reconstruction, F9)."""
    base = build_gemini_generate_content_request(
        GeminiGenerateContentRequest(api_key=api_key, prompt=prompt, image=None)
    )
    parts: list[dict[str, Any]] = [{"text": prompt}]
    for png in images:
        parts.append({"inlineData": {"mimeType": "image/png", "data": base64.b64encode(png).decode("ascii")}})
    body = json.dumps({"contents": [{"parts": parts}]}, separators=(",", ":")).encode("utf-8")
    return _send(client, HttpRequest(method=base.method, url=base.url, headers=base.headers, body=body))


def _send(client: Any, request: HttpRequest) -> str:
    response = client.send(request)
    if not is_success_status(response.status_code):
        raise VlmError(f"gemini_http_{response.status_code}")
    text = extract_gemini_text(try_decode_json(response.body))
    if text is None or text.strip() == "":
        raise VlmError("gemini_empty_text")
    return text
