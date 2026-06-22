from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, assert_never

from odl_vl.ir import NormalizedPage, ProviderName
from odl_vl.ledger import LedgerEvent, append_ledger_event
from odl_vl.normalizers import normalize_deterministic
from odl_vl.orchestrator_input import DocumentInput, PageInput
from odl_vl.providers import DEFAULT_GEMINI_MODEL, DEFAULT_PADDLE_MODEL
from odl_vl.router import RouteDecision, choose_route


ProviderCallable = Callable[[PageInput, RouteDecision], NormalizedPage]
Clock = Callable[[], float]


_MODEL_ALIASES: Mapping[ProviderName, str] = {
    ProviderName.DETERMINISTIC: "deterministic",
    ProviderName.PADDLE: DEFAULT_PADDLE_MODEL,
    ProviderName.GEMINI: DEFAULT_GEMINI_MODEL,
}


@dataclass(frozen=True, slots=True)
class PageResult:
    page_id: str
    page_index: int
    fixture_family: str
    provider: ProviderName
    route_reason: str
    fallback: bool
    status: str
    normalized: NormalizedPage | None
    error: str | None = None

    def to_record(self) -> dict[str, Any]:
        normalized = self.normalized
        return {
            "page_id": self.page_id,
            "page_index": self.page_index,
            "fixture_family": self.fixture_family,
            "provider": str(self.provider),
            "route_reason": self.route_reason,
            "fallback": self.fallback,
            "status": self.status,
            "error": self.error,
            "markdown_chars": len(normalized.markdown) if normalized is not None else 0,
            "image_description": normalized.image_description if normalized is not None else None,
            "confidence": normalized.confidence if normalized is not None else None,
        }


@dataclass(frozen=True, slots=True)
class OrchestratorConfig:
    family_metadata: Mapping[str, Mapping[str, object]]
    paddle_provider: ProviderCallable
    gemini_provider: ProviderCallable
    deterministic_provider: ProviderCallable | None = None
    ledger_path: str | Path | None = None
    clock: Clock = time.monotonic
    model_aliases: Mapping[ProviderName, str] = field(default_factory=lambda: dict(_MODEL_ALIASES))


def orchestrate_document(document: DocumentInput, config: OrchestratorConfig) -> list[PageResult]:
    return [_process_page(page, config) for page in document.pages]


def _process_page(page: PageInput, config: OrchestratorConfig) -> PageResult:
    family_meta = config.family_metadata.get(page.fixture_family, {})
    decision = choose_route(page.routing_task(), family_meta)

    start = config.clock()
    try:
        normalized = _run_provider(page, decision, config)
        status = "ok"
        error: str | None = None
    except Exception as exc:  # provider failure becomes a failed page result, never aborts the run
        normalized = None
        status = "failed"
        error = type(exc).__name__
    latency_ms = max(0.0, (config.clock() - start) * 1000.0)

    event = LedgerEvent(
        provider=str(decision.provider),
        model_alias=config.model_aliases.get(decision.provider, str(decision.provider)),
        route_reason=decision.reason,
        latency_ms=latency_ms,
        status=status,
        fallback=decision.fallback,
        cost_estimate_usd=None,
        metadata=_ledger_metadata(page, normalized),
    )
    if config.ledger_path is not None:
        append_ledger_event(config.ledger_path, event)

    return PageResult(
        page_id=page.page_id,
        page_index=page.page_index,
        fixture_family=page.fixture_family,
        provider=decision.provider,
        route_reason=decision.reason,
        fallback=decision.fallback,
        status=status,
        normalized=normalized,
        error=error,
    )


def _run_provider(page: PageInput, decision: RouteDecision, config: OrchestratorConfig) -> NormalizedPage:
    match decision.provider:
        case ProviderName.DETERMINISTIC:
            provider = config.deterministic_provider or _default_deterministic
            return provider(page, decision)
        case ProviderName.PADDLE:
            return config.paddle_provider(page, decision)
        case ProviderName.GEMINI:
            return config.gemini_provider(page, decision)
        case unreachable:
            assert_never(unreachable)


def _default_deterministic(page: PageInput, _decision: RouteDecision) -> NormalizedPage:
    return normalize_deterministic(page.first_pass_md)


def _ledger_metadata(page: PageInput, normalized: NormalizedPage | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "page_id": page.page_id,
        "page_index": page.page_index,
        "fixture_family": page.fixture_family,
    }
    if normalized is not None:
        metadata["markdown_chars"] = len(normalized.markdown)
        for key, value in normalized.ledger_view().items():
            metadata.setdefault(key, value)
    return metadata
