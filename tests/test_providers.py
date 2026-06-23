from __future__ import annotations

import http.client
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


def test_safe_transport_catches_read_timeout():
    # Given an inner transport that raises TimeoutError (socket read timeout), which
    # is NOT a urllib.error.URLError subclass.
    @dataclass(slots=True)
    class _TimingOutTransport:
        def send(self, request: HttpRequest) -> HttpResponse:
            raise TimeoutError("timed out")

    transport = SafeTransport(_TimingOutTransport())
    request = HttpRequest(method="GET", url="https://provider.example/jobs", headers={})

    # When / Then: a timeout is turned into status 0 instead of escaping the wrapper.
    assert transport.send(request).status_code == 0


def test_safe_transport_catches_malformed_url_exceptions_without_leaking_url():
    # Given inner transports that raise what urlopen raises for a malformed URL:
    # http.client.InvalidURL (an HTTPException, NOT a URLError subclass) and ValueError.
    # Their messages embed the offending URL -- including a signed URL's signature.
    signature = "X-Amz-Signature=" + "TOPSECRETSIGNATUREVALUE"

    @dataclass(slots=True)
    class _InvalidUrlTransport:
        def send(self, request: HttpRequest) -> HttpResponse:
            raise http.client.InvalidURL(f"URL can't contain control characters. '/job?{signature}'")

    @dataclass(slots=True)
    class _ValueErrorTransport:
        def send(self, request: HttpRequest) -> HttpResponse:
            raise ValueError(f"unknown url type: 'ht!tp://host/r?{signature}'")

    request = HttpRequest(method="GET", url="https://provider.example/r", headers={})

    # When / Then: both collapse to status 0, so no URL-bearing exception text escapes
    # the wrapper into the caller's error string.
    for inner in (_InvalidUrlTransport(), _ValueErrorTransport()):
        response = SafeTransport(inner).send(request)
        assert response.status_code == 0
        assert response.body == b""


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


def test_build_gemini_request_attaches_image_as_base64_inline_data():
    import base64

    from odl_vl.providers import GeminiInlineImage

    image_bytes = b"\x89PNG\r\n\x1a\nrealpixels"
    spec = GeminiGenerateContentRequest(
        api_key="fake-gemini-secret-img",
        prompt="Describe the chart.",
        image=GeminiInlineImage(mime_type="image/png", data=image_bytes),
    )

    # When
    request = build_gemini_generate_content_request(spec)
    payload = json.loads(request.body.decode("utf-8"))

    # Then: the request carries both the text and the base64-encoded image.
    parts = payload["contents"][0]["parts"]
    assert {"text": "Describe the chart."} in parts
    inline = next(p["inlineData"] for p in parts if "inlineData" in p)
    assert inline["mimeType"] == "image/png"
    assert base64.b64decode(inline["data"]) == image_bytes


def test_build_gemini_request_without_image_is_text_only():
    spec = GeminiGenerateContentRequest(api_key="fake-gemini-secret", prompt="hi")
    payload = json.loads(build_gemini_generate_content_request(spec).body.decode("utf-8"))
    assert payload == {"contents": [{"parts": [{"text": "hi"}]}]}


def test_build_paddle_submit_request_handles_service_root_base_url():
    # Given a base URL that is the OCR service root, missing the trailing /jobs.
    spec = PaddleSubmitRequest(
        api_key="fake-paddle-secret-root",
        base_url="https://paddle.example.invalid/api/v2/ocr",
        document_url="https://fixtures.example.invalid/page.png",
    )

    # When
    request = build_paddle_submit_request(spec)

    # Then: the path is not duplicated.
    assert request.url == "https://paddle.example.invalid/api/v2/ocr/jobs"


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
