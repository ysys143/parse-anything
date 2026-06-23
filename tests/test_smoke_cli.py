from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from odl_vl.providers import HttpRequest, HttpResponse


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "odl_vl_smoke.py"


def _load_smoke_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("odl_vl_smoke", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["odl_vl_smoke"] = module
    spec.loader.exec_module(module)
    return module


@dataclass(slots=True)
class FakeTransport:
    responses: list[HttpResponse]
    requests: list[HttpRequest] = field(default_factory=list)

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return self.responses.pop(0)


@dataclass(slots=True)
class RaisingTransport:
    requests: list[HttpRequest] = field(default_factory=list)

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        raise urllib.error.HTTPError(
            url="https://signed.example.invalid/path?token=response-body-must-not-print",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )


def test_dry_config_reports_presence_and_hosts_without_secret_values():
    # Given
    module = _load_smoke_module()
    output = io.StringIO()
    runtime = module.Runtime(
        environ={
            "GEMINI_API_KEY": "fake-gemini-secret",
            "PADDLE_API_KEY": "fake-paddle-secret",
            "PADDLE_BASE_URL": "https://paddle.example.invalid/private/path",
            "PADDLE_MODEL": "PaddleOCR-VL-1.6-test",
        },
        transport=FakeTransport([]),
        stdout=output,
        sleep=lambda seconds: None,
    )

    # When
    gemini_exit = module.run_cli(["--provider", "gemini", "--dry-config"], runtime)
    paddle_exit = module.run_cli(["--provider", "paddle", "--dry-config"], runtime)

    # Then
    rendered = output.getvalue()
    assert gemini_exit == 0
    assert paddle_exit == 0
    assert "provider=gemini" in rendered
    assert "provider=paddle" in rendered
    assert "api_key=present" in rendered
    assert "model=gemini-3.1-flash-lite" in rendered
    assert "model=PaddleOCR-VL-1.6-test" in rendered
    assert "base_url_host=generativelanguage.googleapis.com" in rendered
    assert "base_url_host=paddle.example.invalid" in rendered
    assert "fake-gemini-secret" not in rendered
    assert "fake-paddle-secret" not in rendered
    assert "private/path" not in rendered


def test_live_gemini_sends_minimal_prompt_and_does_not_print_response_body():
    # Given
    module = _load_smoke_module()
    output = io.StringIO()
    response_body = {
        "candidates": [
            {"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"},
        ],
        "echoField": "response-body-must-not-print",
    }
    transport = FakeTransport([HttpResponse(status_code=200, body=json.dumps(response_body).encode())])
    runtime = module.Runtime(
        environ={"GEMINI_API_KEY": "fake-gemini-secret"},
        transport=transport,
        stdout=output,
        sleep=lambda seconds: None,
    )

    # When
    exit_code = module.run_cli(["--provider", "gemini", "--live"], runtime)

    # Then
    assert exit_code == 0
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.headers["x-goog-api-key"] == "fake-gemini-secret"
    assert "Authorization" not in request.headers
    assert json.loads(request.body.decode()) == {"contents": [{"parts": [{"text": "Return exactly: ok"}]}]}
    rendered = output.getvalue()
    assert rendered.strip() == "provider=gemini live=pass status=200 text=ok"
    assert "fake-gemini-secret" not in rendered
    assert "response-body-must-not-print" not in rendered


def test_live_gemini_accepts_2xx_other_than_200():
    # Given a 2xx (not exactly 200) Gemini success with valid 'ok' text.
    module = _load_smoke_module()
    output = io.StringIO()
    response_body = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
    transport = FakeTransport([HttpResponse(status_code=201, body=json.dumps(response_body).encode())])
    runtime = module.Runtime(
        environ={"GEMINI_API_KEY": "fake-gemini-secret"},
        transport=transport,
        stdout=output,
        sleep=lambda seconds: None,
    )

    # When
    exit_code = module.run_cli(["--provider", "gemini", "--live"], runtime)

    # Then: any 2xx is treated as success, not just 200.
    assert exit_code == 0
    assert "live=pass status=201 text=ok" in output.getvalue()


def test_live_paddle_submits_demo_url_and_polls_without_downloading_results():
    # Given
    module = _load_smoke_module()
    output = io.StringIO()
    transport = FakeTransport(
        [
            HttpResponse(status_code=202, body=b'{"data":{"jobId":"job-123","status":"queued"}}'),
            HttpResponse(status_code=200, body=b'{"data":{"status":"running"}}'),
            HttpResponse(
                status_code=200,
                body=b'{"data":{"status":"completed","resultUrl":"https://signed.example.invalid/file?token=secret"}}',
            ),
        ]
    )
    runtime = module.Runtime(
        environ={
            "PADDLE_API_KEY": "fake-paddle-secret",
            "PADDLE_BASE_URL": "https://paddle.example.invalid",
        },
        transport=transport,
        stdout=output,
        sleep=lambda seconds: None,
    )

    # When
    exit_code = module.run_cli(["--provider", "paddle", "--live", "--timeout", "3"], runtime)

    # Then
    assert exit_code == 0
    assert [request.method for request in transport.requests] == ["POST", "GET", "GET"]
    submit_payload = json.loads(transport.requests[0].body.decode())
    assert submit_payload["fileUrl"] == module.DEFAULT_PADDLE_DEMO_URL
    assert submit_payload["model"] == "PaddleOCR-VL-1.6"
    assert all(request.body == b"" for request in transport.requests[1:])
    rendered = output.getvalue()
    assert rendered.strip() == "provider=paddle live=pass submit_status=202 poll_status=completed polls=2"
    assert "fake-paddle-secret" not in rendered
    assert "signed.example.invalid" not in rendered
    assert "token=secret" not in rendered


def test_live_paddle_poll_http_error_ignores_done_body():
    # Given
    module = _load_smoke_module()
    output = io.StringIO()
    transport = FakeTransport(
        [
            HttpResponse(status_code=202, body=b'{"data":{"jobId":"job-500","status":"queued"}}'),
            HttpResponse(
                status_code=500,
                body=b'{"data":{"status":"done","resultUrl":"https://signed.example.invalid/file?token=secret"}}',
            ),
        ]
    )
    runtime = module.Runtime(
        environ={
            "PADDLE_API_KEY": "fake-paddle-secret",
            "PADDLE_BASE_URL": "https://paddle.example.invalid/api/v2/ocr/jobs",
        },
        transport=transport,
        stdout=output,
        sleep=lambda seconds: None,
    )

    # When
    exit_code = module.run_cli(["--provider", "paddle", "--live", "--timeout", "3"], runtime)

    # Then
    rendered = output.getvalue()
    assert exit_code == 1
    assert rendered.strip() == "provider=paddle live=fail submit_status=202 poll_status=http_500 polls=1"
    assert "live=pass" not in rendered
    assert "fake-paddle-secret" not in rendered
    assert "signed.example.invalid" not in rendered
    assert "token=secret" not in rendered


def test_live_http_error_prints_opaque_failure_without_traceback():
    # Given
    module = _load_smoke_module()
    output = io.StringIO()
    runtime = module.Runtime(
        environ={"GEMINI_API_KEY": "fake-gemini-secret"},
        transport=RaisingTransport(),
        stdout=output,
        sleep=lambda seconds: None,
    )

    # When
    exit_code = module.run_cli(["--provider", "gemini", "--live"], runtime)

    # Then
    rendered = output.getvalue()
    assert exit_code == 1
    assert rendered.strip() == "provider=gemini live=fail status=401"
    assert "Traceback" not in rendered
    assert "fake-gemini-secret" not in rendered
    assert "signed.example.invalid" not in rendered
    assert "response-body-must-not-print" not in rendered
