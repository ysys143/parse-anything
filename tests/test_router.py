from __future__ import annotations

import json

from odl_vl.router import RouteProvider, RoutingTask, choose_route


def _family_metadata(name: str) -> dict[str, object]:
    manifest = json.loads(open("tests/fixtures/manifest.json", encoding="utf-8").read())
    return manifest["families"][name]


def test_choose_route_uses_deterministic_for_simple_text_metadata():
    # Given
    task = RoutingTask(fixture_family="simple_text")

    # When
    decision = choose_route(task, family_metadata=_family_metadata("simple_text"))

    # Then
    assert decision.provider is RouteProvider.DETERMINISTIC
    assert decision.reason == "fixture:simple_text expected deterministic_only"
    assert decision.fallback is False


def test_choose_route_uses_gemini_for_chart_semantics_hint():
    # Given
    task = RoutingTask(fixture_family="chart_like_page", needs_image_description=True)

    # When
    decision = choose_route(task, family_metadata=_family_metadata("chart_like_page"))

    # Then
    assert decision.provider is RouteProvider.GEMINI
    assert decision.reason == "hint:needs_image_description"
    assert decision.fallback is False


def test_choose_route_uses_paddle_for_table_preservation_hint_on_hybrid_family():
    # Given
    task = RoutingTask(fixture_family="merged_table", needs_table_structure=True)

    # When
    decision = choose_route(task, family_metadata=_family_metadata("merged_table"))

    # Then
    assert decision.provider is RouteProvider.PADDLE
    assert decision.reason == "hint:needs_table_structure"
    # A hint is a deliberate route, so it is not fallback-eligible.
    assert decision.fallback is False


def test_choose_route_uses_paddle_for_missing_text_layer_hint():
    # Given
    task = RoutingTask(fixture_family="simple_text", has_text_layer=False)

    # When
    decision = choose_route(task, family_metadata=_family_metadata("simple_text"))

    # Then
    assert decision.provider is RouteProvider.PADDLE
    assert decision.reason == "hint:no_text_layer"
    assert decision.fallback is False


def test_choose_route_rejects_unknown_expected_route():
    # Given
    task = RoutingTask(fixture_family="unknown")


    # When / Then
    try:
        choose_route(task, family_metadata={"expected_route": "unexpected"})
    except ValueError as error:
        assert str(error) == "unsupported expected_route: unexpected"
    else:
        raise AssertionError("expected ValueError")
