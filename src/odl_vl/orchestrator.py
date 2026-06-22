from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, assert_never

from odl_vl.ir import NormalizedPage, ProviderName
from odl_vl.ledger import LedgerEvent, append_ledger_event
from odl_vl.normalizers import normalize_deterministic
from odl_vl.orchestrator_input import DocumentInput, PageInput
from odl_vl.providers import DEFAULT_GEMINI_MODEL, DEFAULT_PADDLE_MODEL
from odl_vl.router import RouteDecision, choose_route
from odl_vl.secret_patterns import redact_secrets


ProviderCallable = Callable[[PageInput, RouteDecision], NormalizedPage]
Clock = Callable[[], float]

_UNKNOWN_PROVIDER = "unknown"


class _FallbackExhausted(RuntimeError):
    """Raised when a fallback-eligible route's primary and alternate both fail.

    Lets the page record that a fallback was actually attempted even though it failed.
    """


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
    provider: ProviderName | str
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
            "route_reason": redact_secrets(self.route_reason),
            "fallback": self.fallback,
            "status": self.status,
            "error": redact_secrets(self.error) if self.error is not None else None,
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
    max_workers: int = 1


def orchestrate_document(document: DocumentInput, config: OrchestratorConfig) -> list[PageResult]:
    pages = document.pages
    if config.max_workers <= 1 or len(pages) <= 1:
        lock = threading.Lock()
        return [_process_page(page, config, lock) for page in pages]

    # Pages are independent; run them concurrently while keeping output order and
    # serializing the shared ledger append.
    lock = threading.Lock()
    results: list[PageResult | None] = [None] * len(pages)
    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        futures = {executor.submit(_process_page, page, config, lock): index for index, page in enumerate(pages)}
        for future in futures:
            results[futures[future]] = future.result()
    return [result for result in results if result is not None]


def _process_page(page: PageInput, config: OrchestratorConfig, ledger_lock: threading.Lock) -> PageResult:
    family_meta = config.family_metadata.get(page.fixture_family, {})
    decision: RouteDecision | None = None
    actual_provider: ProviderName | None = None
    fallback_used = False
    start = config.clock()
    try:
        # Routing is inside the try so a malformed manifest family fails only this
        # page instead of aborting the whole run.
        decision = choose_route(page.routing_task(), family_meta)
        actual_provider = decision.provider  # default if the call below raises
        normalized, actual_provider, fallback_used = _run_with_fallback(page, decision, config)
        status = "ok"
        error: str | None = None
    except Exception as exc:  # routing or provider failure becomes a failed page result
        normalized = None
        status = "failed"
        # A fallback that was attempted but also failed is still a fallback.
        fallback_used = isinstance(exc, _FallbackExhausted)
        # Keep the provider's specific message (e.g. "gemini_http_429"); fall back
        # to the class name for exceptions with no message.
        error = str(exc) or type(exc).__name__
    latency_ms = max(0.0, (config.clock() - start) * 1000.0)

    provider_label = str(actual_provider) if actual_provider is not None else _UNKNOWN_PROVIDER
    route_reason = decision.reason if decision is not None else f"route_error:{error}"
    model_alias = (
        config.model_aliases.get(actual_provider, provider_label)
        if actual_provider is not None
        else _UNKNOWN_PROVIDER
    )

    event = LedgerEvent(
        provider=provider_label,
        model_alias=model_alias,
        route_reason=route_reason,
        latency_ms=latency_ms,
        status=status,
        fallback=fallback_used,
        cost_estimate_usd=None,
        metadata=_ledger_metadata(page, normalized),
    )
    if config.ledger_path is not None:
        # A ledger write failure must not abort the run: OSError (disk full,
        # read-only dir) or a serialization error (TypeError/ValueError on exotic
        # metadata) only loses that one audit line.
        try:
            with ledger_lock:
                append_ledger_event(config.ledger_path, event)
        except (OSError, TypeError, ValueError):
            pass

    return PageResult(
        page_id=page.page_id,
        page_index=page.page_index,
        fixture_family=page.fixture_family,
        provider=provider_label,
        route_reason=route_reason,
        fallback=fallback_used,
        status=status,
        normalized=normalized,
        error=error,
    )


def _run_with_fallback(
    page: PageInput, decision: RouteDecision, config: OrchestratorConfig
) -> tuple[NormalizedPage, ProviderName, bool]:
    """Run the routed provider; on failure, try the alternate provider when the route allows it.

    Returns (normalized page, provider that actually produced it, whether fallback was used).
    """
    try:
        return _call_provider(decision.provider, page, decision, config), decision.provider, False
    except Exception as primary_exc:
        alternate = _fallback_provider(decision.provider) if decision.fallback else None
        if alternate is None:
            raise
        # Primary failed but the hybrid route allows a second provider.
        try:
            return _call_provider(alternate, page, decision, config), alternate, True
        except Exception as fallback_exc:
            # Preserve both failures (and the fact a fallback was attempted).
            raise _FallbackExhausted(
                f"{decision.provider}:{primary_exc} | fallback {alternate}:{fallback_exc}"
            ) from fallback_exc


def _fallback_provider(primary: ProviderName) -> ProviderName | None:
    match primary:
        case ProviderName.PADDLE:
            return ProviderName.GEMINI
        case ProviderName.GEMINI:
            return ProviderName.PADDLE
        case ProviderName.DETERMINISTIC:
            return None


def _call_provider(
    provider: ProviderName, page: PageInput, decision: RouteDecision, config: OrchestratorConfig
) -> NormalizedPage:
    match provider:
        case ProviderName.DETERMINISTIC:
            run = config.deterministic_provider or _default_deterministic
            return run(page, decision)
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
