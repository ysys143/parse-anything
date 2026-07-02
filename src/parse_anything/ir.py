from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class ProviderName(StrEnum):
    DETERMINISTIC = "deterministic"
    PADDLE = "paddle"
    GEMINI = "gemini"


@dataclass(frozen=True, slots=True)
class BoundingBox:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True, slots=True)
class JsonElement:
    element_type: str
    text: str
    bbox: BoundingBox | None = None
    confidence: float | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VlmPassInput:
    page_image: str
    first_pass_md: str | None = None
    intent_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedPage:
    markdown: str
    json_elements: tuple[JsonElement, ...] = ()
    tables_html: tuple[str, ...] = ()
    image_description: str | None = None
    confidence: float | None = None
    provider: ProviderName = ProviderName.DETERMINISTIC
    ledger_fields: dict[str, Any] = field(default_factory=dict)

    def ledger_view(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(dict(self.ledger_fields))
