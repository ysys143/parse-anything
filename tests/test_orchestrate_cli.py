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


def _write_live_input(tmp_path: Path) -> Path:
    # Live mode fetches/hands off the page image over HTTP, so a live input needs
    # http(s) page_image URLs. These are inert, non-resolvable hosts (the FakeTransport
    # returns canned responses); they live in tmp_path, never in committed fixtures.
    doc = tmp_path / "live_input.json"
    doc.write_text(
        json.dumps(
            {
                "document_id": "live-orchestrator-doc",
                "pages": [
                    {
                        "page_id": "p1-simple",
                        "page_index": 0,
                        "fixture_family": "simple_text",
                        "page_image": "https://images.invalid/simple_text/page-0.png",
                        "first_pass_md": "# Quarterly Notes\n\nBorn-digital body text.",
                    },
                    {
                        "page_id": "p2-table",
                        "page_index": 1,
                        "fixture_family": "merged_table",
                        "page_image": "https://images.invalid/merged_table/page-0.png",
                        "first_pass_md": "## Measurements\n\n| Group | Value |\n| --- | --- |\n| A | 1 |",
                    },
                    {
                        "page_id": "p3-chart",
                        "page_index": 2,
                        "fixture_family": "chart_like_page",
                        "page_image": "https://images.invalid/chart_like_page/page-0.png",
                        "first_pass_md": "Figure 1. Revenue trend.",
                        "intent_prompt": "Summarize the chart trend and legend.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return doc


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
    live_input = _write_live_input(tmp_path)
    signed_url = "https://signed.example/result.json?X-Amz-Signature=must-not-leak"
    transport = FakeTransport(
        responses=[
            # paddle submit
            _json_response({"code": 0, "msg": "Success", "data": {"jobId": "job-123"}}),
            # paddle poll -> done, result behind a signed URL
            _json_response({"data": {"state": "done", "resultUrl": {"jsonUrl": signed_url}}}),
            # paddle signed-URL result fetch
            _json_response({"result": {"layoutParsingResults": [{"markdown": {"text": "live paddle md"}}]}}),
            # gemini fetches the page image first, then calls generateContent
            HttpResponse(status_code=200, body=b"\x89PNG\r\n\x1a\nfake-image-bytes"),
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
        ["--input", str(live_input), "--output-dir", str(output_dir), "--mode", "live"],
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
    # The Gemini request must actually carry the page image (inlineData), not just text.
    gemini_post = transport.requests[-1]
    assert b"inlineData" in gemini_post.body
    assert b"fake-image-bytes" not in gemini_post.body  # sent base64-encoded, not raw
    # Secrets must never leak into ledger output.
    ledger = (output_dir / "ledger.jsonl").read_text(encoding="utf-8")
    assert "fake-gemini-secret-value" not in ledger
    assert "fake-paddle-secret-value" not in ledger
    assert "X-Amz-Signature" not in ledger
    assert "signed.example" not in ledger


def test_offline_cli_does_not_overwrite_slug_colliding_pages(tmp_path):
    # Given two page_ids that slug to the same string at the same page_index.
    module = _load_module()
    doc = tmp_path / "doc.json"
    doc.write_text(
        json.dumps(
            {
                "document_id": "collide",
                "pages": [
                    {
                        "page_id": "doc.1",
                        "page_index": 0,
                        "fixture_family": "simple_text",
                        "page_image": "fixtures://a.png",
                        "first_pass_md": "# first page body",
                    },
                    {
                        "page_id": "doc-1",
                        "page_index": 0,
                        "fixture_family": "simple_text",
                        "page_image": "fixtures://b.png",
                        "first_pass_md": "# second page body",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    # When
    module.run_cli(["--input", str(doc), "--output-dir", str(output_dir), "--mode", "offline"], module.Runtime(environ={}, stdout=io.StringIO()))

    # Then: both pages keep distinct markdown files (no silent overwrite).
    markdown_files = sorted((output_dir / "pages").glob("*.md"))
    assert len(markdown_files) == 2
    bodies = {f.read_text(encoding="utf-8") for f in markdown_files}
    assert bodies == {"# first page body", "# second page body"}


def test_cli_rejects_manifest_without_families(tmp_path):
    # Given a syntactically valid manifest that is missing the 'families' mapping.
    module = _load_module()
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    runtime = module.Runtime(environ={}, stdout=io.StringIO())

    # When
    code = module.run_cli(
        [
            "--input", str(_SAMPLE),
            "--output-dir", str(tmp_path / "out"),
            "--mode", "offline",
            "--manifest", str(bad_manifest),
        ],
        runtime,
    )

    # Then: a clear error instead of silently routing every page to deterministic.
    assert code == 2
    assert "families" in runtime.stdout.getvalue()


def test_cli_rejects_manifest_with_non_string_expected_route(tmp_path):
    # Given a manifest whose family has a non-string expected_route (typo as a list).
    module = _load_module()
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text(
        json.dumps({"families": {"simple_text": {"expected_route": ["paddle_ocr"]}}}), encoding="utf-8"
    )
    runtime = module.Runtime(environ={}, stdout=io.StringIO())

    # When
    code = module.run_cli(
        ["--input", str(_SAMPLE), "--output-dir", str(tmp_path / "out"),
         "--mode", "offline", "--manifest", str(bad_manifest)],
        runtime,
    )

    # Then: a clear manifest error instead of a per-page TypeError.
    assert code == 2
    assert "expected_route" in runtime.stdout.getvalue()


def test_cli_rejects_manifest_with_unknown_expected_route_value(tmp_path):
    # Given a manifest family with a typo'd expected_route value.
    module = _load_module()
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text(
        json.dumps({"families": {"simple_text": {"expected_route": "paddleocr"}}}), encoding="utf-8"
    )
    runtime = module.Runtime(environ={}, stdout=io.StringIO())

    # When
    code = module.run_cli(
        ["--input", str(_SAMPLE), "--output-dir", str(tmp_path / "out"),
         "--mode", "offline", "--manifest", str(bad_manifest)],
        runtime,
    )

    # Then: a clear manifest error instead of failing every page of that family.
    assert code == 2
    assert "expected_route" in runtime.stdout.getvalue()


def test_live_cli_paddle_200_without_job_id_reports_distinct_error(tmp_path):
    # Given a Paddle submit that returns HTTP 200 but no recognizable job id.
    module = _load_module()
    output_dir = tmp_path / "out"
    live_input = _write_live_input(tmp_path)
    transport = FakeTransport(
        responses=[
            _json_response({"code": 0, "msg": "Success", "data": {}}),  # p2 paddle 200, no jobId -> fail
            _json_response({"candidates": [{"content": {"parts": [{"text": "g"}]}}]}),  # p3 gemini ok
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
    module.run_cli(["--input", str(live_input), "--output-dir", str(output_dir), "--mode", "live"], runtime)

    # Then: a 200 submit with no job id is reported distinctly (not paddle_submit_200).
    results = {record["page_id"]: record for record in _read_results(output_dir)}
    assert results["p2-table"]["status"] == "failed"
    assert "paddle_submit_no_job_id" in results["p2-table"]["error"]


def test_live_cli_empty_paddle_result_marks_page_failed(tmp_path):
    # Given a Paddle result that is valid JSON but has no recognizable layout (empty markdown).
    module = _load_module()
    output_dir = tmp_path / "out"
    live_input = _write_live_input(tmp_path)
    transport = FakeTransport(
        responses=[
            _json_response({"code": 0, "msg": "Success", "data": {"jobId": "job-1"}}),
            _json_response({"data": {"state": "done", "resultUrl": {"jsonUrl": "https://signed.example/r"}}}),
            _json_response({"result": {"unexpectedShape": []}}),  # JSON, but no layoutParsingResults
            _json_response({"candidates": [{"content": {"parts": [{"text": "g"}]}}]}),  # p3 gemini ok
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
    module.run_cli(["--input", str(live_input), "--output-dir", str(output_dir), "--mode", "live"], runtime)

    # Then: an empty result is a failure, not a silently blank "ok" page.
    results = {record["page_id"]: record for record in _read_results(output_dir)}
    assert results["p2-table"]["status"] == "failed"
    assert "paddle_empty_result" in results["p2-table"]["error"]


def test_live_cli_non_json_paddle_result_marks_page_failed(tmp_path):
    # Given a Paddle job whose signed result URL returns a non-JSON (HTML) 200 body.
    module = _load_module()
    output_dir = tmp_path / "out"
    live_input = _write_live_input(tmp_path)
    transport = FakeTransport(
        responses=[
            _json_response({"code": 0, "msg": "Success", "data": {"jobId": "job-1"}}),
            _json_response({"data": {"state": "done", "resultUrl": {"jsonUrl": "https://signed.example/r"}}}),
            HttpResponse(status_code=200, body=b"<html>upstream error</html>"),  # p2 result not JSON -> fail
            _json_response({"candidates": [{"content": {"parts": [{"text": "g"}]}}]}),  # p3 gemini ok
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
    module.run_cli(["--input", str(live_input), "--output-dir", str(output_dir), "--mode", "live"], runtime)

    # Then: an empty/non-JSON result is a failure, not a silent empty "ok" page.
    results = {record["page_id"]: record for record in _read_results(output_dir)}
    assert results["p2-table"]["status"] == "failed"
    assert "paddle_result_not_json" in results["p2-table"]["error"]


def test_live_cli_gemini_empty_text_marks_page_failed(tmp_path):
    # Given a Paddle path that succeeds and a Gemini 200 with no candidate text.
    module = _load_module()
    output_dir = tmp_path / "out"
    live_input = _write_live_input(tmp_path)
    transport = FakeTransport(
        responses=[
            _json_response({"code": 0, "msg": "Success", "data": {"jobId": "job-1"}}),
            _json_response({"data": {"state": "done", "resultUrl": {"jsonUrl": "https://signed.example/r"}}}),
            _json_response({"result": {"layoutParsingResults": [{"markdown": {"text": "paddle ok"}}]}}),
            HttpResponse(status_code=200, body=b"fake-image-bytes"),  # gemini image fetch
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
        ["--input", str(live_input), "--output-dir", str(output_dir), "--mode", "live"],
        runtime,
    )

    # Then
    assert code == 1
    results = {record["page_id"]: record for record in _read_results(output_dir)}
    assert results["p2-table"]["status"] == "ok"
    assert results["p3-chart"]["status"] == "failed"
    assert results["p3-chart"]["error"] == "gemini_empty_text"  # specific reason preserved


def test_live_cli_missing_keys_marks_pages_failed(tmp_path):
    # Given
    module = _load_module()
    output_dir = tmp_path / "out"
    live_input = _write_live_input(tmp_path)
    runtime = module.Runtime(environ={}, transport=FakeTransport(responses=[]), stdout=io.StringIO())

    # When
    code = module.run_cli(
        ["--input", str(live_input), "--output-dir", str(output_dir), "--mode", "live"],
        runtime,
    )

    # Then
    assert code == 1
    results = {record["page_id"]: record for record in _read_results(output_dir)}
    # Deterministic page still succeeds with no provider keys.
    assert results["p1-simple"]["status"] == "ok"
    assert results["p2-table"]["status"] == "failed"
    assert results["p3-chart"]["status"] == "failed"


def test_live_cli_non_http_page_image_reports_clear_error(tmp_path):
    # Given a live run over the offline sample, whose page_image values are non-http
    # fixtures:// references (live mode must fetch/hand off the image over HTTP).
    module = _load_module()
    output_dir = tmp_path / "out"
    runtime = module.Runtime(
        environ={
            "GEMINI_API_KEY": "fake-gemini-secret-value",
            "PADDLE_API_KEY": "fake-paddle-secret-value",
            "PADDLE_BASE_URL": "https://paddle.example/api/v2/ocr/jobs",
        },
        transport=FakeTransport(responses=[]),
        stdout=io.StringIO(),
        sleep=lambda _seconds: None,
    )

    # When
    code = module.run_cli(
        ["--input", str(_SAMPLE), "--output-dir", str(output_dir), "--mode", "live"],
        runtime,
    )

    # Then: a clear, secret-free reason instead of an opaque fetch_0 status.
    assert code == 1
    results = {record["page_id"]: record for record in _read_results(output_dir)}
    assert results["p2-table"]["error"] == "paddle_image_non_http_url"
    assert results["p3-chart"]["error"] == "gemini_image_non_http_url"


def test_live_cli_gemini_accepts_lowercase_content_type_header(tmp_path):
    # Given a Gemini page whose image fetch returns a lowercased 'content-type' header
    # (HTTP header names are case-insensitive; the server may use any casing).
    module = _load_module()
    output_dir = tmp_path / "out"
    live_input = _write_live_input(tmp_path)
    transport = FakeTransport(
        responses=[
            _json_response({"code": 0, "msg": "Success", "data": {"jobId": "job-1"}}),
            _json_response({"data": {"state": "done", "resultUrl": {"jsonUrl": "https://signed.example/r"}}}),
            _json_response({"result": {"layoutParsingResults": [{"markdown": {"text": "paddle ok"}}]}}),
            HttpResponse(
                status_code=200,
                body=b"\x89PNG\r\n\x1a\nfake-image-bytes",
                headers={"content-type": "image/jpeg"},
            ),
            _json_response({"candidates": [{"content": {"parts": [{"text": "g"}]}}]}),
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
        ["--input", str(live_input), "--output-dir", str(output_dir), "--mode", "live"],
        runtime,
    )

    # Then: the lowercase header is honored, so the Gemini request carries image/jpeg.
    assert code == 0
    gemini_post = transport.requests[-1]
    assert b"image/jpeg" in gemini_post.body
