from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from pathlib import Path
from types import ModuleType


_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "orchestrator"
_SAMPLE = _FIXTURE_DIR / "sample_document.json"
_EXPECTED = _FIXTURE_DIR / "expected_results.json"
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "odl_vl_orchestrate.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("odl_vl_orchestrate", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["odl_vl_orchestrate"] = module
    spec.loader.exec_module(module)
    return module


def test_sample_document_has_three_named_pages():
    # Given
    document = json.loads(_SAMPLE.read_text(encoding="utf-8"))

    # Then
    families = [page["fixture_family"] for page in document["pages"]]
    assert families == ["simple_text", "merged_table", "chart_like_page"]


def test_offline_run_matches_golden_expectations(tmp_path):
    # Given
    module = _load_module()
    expected = json.loads(_EXPECTED.read_text(encoding="utf-8"))
    output_dir = tmp_path / "out"

    # When
    module.run_cli(
        ["--input", str(_SAMPLE), "--output-dir", str(output_dir), "--mode", "offline"],
        module.Runtime(environ={}, stdout=io.StringIO()),
    )
    produced = {
        record["page_id"]: record
        for record in (
            json.loads(line)
            for line in (output_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }

    # Then
    for golden in expected["pages"]:
        record = produced[golden["page_id"]]
        assert record["provider"] == golden["provider"]
        assert record["route_reason"] == golden["route_reason"]
        assert record["fallback"] == golden["fallback"]
        assert record["status"] == golden["status"]
        markdown = (output_dir / record["markdown_file"]).read_text(encoding="utf-8")
        assert golden["markdown_contains"] in markdown


def test_fixture_files_have_no_private_paths_or_signed_urls():
    # Given
    blob = _SAMPLE.read_text(encoding="utf-8") + _EXPECTED.read_text(encoding="utf-8")

    # Then
    assert "/Users/" not in blob
    assert "/home/" not in blob
    assert "X-Amz-Signature" not in blob
    assert "x-goog-signature" not in blob.lower()
    assert re.search(r"https?://", blob) is None
