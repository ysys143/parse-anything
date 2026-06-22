from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odl_vl.router import RoutingTask


_REQUIRED_PAGE_FIELDS: tuple[str, ...] = (
    "page_id",
    "page_index",
    "first_pass_md",
    "page_image",
    "fixture_family",
)


@dataclass(frozen=True, slots=True)
class PageInput:
    page_id: str
    page_index: int
    first_pass_md: str
    page_image: str
    fixture_family: str
    intent_prompt: str | None = None
    has_text_layer: bool | None = True
    needs_table_structure: bool = False
    needs_image_description: bool = False
    is_rotated_or_scan: bool = False
    is_low_quality_scan: bool = False

    def routing_task(self) -> RoutingTask:
        return RoutingTask(
            fixture_family=self.fixture_family,
            has_text_layer=self.has_text_layer,
            needs_table_structure=self.needs_table_structure,
            needs_image_description=self.needs_image_description,
            is_rotated_or_scan=self.is_rotated_or_scan,
            is_low_quality_scan=self.is_low_quality_scan,
        )


@dataclass(frozen=True, slots=True)
class DocumentInput:
    document_id: str
    pages: tuple[PageInput, ...]


def load_document_input(path: str | Path) -> DocumentInput:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"document input is not valid JSON: {error}") from error
    return parse_document_input(payload)


def parse_document_input(payload: Any) -> DocumentInput:
    if not isinstance(payload, Mapping):
        raise ValueError("document input must be a JSON object")

    document_id = _require_str(payload, "document_id", context="document")
    raw_pages = payload.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        raise ValueError("document input requires a non-empty 'pages' list")

    pages = tuple(_parse_page(entry, index) for index, entry in enumerate(raw_pages))
    return DocumentInput(document_id=document_id, pages=pages)


def _parse_page(entry: Any, position: int) -> PageInput:
    context = f"pages[{position}]"
    if not isinstance(entry, Mapping):
        raise ValueError(f"{context} must be a JSON object")

    for field_name in _REQUIRED_PAGE_FIELDS:
        if field_name not in entry:
            raise ValueError(f"{context} is missing required field '{field_name}'")

    return PageInput(
        page_id=_require_str(entry, "page_id", context=context),
        page_index=_require_int(entry, "page_index", context=context),
        first_pass_md=_require_str(entry, "first_pass_md", context=context, allow_empty=True),
        page_image=_require_str(entry, "page_image", context=context),
        fixture_family=_require_str(entry, "fixture_family", context=context),
        intent_prompt=_optional_str(entry, "intent_prompt", context=context),
        has_text_layer=_optional_tristate_bool(entry, "has_text_layer", context=context),
        needs_table_structure=_optional_bool(entry, "needs_table_structure", context=context),
        needs_image_description=_optional_bool(entry, "needs_image_description", context=context),
        is_rotated_or_scan=_optional_bool(entry, "is_rotated_or_scan", context=context),
        is_low_quality_scan=_optional_bool(entry, "is_low_quality_scan", context=context),
    )


def _require_str(values: Mapping[str, Any], key: str, *, context: str, allow_empty: bool = False) -> str:
    value = values.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{context} field '{key}' must be a string")
    if not allow_empty and value.strip() == "":
        raise ValueError(f"{context} field '{key}' must not be empty")
    return value


def _require_int(values: Mapping[str, Any], key: str, *, context: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} field '{key}' must be an integer")
    if value < 0:
        raise ValueError(f"{context} field '{key}' must be a non-negative integer")
    return value


def _optional_str(values: Mapping[str, Any], key: str, *, context: str) -> str | None:
    if key not in values or values[key] is None:
        return None
    value = values[key]
    if not isinstance(value, str):
        raise ValueError(f"{context} field '{key}' must be a string when present")
    return value


def _optional_bool(values: Mapping[str, Any], key: str, *, context: str) -> bool:
    if key not in values or values[key] is None:
        return False
    value = values[key]
    if not isinstance(value, bool):
        raise ValueError(f"{context} field '{key}' must be a boolean when present")
    return value


def _optional_tristate_bool(values: Mapping[str, Any], key: str, *, context: str) -> bool | None:
    if key not in values:
        return True
    value = values[key]
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{context} field '{key}' must be a boolean or null")
    return value
