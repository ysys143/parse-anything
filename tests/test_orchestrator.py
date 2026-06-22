from __future__ import annotations

import json
import re
from itertools import count

import pytest

from odl_vl.ir import NormalizedPage
from odl_vl.normalizers import normalize_gemini, normalize_paddle
from odl_vl.orchestrator import OrchestratorConfig, orchestrate_document
from odl_vl.orchestrator_input import parse_document_input


_FAMILY_METADATA = {
    "simple_text": {"expected_route": "deterministic_only"},
    "merged_table": {"expected_route": "hybrid"},
    "chart_like_page": {"expected_route": "gemini_vlm"},
}


def _document(pages: list[dict]) -> object:
    return parse_document_input({"document_id": "doc", "pages": pages})


def _page(page_id: str, index: int, family: str, **extra) -> dict:
    base = {
        "page_id": page_id,
        "page_index": index,
        "first_pass_md": f"first pass for {page_id}",
        "page_image": f"fixtures://{family}/page-{index}.png",
        "fixture_family": family,
    }
    base.update(extra)
    return base


def _fake_paddle(page, _decision) -> NormalizedPage:
    return normalize_paddle({"layoutParsingResults": [{"markdown": {"text": f"paddle:{page.page_id}"}}]})


def _fake_gemini(page, _decision) -> NormalizedPage:
    return normalize_gemini(f"gemini:{page.page_id}", image_description="desc")


def _stub_clock():
    counter = count(start=0)
    return lambda: float(next(counter))


def test_orchestrate_routes_each_provider_path(tmp_path):
    # Given
    document = _document(
        [
            _page("p1", 0, "simple_text"),
            _page("p2", 1, "merged_table"),
            _page("p3", 2, "chart_like_page"),
        ]
    )
    config = OrchestratorConfig(
        family_metadata=_FAMILY_METADATA,
        paddle_provider=_fake_paddle,
        gemini_provider=_fake_gemini,
        ledger_path=tmp_path / "ledger.jsonl",
        clock=_stub_clock(),
    )

    # When
    results = orchestrate_document(document, config)

    # Then
    providers = [str(result.provider) for result in results]
    assert providers == ["deterministic", "paddle", "gemini"]
    assert all(result.status == "ok" for result in results)
    # merged_table is hybrid (fallback-eligible) but paddle succeeds, so no fallback was used.
    assert results[1].fallback is False
    assert results[0].normalized.markdown == "first pass for p1"
    assert results[1].normalized.markdown == "paddle:p2"
    assert results[2].normalized.image_description == "desc"


def test_max_workers_preserves_order_and_processes_all_pages(tmp_path):
    # Given many pages and concurrent processing.
    document = _document([_page(f"p{i}", i, "simple_text") for i in range(12)])
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrchestratorConfig(
        family_metadata=_FAMILY_METADATA,
        paddle_provider=_fake_paddle,
        gemini_provider=_fake_gemini,
        ledger_path=ledger_path,
        max_workers=4,
    )

    # When
    results = orchestrate_document(document, config)

    # Then: output order matches input order and every page is processed once.
    assert [r.page_id for r in results] == [f"p{i}" for i in range(12)]
    assert all(r.status == "ok" for r in results)
    # Ledger append is serialized: one well-formed JSON line per page, no torn writes.
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 12
    assert all(json.loads(line)["provider"] == "deterministic" for line in lines)


