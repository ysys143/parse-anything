"""VLM transcriber wrappers for the proxy (reuses odl_vl.pipeline VLM modules).

A transcriber is a ``Callable[[bytes, str], str]`` : ``(page_png, prompt) -> markdown``. Gemini
honors the prompt; Paddle (document-specialized OCR) ignores it. The live HTTP client is the
repo's ``ProviderHttpClient(SafeTransport(UrllibTransport()))`` so URL/key-bearing exceptions
collapse to status codes (no secret leakage). Credentials come from ``load_settings`` (.env /
env), never hard-coded.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol

from odl_vl.config import load_settings
from odl_vl.pipeline import paddle_vlm
from odl_vl.pipeline.vlm import transcribe_image
from odl_vl.providers import ProviderHttpClient, SafeTransport, UrllibTransport

Transcriber = Callable[[bytes, str], str]


class _Settings(Protocol):
    gemini_api_key: str | None
    paddle_api_key: str | None
    paddle_base_url: str | None
    paddle_model: str | None
    has_gemini: bool
    has_paddle: bool


def make_http_client() -> ProviderHttpClient:
    """Live client; SafeTransport keeps non-2xx and URL errors from raising URL-bearing text."""
    return ProviderHttpClient(transport=SafeTransport(UrllibTransport()))


def gemini_transcriber(api_key: str, *, client: Any = None) -> Transcriber:
    cl = client or make_http_client()
    return lambda png, prompt: transcribe_image(png, prompt, api_key=api_key, client=cl)


def paddle_transcriber(
    base_url: str, token: str, *, model: str | None = None, client: Any = None, doc_preprocess: bool = False
) -> Transcriber:
    cl = client or make_http_client()
    fn = paddle_vlm.make_transcriber(
        cl, base_url=base_url, token=token, model=model or paddle_vlm._DEFAULT_MODEL, doc_preprocess=doc_preprocess
    )
    return lambda png, _prompt: fn(png)  # Paddle ignores the prompt


def transcriber_from_env(
    provider: str, *, settings: _Settings | None = None, doc_preprocess: bool = False
) -> Transcriber:
    """Build a transcriber from .env/env settings. Raises if the provider is unconfigured.
    ``doc_preprocess`` enables Paddle's scan orientation/unwarp correction (no-op for Gemini)."""
    s = settings or load_settings()
    if provider == "gemini":
        if not s.has_gemini:
            raise RuntimeError("gemini provider requires GEMINI_API_KEY")
        return gemini_transcriber(s.gemini_api_key)  # type: ignore[arg-type]
    if provider == "paddle":
        if not s.has_paddle:
            raise RuntimeError("paddle provider requires PADDLE_BASE_URL + PADDLE_API_KEY")
        return paddle_transcriber(
            s.paddle_base_url, s.paddle_api_key, model=s.paddle_model, doc_preprocess=doc_preprocess  # type: ignore[arg-type]
        )
    raise ValueError(f"unknown provider: {provider!r}")
