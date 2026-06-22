from __future__ import annotations

import io
import json
import urllib.error
from dataclasses import dataclass, field

from odl_vl.providers import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_PADDLE_MODEL,
    GeminiGenerateContentRequest,
    HttpRequest,
    HttpResponse,
    PaddlePollRequest,
    PaddleSubmitRequest,
    ProviderHttpClient,
    SafeTransport,
    build_gemini_generate_content_request,
    build_paddle_poll_request,
    build_paddle_submit_request,
)


def test_safe_transport_preserves_http_error_status_and_body():
    # Given an inner transport that raises an HTTPError carrying a server reason body.
    @dataclass(slots=True)
    class _RaisingTransport:
        def send(self, request: HttpRequest) -> HttpResponse:
            raise urllib.error.HTTPError(
                url=request.url,
                code=429,
                msg="Too Many Requests",
                hdrs={},  # type: ignore[arg-type]
                fp=io.BytesIO(b'{"error":"quota exceeded"}'),
            )

    transport = SafeTransport(_RaisingTransport())
    request = HttpRequest(method="GET", url="https://provider.example/jobs", headers={})

    # When
    response = transport.send(request)

    # Then: the error surfaces as a status code with the server body preserved.
    assert response.status_code == 429
    assert b"quota exceeded" in response.body


def test_build_gemini_generate_content_request_uses_safe_default_model():
    # Given
    secret = "fake-gemini-secret-123"
    spec = GeminiGenerateContentRequest(api_key=secret, prompt="Extract this page.")

    # When
    request = build_gemini_generate_content_request(spec)
    payload = json.loads(request.body.decode("utf-8"))

    # Then
    assert spec.model == DEFAULT_GEMINI_MODEL == "gemini-3.1-flash-lite"
    assert request.method == "POST"
    assert request.url == (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-3.1-flash-lite:generateContent"
    )
    assert request.headers["x-goog-api-key"] == secret
    assert "Authorization" not in request.headers
    assert request.headers["Content-Type"] == "application/json"
    assert payload == {"contents": [{"parts": [{"text": "Extract this page."}]}]}
    assert secret not in repr(spec)
    assert secret not in repr(request)


def test_build_paddle_submit_request_uses_safe_default_model():
    # Given
    secret = "fake-paddle-secret-123"
    spec = PaddleSubmitRequest(
        api_key=secret,
        base_url="https://paddle.example.invalid",
        document_url="https://fixtures.example.invalid/page.png",
    )

    # When
    request = build_paddle_submit_request(spec)
    payload = json.loads(request.body.decode("utf-8"))

    # Then
    assert spec.model == DEFAULT_PADDLE_MODEL == "PaddleOCR-VL-1.6"
    assert request.method == "POST"
    assert request.url == "https://paddle.example.invalid/api/v2/ocr/jobs"
    assert request.headers["Authorization"] == f"Bearer {secret}"
    assert request.headers["Content-Type"] == "application/json"
    assert payload == {
        "fileUrl": "https://fixtures.example.invalid/page.png",
        "model": "PaddleOCR-VL-1.6",
        "optionalPayload": {
            "useChartRecognition": False,
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
        },
    }
    assert secret not in repr(spec)
    assert secret not in repr(request)


def test_build_paddle_submit_request_accepts_full_jobs_endpoint_base_url():
    # Given
    secret = "fake-paddle-secret-full-endpoint"
    spec = PaddleSubmitRequest(
        api_key=secret,
        base_url="https://paddle.example.invalid/api/v2/ocr/jobs",
        document_url="https://fixtures.example.invalid/page.png",
    )

    # When
    request = build_paddle_submit_request(spec)

    # Then
    assert request.url == "https://paddle.example.invalid/api/v2/ocr/jobs"
    assert secret not in repr(spec)
    assert secret not in repr(request)


def test_build_paddle_submit_request_accepts_optional_payload_override():
    # Given
    spec = PaddleSubmitRequest(
        api_key="fake-paddle-secret-override",
        base_url="https://paddle.example.invalid",
        document_url="https://fixtures.example.invalid/page.png",
        optional_payload={
            "useDocOrientationClassify": True,
            "useDocUnwarping": False,
            "useChartRecognition": True,
        },
    )

    # When
    request = build_paddle_submit_request(spec)
    payload = json.loads(request.body.decode("utf-8"))

    # Then
    assert payload == {
        "fileUrl": "https://fixtures.example.invalid/page.png",
        "model": "PaddleOCR-VL-1.6",
        "optionalPayload": {
            "useChartRecognition": True,
            "useDocOrientationClassify": True,
            "useDocUnwarping": False,
        },
    }
    assert "fake-paddle-secret-override" not in repr(spec)
    assert "fake-paddle-secret-override" not in repr(request)


def test_build_paddle_poll_request_targets_official_job_url():
    # Given
    secret = "fake-paddle-secret-456"
    spec = PaddlePollRequest(
        api_key=secret,
        base_url="https://paddle.example.invalid/",
        job_id="job/with space",
    )

    # When
    request = build_paddle_poll_request(spec)

    # Then
    assert request.method == "GET"
    assert request.url == "https://paddle.example.invalid/api/v2/ocr/jobs/job%2Fwith%20space"
    assert request.headers["Authorization"] == f"Bearer {secret}"
    assert request.body == b""
    assert secret not in repr(spec)
    assert secret not in repr(request)


def test_build_paddle_poll_request_accepts_full_jobs_endpoint_base_url():
    # Given
    secret = "fake-paddle-secret-full-poll"
    spec = PaddlePollRequest(
        api_key=secret,
        base_url="https://paddle.example.invalid/api/v2/ocr/jobs",
        job_id="job/with space",
    )

    # When
    request = build_paddle_poll_request(spec)

    # Then
    assert request.url == "https://paddle.example.invalid/api/v2/ocr/jobs/job%2Fwith%20space"
    assert request.headers["Authorization"] == f"Bearer {secret}"
    assert request.body == b""
    assert secret not in repr(spec)
    assert secret not in repr(request)


def test_provider_http_client_uses_injected_transport_without_network():
    # Given
    @dataclass(slots=True)
    class RecordingTransport:
        requests: list[HttpRequest] = field(default_factory=list)

        def send(self, request: HttpRequest) -> HttpResponse:
            self.requests.append(request)
            return HttpResponse(status_code=202, body=b'{"status":"queued"}')

    transport = RecordingTransport()
    client = ProviderHttpClient(transport=transport)
    request = build_paddle_submit_request(
        PaddleSubmitRequest(
            api_key="fake-paddle-secret-789",
            base_url="https://paddle.example.invalid",
            document_url="https://fixtures.example.invalid/page.png",
        )
    )

    # When
    response = client.send(request)

    # Then
    assert response.status_code == 202
    assert response.body == b'{"status":"queued"}'
    assert transport.requests == [request]
