from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Protocol, TypedDict


DEFAULT_GEMINI_MODEL: Final = "gemini-3.1-flash-lite"
DEFAULT_PADDLE_MODEL: Final = "PaddleOCR-VL-1.6"
GEMINI_BASE_URL: Final = "https://generativelanguage.googleapis.com"
_PADDLE_JOBS_PATH: Final = "/api/v2/ocr/jobs"
_PADDLE_OCR_PATH: Final = "/api/v2/ocr"
_JSON_CONTENT_TYPE: Final = "application/json"


class GeminiPart(TypedDict):
    text: str


class GeminiContent(TypedDict):
    parts: list[GeminiPart]


class GeminiPayload(TypedDict):
    contents: list[GeminiContent]


class PaddleOptionalPayload(TypedDict):
    useDocOrientationClassify: bool
    useDocUnwarping: bool
    useChartRecognition: bool


class PaddleSubmitPayload(TypedDict):
    fileUrl: str
    model: str
    optionalPayload: PaddleOptionalPayload


def _default_paddle_optional_payload() -> PaddleOptionalPayload:
    return {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    }


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = b""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


class Transport(Protocol):
    def send(self, request: HttpRequest) -> HttpResponse: ...


@dataclass(frozen=True, slots=True)
class GeminiGenerateContentRequest:
    api_key: str = field(repr=False)
    prompt: str
    model: str = DEFAULT_GEMINI_MODEL
    base_url: str = GEMINI_BASE_URL


@dataclass(frozen=True, slots=True)
class PaddleSubmitRequest:
    api_key: str = field(repr=False)
    base_url: str
    document_url: str
    model: str = DEFAULT_PADDLE_MODEL
    optional_payload: PaddleOptionalPayload = field(default_factory=_default_paddle_optional_payload)


@dataclass(frozen=True, slots=True)
class PaddlePollRequest:
    api_key: str = field(repr=False)
    base_url: str
    job_id: str


@dataclass(frozen=True, slots=True)
class UrllibTransport:
    timeout_seconds: float = 30.0

    def send(self, request: HttpRequest) -> HttpResponse:
        urllib_request = urllib.request.Request(
            request.url,
            data=request.body or None,
            headers=dict(request.headers),
            method=request.method,
        )
        with urllib.request.urlopen(urllib_request, timeout=self.timeout_seconds) as response:
            return HttpResponse(
                status_code=response.status,
                body=response.read(),
                headers=dict(response.getheaders()),
            )


@dataclass(frozen=True, slots=True)
class SafeTransport:
    """Wrap a transport so HTTP/URL errors surface as a status code instead of raising.

    Lets provider code branch on ``response.status_code`` uniformly for both fake
    transports (tests) and the live ``UrllibTransport`` (which raises on non-2xx).
    """

    inner: Transport

    def send(self, request: HttpRequest) -> HttpResponse:
        try:
            return self.inner.send(request)
        except urllib.error.HTTPError as error:
            # Preserve the server error body so callers can surface the reason.
            try:
                body = error.read()
            except OSError:
                body = b""
            return HttpResponse(status_code=error.code, body=body)
        except urllib.error.URLError:
            return HttpResponse(status_code=0, body=b"")


@dataclass(frozen=True, slots=True)
class ProviderHttpClient:
    transport: Transport = field(default_factory=UrllibTransport)

    def send(self, request: HttpRequest) -> HttpResponse:
        return self.transport.send(request)


def is_success_status(status_code: int) -> bool:
    return 200 <= status_code < 300


def build_gemini_generate_content_request(spec: GeminiGenerateContentRequest) -> HttpRequest:
    payload: GeminiPayload = {"contents": [{"parts": [{"text": spec.prompt}]}]}
    return HttpRequest(
        method="POST",
        url=_join_url(spec.base_url, f"/v1beta/models/{spec.model}:generateContent"),
        # Gemini API keys authenticate via x-goog-api-key, not Authorization: Bearer.
        headers=_gemini_api_key_headers(spec.api_key),
        body=_json_body(payload),
    )


def build_paddle_submit_request(spec: PaddleSubmitRequest) -> HttpRequest:
    payload: PaddleSubmitPayload = {
        "fileUrl": spec.document_url,
        "model": spec.model,
        "optionalPayload": spec.optional_payload,
    }
    return HttpRequest(
        method="POST",
        url=_paddle_jobs_url(spec.base_url),
        headers=_json_authorization_headers(spec.api_key),
        body=_json_body(payload),
    )


def build_paddle_poll_request(spec: PaddlePollRequest) -> HttpRequest:
    job_id = urllib.parse.quote(spec.job_id, safe="")
    return HttpRequest(
        method="GET",
        url=_join_url(_paddle_jobs_url(spec.base_url), job_id),
        headers={"Authorization": f"Bearer {spec.api_key}"},
    )


def _json_authorization_headers(api_key: str) -> Mapping[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": _JSON_CONTENT_TYPE,
    }


def _gemini_api_key_headers(api_key: str) -> Mapping[str, str]:
    return {
        "Content-Type": _JSON_CONTENT_TYPE,
        "x-goog-api-key": api_key,
    }


def _json_body(payload: GeminiPayload | PaddleSubmitPayload) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _join_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


def _paddle_jobs_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    path = parsed.path.rstrip("/")
    if path.endswith(_PADDLE_JOBS_PATH):
        target = path  # already the jobs endpoint
    elif path.endswith(_PADDLE_OCR_PATH):
        target = path + "/jobs"  # service root: append the missing /jobs
    else:
        return _join_url(base_url, _PADDLE_JOBS_PATH)  # host root or unrelated base
    normalized = parsed._replace(path=target, params="", query="", fragment="")
    return urllib.parse.urlunparse(normalized)
