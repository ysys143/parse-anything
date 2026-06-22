from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


FIXTURE_DIR = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
GOLDEN_SCHEMA_PATH = FIXTURE_DIR / "golden_schema.json"

EXPECTED_FAMILIES = {
    "simple_text",
    "two_column_ko_en",
    "merged_table",
    "formula_symbols",
    "chart_like_page",
    "text_as_image",
    "rotated_scan",
    "low_quality_scan",
}

REQUIRED_FAMILY_FIELDS = {
    "expected_route",
    "primary_metric",
    "mutation_strategy",
    "expected_challenge",
    "source_type",
    "page_count",
    "language_profile",
    "generation_recipe",
    "scoring_targets",
    "expected_outputs",
    "route_rationale",
}

ALLOWED_ROUTES = {"deterministic_only", "paddle_ocr", "gemini_vlm", "hybrid"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    assert isinstance(data, dict)
    return data


def test_fixture_manifest_contains_exact_initial_families() -> None:
    manifest = load_json(MANIFEST_PATH)

    families = manifest.get("families")
    assert isinstance(families, dict)
    assert set(families) == EXPECTED_FAMILIES


def test_fixture_families_have_required_contract_fields() -> None:
    manifest = load_json(MANIFEST_PATH)
    families = manifest["families"]

    missing_fields = {
        family: sorted(REQUIRED_FAMILY_FIELDS - set(metadata))
        for family, metadata in families.items()
        if REQUIRED_FAMILY_FIELDS - set(metadata)
    }

    assert missing_fields == {}

    for metadata in families.values():
        assert metadata["expected_route"] in ALLOWED_ROUTES
        assert isinstance(metadata["primary_metric"], str)
        assert metadata["primary_metric"] in metadata["scoring_targets"]
        assert isinstance(metadata["mutation_strategy"], dict)
        assert metadata["mutation_strategy"]["baseline"] == "generated_synthetic"
        assert isinstance(metadata["expected_challenge"], str)
        assert metadata["page_count"] >= 1
        assert metadata["generation_recipe"]["artifact_status"] == "not_generated"
        assert metadata["generation_recipe"]["storage_policy"] == "repo_metadata_only"
        assert metadata["expected_outputs"]["golden_record"] == "page_level"


def test_fixture_manifest_route_distribution_is_explicit() -> None:
    manifest = load_json(MANIFEST_PATH)
    families = manifest["families"]

    route_distribution = Counter(
        metadata["expected_route"] for metadata in families.values()
    )

    assert manifest["route_distribution"] == dict(sorted(route_distribution.items()))


def test_golden_schema_documents_page_level_contract() -> None:
    schema = load_json(GOLDEN_SCHEMA_PATH)

    assert schema["schema_version"] == 1
    assert schema["record_scope"] == "page"
    assert schema["format"] == "json"
    assert schema["additional_dependencies"] == []
    assert set(schema["fixture_families"]) == EXPECTED_FAMILIES
    assert schema["required_page_fields"] == [
        "fixture_family",
        "page_index",
        "expected_route",
        "reading_order",
        "table_structure",
        "key_fields",
        "image_description_expectation",
        "bbox_tolerance",
        "provider_allowances",
        "scoring_metrics",
    ]


def test_manifest_references_golden_schema_version() -> None:
    manifest = load_json(MANIFEST_PATH)
    schema = load_json(GOLDEN_SCHEMA_PATH)

    assert manifest["golden_schema_version"] == schema["schema_version"]