def test_hybrid_page_falls_back_to_gemini_when_paddle_fails(tmp_path):
    # Given a hybrid (fallback-eligible) page whose paddle provider fails.
    def _failing_paddle(page, _decision) -> NormalizedPage:
        raise RuntimeError("paddle_poll_timeout")

    document = _document([_page("p2", 0, "merged_table")])
    config = OrchestratorConfig(
        family_metadata=_FAMILY_METADATA,
        paddle_provider=_failing_paddle,
        gemini_provider=_fake_gemini,
        ledger_path=tmp_path / "ledger.jsonl",
        clock=_stub_clock(),
    )

    # When
    results = orchestrate_document(document, config)

    # Then: the alternate provider produced the page and fallback is recorded as used.
    assert results[0].status == "ok"
    assert str(results[0].provider) == "gemini"
    assert results[0].fallback is True
    assert results[0].normalized.markdown == "gemini:p2"
    record = json.loads((tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["provider"] == "gemini"
    assert record["fallback"] is True


def test_hybrid_page_failed_when_both_providers_fail(tmp_path):
    # Given a hybrid page where both primary and fallback providers fail.
    def _boom(page, _decision) -> NormalizedPage:
        raise RuntimeError("down")

    document = _document([_page("p2", 0, "merged_table")])
    config = OrchestratorConfig(
        family_metadata=_FAMILY_METADATA,
        paddle_provider=_boom,
        gemini_provider=_boom,
        ledger_path=tmp_path / "ledger.jsonl",
        clock=_stub_clock(),
    )

    # When
    results = orchestrate_document(document, config)

    # Then
    assert results[0].status == "failed"
    assert results[0].error == "down"


def test_provider_failure_becomes_failed_page(tmp_path):
    # Given
    def _boom(page, _decision) -> NormalizedPage:
        raise RuntimeError("provider exploded")

    document = _document([_page("p3", 0, "chart_like_page")])
    config = OrchestratorConfig(
        family_metadata=_FAMILY_METADATA,
        paddle_provider=_fake_paddle,
        gemini_provider=_boom,
        ledger_path=tmp_path / "ledger.jsonl",
        clock=_stub_clock(),
    )

    # When
    results = orchestrate_document(document, config)

    # Then
    assert results[0].status == "failed"
    assert results[0].error == "provider exploded"  # specific message preserved, not just the class
    assert results[0].normalized is None


def test_ledger_records_routes_without_secret_or_signed_url(tmp_path):
    # Given
    secret_like = "k" * 40

    def _leaky_gemini(page, _decision) -> NormalizedPage:
        return normalize_gemini(
            "gemini body",
            ledger_fields={
                "api_key": secret_like,
                "result_url": f"https://provider.example/r?X-Amz-Signature={'s' * 40}",
            },
        )

    document = _document([_page("p3", 0, "chart_like_page")])
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrchestratorConfig(
        family_metadata=_FAMILY_METADATA,
        paddle_provider=_fake_paddle,
        gemini_provider=_leaky_gemini,
        ledger_path=ledger_path,
        clock=_stub_clock(),
    )

    # When
    orchestrate_document(document, config)
    contents = ledger_path.read_text(encoding="utf-8")

    # Then
    records = [json.loads(line) for line in contents.splitlines()]
    assert len(records) == 1
    assert records[0]["provider"] == "gemini"
    assert records[0]["route_reason"] == "fixture:chart_like_page expected gemini_vlm"
    assert "api_key" not in contents
    assert secret_like not in contents
    assert "X-Amz-Signature" not in contents
    assert "result_url" not in contents
    assert re.search(r"[A-Za-z0-9_-]{40,}", contents) is None


def test_malformed_manifest_family_fails_only_that_page(tmp_path):
    # Given a manifest where one family has an invalid expected_route.
    family_metadata = {
        "simple_text": {"expected_route": "deterministic_only"},
        "broken_family": {"expected_route": "not_a_real_route"},
    }
    document = _document(
        [
            _page("p1", 0, "simple_text"),
            _page("p2", 1, "broken_family"),
            _page("p3", 2, "simple_text"),
        ]
    )
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrchestratorConfig(
        family_metadata=family_metadata,
        paddle_provider=_fake_paddle,
        gemini_provider=_fake_gemini,
        ledger_path=ledger_path,
        clock=_stub_clock(),
    )

    # When
    results = orchestrate_document(document, config)

    # Then: the bad page fails, the run continues, good pages still succeed.
    assert [r.status for r in results] == ["ok", "failed", "ok"]
    assert results[1].provider == "unknown"
    assert results[1].route_reason.startswith("route_error:")
    records = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(records) == 3  # ledger written for every page including the failed one


def test_ledger_write_failure_does_not_abort_the_run(tmp_path):
    # Given a ledger path whose parent is a regular file, so the append raises OSError.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    document = _document([_page("p1", 0, "simple_text"), _page("p2", 1, "simple_text")])
    config = OrchestratorConfig(
        family_metadata=_FAMILY_METADATA,
        paddle_provider=_fake_paddle,
        gemini_provider=_fake_gemini,
        ledger_path=blocker / "ledger.jsonl",
        clock=_stub_clock(),
    )

    # When / Then: the run completes and returns results instead of crashing.
    results = orchestrate_document(document, config)
    assert [r.status for r in results] == ["ok", "ok"]


def test_ledger_latency_is_non_negative(tmp_path):
    # Given
    document = _document([_page("p1", 0, "simple_text")])
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrchestratorConfig(
        family_metadata=_FAMILY_METADATA,
        paddle_provider=_fake_paddle,
        gemini_provider=_fake_gemini,
        ledger_path=ledger_path,
        clock=_stub_clock(),
    )

    # When
    orchestrate_document(document, config)
    record = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[0])

    # Then
    assert record["latency_ms"] == pytest.approx(1000.0)
    assert record["fallback"] is False
