from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from odl_vl.ir import ProviderName


RouteProvider = ProviderName


@dataclass(frozen=True, slots=True)
class RoutingTask:
    fixture_family: str | None = None
    has_text_layer: bool | None = True
    needs_table_structure: bool = False
    needs_image_description: bool = False
    is_rotated_or_scan: bool = False
    is_low_quality_scan: bool = False


@dataclass(frozen=True, slots=True)
class RouteDecision:
    provider: RouteProvider
    reason: str
    fallback: bool


def choose_route(task: RoutingTask, family_metadata: Mapping[str, object]) -> RouteDecision:
    expected_route = _expected_route(family_metadata)

    # A routing hint is a deliberate provider choice, so it is not fallback-eligible:
    # falling back to the other provider would contradict the hint (e.g. a page that
    # needs image description must not silently rerun through OCR-only Paddle).
    if task.needs_image_description:
        return RouteDecision(RouteProvider.GEMINI, "hint:needs_image_description", False)
    if task.has_text_layer is False:
        return RouteDecision(RouteProvider.PADDLE, "hint:no_text_layer", False)
    if task.needs_table_structure:
        return RouteDecision(RouteProvider.PADDLE, "hint:needs_table_structure", False)
    if task.is_rotated_or_scan:
        return RouteDecision(RouteProvider.PADDLE, "hint:rotated_or_scan", False)
    if task.is_low_quality_scan:
        return RouteDecision(RouteProvider.PADDLE, "hint:low_quality_scan", False)

    return _route_from_fixture(task.fixture_family, expected_route)


def _expected_route(family_metadata: Mapping[str, object]) -> str | None:
    value = family_metadata.get("expected_route")
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("expected_route must be a string")
    return value


def _route_from_fixture(fixture_family: str | None, expected_route: str | None) -> RouteDecision:
    family = fixture_family or "unknown"
    match expected_route:
        case "deterministic_only":
            return RouteDecision(
                RouteProvider.DETERMINISTIC,
                f"fixture:{family} expected deterministic_only",
                False,
            )
        case "paddle_ocr":
            return RouteDecision(RouteProvider.PADDLE, f"fixture:{family} expected paddle_ocr", False)
        case "gemini_vlm":
            return RouteDecision(RouteProvider.GEMINI, f"fixture:{family} expected gemini_vlm", False)
        case "hybrid":
            return RouteDecision(RouteProvider.PADDLE, f"fixture:{family} expected hybrid", True)
        case None:
            return RouteDecision(RouteProvider.DETERMINISTIC, "default:deterministic", False)
        case unexpected:
            raise ValueError(f"unsupported expected_route: {unexpected}")
