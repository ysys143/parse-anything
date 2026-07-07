"""OpenAI-compatible multi-image transcriber for whole-document mode (--whole-doc).

Some document VLMs (e.g. baidu/Unlimited-OCR's ``infer_multi``) transcribe the WHOLE document in a
single call -- all page images in, one coherent Markdown document out (cross-page reading order,
page-spanning tables resolved in one 32k-context pass). parse-anything's per-page ``--primary paddle``
path can't exercise that. This module POSTs every rendered page as ONE OpenAI /v1/chat/completions
request (N ``image_url`` parts + one text part) and returns the assembled document Markdown, so the
model's one-shot output can be wrapped by the deterministic substrate (ODL structure, value oracle,
semantic graph, chunks, provenance) instead of the model being called per page.

The ``client`` is injectable (the repo's ProviderHttpClient in real runs, a fake in tests). Credentials
come from settings (.env PADDLE_BASE_URL reused as the OpenAI /v1 base / PADDLE_API_KEY) and are NEVER
hard-coded. Errors surface as opaque codes (no URL/key text) per the security posture.
"""
from __future__ import annotations

import base64
import json
from collections.abc import Callable, Sequence
from typing import Any

from parse_anything.providers import HttpRequest, _join_url, is_success_status

_DEFAULT_MODEL = "model"
_DEFAULT_PROMPT = "document parsing."


class OpenAiVlmError(RuntimeError):
    """Opaque OpenAI-compatible transcription failure (e.g. openai_http_500, openai_empty_text)."""


def transcribe_document(
    pngs: Sequence[bytes], *, client: Any, base_url: str, token: str,
    model: str = _DEFAULT_MODEL, prompt: str = _DEFAULT_PROMPT,
) -> str:
    """Send ALL page images in ONE request; return the whole-document Markdown."""
    content: list[dict[str, Any]] = [
        {"type": "image_url",
         "image_url": {"url": f"data:image/png;base64,{base64.b64encode(p).decode('ascii')}"}}
        for p in pngs
    ]
    content.append({"type": "text", "text": prompt})
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.0,
    }, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token or 'EMPTY'}"}
    response = client.send(HttpRequest("POST", _join_url(base_url, "chat/completions"), headers, body))
    if not is_success_status(response.status_code):
        raise OpenAiVlmError(f"openai_http_{response.status_code}")
    try:
        text = json.loads(response.body)["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        raise OpenAiVlmError("openai_bad_response") from exc
    if not isinstance(text, str) or text.strip() == "":
        raise OpenAiVlmError("openai_empty_text")
    return text


def make_multi_transcriber(
    client: Any, *, base_url: str, token: str, model: str = _DEFAULT_MODEL, prompt: str = _DEFAULT_PROMPT,
) -> Callable[[Sequence[bytes]], str]:
    """A list[png] -> document-Markdown callable for whole-doc assembly (--whole-doc)."""
    return lambda pngs: transcribe_document(pngs, client=client, base_url=base_url, token=token,
                                            model=model, prompt=prompt)
