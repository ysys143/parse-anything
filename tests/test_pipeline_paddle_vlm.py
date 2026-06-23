from __future__ import annotations

import json

import pytest

from odl_vl.pipeline.paddle_vlm import PaddleError, make_transcriber, transcribe
from odl_vl.providers import HttpResponse

_BASE = "https://paddleocr.aistudio-app.com"


def _ok(payload) -> HttpResponse:
    return HttpResponse(status_code=200, body=json.dumps(payload).encode("utf-8"))


class _FakePaddle:
    def __init__(self, jsonl: str, *, fail: bool = False):
        self.jsonl = jsonl
        self.fail = fail
        self.calls = []

    def send(self, req):
        self.calls.append((req.method, req.url))
        if req.method == "POST":                                   # multipart submit
            assert b"PNGDATA" in req.body and "multipart/form-data" in req.headers["Content-Type"]
            return _ok({"data": {"jobId": "job-1"}})
        if req.url.endswith("/job-1"):                              # poll
            if self.fail:
                return _ok({"data": {"state": "failed", "errorMsg": "boom"}})
            return _ok({"data": {"state": "done", "resultUrl": {"jsonUrl": f"{_BASE}/r.jsonl"}}})
        return HttpResponse(status_code=200, body=self.jsonl.encode("utf-8"))  # result fetch


def _jsonl(text: str) -> str:
    return json.dumps({"result": {"layoutParsingResults": [{"markdown": {"text": text}}]}})


def test_paddle_transcribe_uploads_polls_and_returns_text():
    client = _FakePaddle(_jsonl("recovered value 12345"))
    text = transcribe(b"PNGDATA", client=client, base_url=_BASE, token="secret", poll_interval=0)
    assert text == "recovered value 12345"
    assert client.calls[0][0] == "POST"                            # local-file multipart submit


def test_make_transcriber_is_a_png_to_text_callable():
    client = _FakePaddle(_jsonl("ok"))
    fn = make_transcriber(client, base_url=_BASE, token="secret")
    assert callable(fn) and fn(b"PNGDATA") == "ok"


def test_paddle_failed_job_raises():
    client = _FakePaddle(_jsonl("x"), fail=True)
    with pytest.raises(PaddleError):
        transcribe(b"PNGDATA", client=client, base_url=_BASE, token="secret", poll_interval=0)
