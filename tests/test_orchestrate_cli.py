from __future__ import annotations

import importlib.util
import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from odl_vl.providers import HttpRequest, HttpResponse


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "odl_vl_orchestrate.py"
_SAMPLE = _REPO_ROOT / "tests" / "fixtures" / "orchestrator" / "sample_document.json"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("odl_vl_orchestrate", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["odl_vl_orchestrate"] = module
    spec.loader.exec_module(module)
    return module


@dataclass(slots=True)
class FakeTransport:
    responses: list[HttpResponse]
    requests: list[HttpRequest] = field(default_factory=list)

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def _json_response(payload: dict) -> HttpResponse:
    return HttpResponse(status_code=200, body=json.dumps(payload).encode("utf-8"))


def _read_results(output_dir: Path) -> list[dict]:
    lines = (output_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_offline_cli_writes_results_ledger_and_markdown(tmp_path):
    # Given
    module = _load_module()
    output_dir = tmp_path / "out"
    runtime = module.Runtime(environ={}, stdout=io.StringIO())

    # When
    code = module.run_cli(
        ["--input", str(_SAMPLE), "--output-dir", str(output_dir), "--mode", "offline"],
        runtime,
    )

    # Then
    assert code == 0
    results = _read_results(output_dir)
    assert len(results) == 3
    providers = {record["provider"] for record in results}
    assert providers == {"deterministic", "paddle", "gemini"}
    assert (output_dir / "ledger.jsonl").exists()
    markdown_files = list((output_dir / "pages").glob("*.md"))
    assert len(markdown_files) == 3
    summary = runtime.stdout.getvalue()
    assert "pages=3" in summary
    assert "mode=offline" in summary


def test_offline_cli_ledger_has_no_secret_values(tmp_path):
    # Given
    module = _load_module()
    output_dir = tmp_path / "out"
    runtime = module.Runtime(environ={}, stdout=io.StringIO())

    # When
    module.run_cli(
        ["--input", str(_SAMPLE), "--output-dir", str(output_dir), "--mode", "offline"],
        runtime,
    )
    ledger = (output_dir / "ledger.jsonl").read_text(encoding="utf-8")

    # Then
    records = [json.loads(line) for line in ledger.splitlines()]
    assert len(records) == 3
    for record in records:
        assert {"provider", "model_alias", "route_reason", "status"} <= set(record)
    assert "api_key" not in ledger.lower()


def test_live_cli_calls_providers_through_transport(tmp_path):
    # Given
    module = _load_module()
    output_dir = tmp_path / "out"
    signed_url = "https://signed.example/result.json?X-Amz-Signature=must-not-leak"
    transport = FakeTransport(
        responses=[
            # paddle submit
            _json_response({"code": 0, "msg": "Success", "data": {"jobId": "job-123"}}),
            # paddle poll -> done, result behind a signed URL
            _json_response({"data": {"state": "done", "resultUrl": {"jsonUrl": signed_url}}}),
            # paddle signed-URL result fetch
            _json_response({"result": {"layoutParsingResults": [{"markdown": {"text": "live paddle md"}}]}}),
            # gemini generateContent
            _json_response({"candidates": [{"content": {"parts": [{"text": "live gemini md"}]}}]}),
        ]
    )
    runtime = module.Runtime(
        environ={
            "GEMINI_API_KEY": "fake-gemini-secret-value",
            "PADDLE_API_KEY": "fake-paddle-secret-value",
            "PADDLE_BASE_URL": "https://paddle.example/api/v2/ocr/jobs",
        },
        transport=transport,
        stdout=io.StringIO(),
        sleep=lambda _seconds: None,
    )

    # When
    code = module.run_cli(
        ["--input", str(_SAMPLE), "--output-dir", str(output_dir), "--mode", "live"],
        runtime,
    )

    # Then
    assert code == 0
    results = {record["page_id"]: record for record in _read_results(output_dir)}
    assert results["p2-table"]["provider"] == "paddle"
    assert results["p3-chart"]["provider"] == "gemini"
    paddle_md = (output_dir / "pages" / "page-001-p2-table.md").read_text(encoding="utf-8")
    gemini_md = (output_dir / "pages" / "page-002-p3-chart.md").read_text(encoding="utf-8")
    assert "live paddle md" in paddle_md
    assert "live gemini md" in gemini_md
    # Secrets must never leak into ledger output.
    ledger = (output_dir / "ledger.jsonl").read_text(encoding="utf-8")
    assert "fake-gemini-secret-value" not in ledger
    assert "fake-paddle-secret-value" not in ledger
    assert "X-Amz-Signature" not in ledger
    assert "signed.example" not in ledger


def test_live_cli_gemini_empty_text_marks_page_failed(tmp_path):
    # Given a Paddle path that succeeds and a Gemini 200 with no candidate text.
    module = _load_module()
    output_dir = tmp_path / "out"
    transport = FakeTransport(
        responses=[
            _json_response({"code": 0, "msg": "Success", "data": {"jobId": "job-1"}}),
            _json_response({"data": {"state": "done", "resultUrl": {"jsonUrl": "https://signed.example/r"}}}),
            _json_response({"result": {"layoutParsingResults": [{"markdown": {"text": "paddle ok"}}]}}),
            _json_response({"candidates": []}),  # gemini 200 but empty -> must fail, not silent empty
        ]
    )
    runtime = module.Runtime(
        environ={
            "GEMINI_API_KEY": "fake-gemini-secret-value",
            "PADDLE_API_KEY": "fake-paddle-secret-value",
            "PADDLE_BASE_URL": "https://paddle.example/api/v2/ocr/jobs",
        },
        transport=transport,
        stdout=io.StringIO(),
        sleep=lambda _seconds: None,
    )

    # When
    code = module.run_cli(
        ["--input", str(_SAMPLE), "--output-dir", str(output_dir), "--mode", "live"],
        runtime,
    )

    # Then
    assert code == 1
    results = {record["page_id"]: record for record in _read_results(output_dir)}
    assert results["p2-table"]["status"] == "ok"
    assert results["p3-chart"]["status"] == "failed"
    assert results["p3-chart"]["error"] == "RuntimeError"


def test_live_cli_missing_keys_marks_pages_failed(tmp_path):
    # Given
    module = _load_module()
    output_dir = tmp_path / "out"
    runtime = module.Runtime(environ={}, transport=FakeTransport(responses=[]), stdout=io.StringIO())

    # When
    code = module.run_cli(
        ["--input", str(_SAMPLE), "--output-dir", str(output_dir), "--mode", "live"],
        runtime,
    )

    # Then
    assert code == 1
    results = {record["page_id"]: record for record in _read_results(output_dir)}
    # Deterministic page still succeeds with no provider keys.
    assert results["p1-simple"]["status"] == "ok"
    assert results["p2-table"]["status"] == "failed"
    assert results["p3-chart"]["status"] == "failed"
