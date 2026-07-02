"""PaddleOCR official API as a det_vlm primary transcriber (--primary paddle, R10).

Uploads a rendered page image in local-file (multipart) mode, polls the job, fetches the result
JSONL, and returns the concatenated Markdown text. The HTTP
client is injectable (the repo's ProviderHttpClient in real runs, a fake in tests). Credentials
come from settings (.env PADDLE_BASE_URL / PADDLE_API_KEY) and are NEVER hard-coded.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable

from parse_anything.providers import HttpRequest, _join_url, _paddle_jobs_url, is_success_status

_DEFAULT_MODEL = "PaddleOCR-VL-1.6"
_OPTIONAL_PAYLOAD = {"useDocOrientationClassify": False, "useDocUnwarping": False, "useChartRecognition": False}


class PaddleError(RuntimeError):
    """Opaque PaddleOCR failure (e.g. paddle_submit_429, paddle_job_failed)."""


def _multipart(png: bytes, fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----odlvl" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    chunks.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="page.png"\r\n'
        f"Content-Type: image/png\r\n\r\n".encode("utf-8")
    )
    chunks.append(png)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _data(response: Any) -> dict[str, Any]:
    if not is_success_status(response.status_code):
        raise PaddleError(f"paddle_http_{response.status_code}")
    return json.loads(response.body)["data"]


def transcribe(
    png: bytes, *, client: Any, base_url: str, token: str, model: str = _DEFAULT_MODEL,
    poll_interval: float = 5.0, max_polls: int = 120,
) -> str:
    jobs_url = _paddle_jobs_url(base_url)
    auth = {"Authorization": f"bearer {token}"}

    body, content_type = _multipart(png, {"model": model, "optionalPayload": json.dumps(_OPTIONAL_PAYLOAD)})
    job_id = _data(client.send(HttpRequest("POST", jobs_url, {**auth, "Content-Type": content_type}, body))).get("jobId")
    if not job_id:
        raise PaddleError("paddle_no_job_id")

    json_url = ""
    for _ in range(max_polls):
        data = _data(client.send(HttpRequest("GET", _join_url(jobs_url, str(job_id)), auth, b"")))
        state = data.get("state")
        if state == "done":
            json_url = data.get("resultUrl", {}).get("jsonUrl", "")
            break
        if state == "failed":
            raise PaddleError("paddle_job_failed")
        time.sleep(poll_interval)
    if not json_url:
        raise PaddleError("paddle_poll_timeout")

    result = client.send(HttpRequest("GET", json_url, {}, b""))
    if not is_success_status(result.status_code):
        raise PaddleError(f"paddle_result_{result.status_code}")
    texts: list[str] = []
    for line in result.body.decode("utf-8").strip().split("\n"):
        if not line.strip():
            continue
        for parsed in json.loads(line)["result"]["layoutParsingResults"]:
            texts.append(parsed["markdown"]["text"])
    return "\n".join(texts)


def make_transcriber(client: Any, *, base_url: str, token: str, model: str = _DEFAULT_MODEL) -> Callable[[bytes], str]:
    """A png -> text callable for det_vlm's injectable primary transcriber (--primary paddle, R10)."""
    return lambda png: transcribe(png, client=client, base_url=base_url, token=token, model=model)
