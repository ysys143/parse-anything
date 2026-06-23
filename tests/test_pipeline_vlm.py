from __future__ import annotations

import json

import pytest

from odl_vl.pipeline.vlm import VlmError, transcribe_image, transcribe_images
from odl_vl.providers import HttpResponse


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def _gemini_ok(text: str) -> HttpResponse:
    body = json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode("utf-8")
    return HttpResponse(status_code=200, body=body)


def test_transcribe_image_returns_text_and_sends_inline_image():
    client = _FakeClient([_gemini_ok("# Heading\n\nbody")])
    out = transcribe_image(b"\x89PNG\r\n\x1a\nfake", "transcribe", api_key="k", client=client)
    assert out == "# Heading\n\nbody"
    assert b"inlineData" in client.requests[-1].body


def test_transcribe_images_sends_all_images_in_one_request():
    client = _FakeClient([_gemini_ok("merged table")])
    out = transcribe_images([b"img-a", b"img-b"], "stitch", api_key="k", client=client)
    assert out == "merged table"
    assert client.requests[-1].body.count(b"inlineData") == 2  # both pages in one call


def test_http_error_raises_opaque_vlm_error():
    client = _FakeClient([HttpResponse(status_code=429, body=b"")])
    with pytest.raises(VlmError, match="gemini_http_429"):
        transcribe_image(b"x", "p", api_key="k", client=client)


def test_empty_response_raises():
    client = _FakeClient([_gemini_ok("")])
    with pytest.raises(VlmError, match="gemini_empty_text"):
        transcribe_image(b"x", "p", api_key="k", client=client)
