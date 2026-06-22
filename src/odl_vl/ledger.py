from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_LONG_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?=[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_-]))"
    r"(?=[A-Za-z0-9_-]*[0-9_-])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_-])"
)
_SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|signature|authorization|credential)", re.IGNORECASE)
_SIGNED_URL_QUERY_RE = re.compile(r"(x-amz-signature|signature|token|expires|x-goog-signature)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    provider: str
    model_alias: str
    route_reason: str
    latency_ms: float
    status: str
    fallback: bool
    cost_estimate_usd: float | None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def redacted_event(event: LedgerEvent) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": event.provider,
        "model_alias": event.model_alias,
        "route_reason": event.route_reason,
        "latency_ms": event.latency_ms,
        "status": event.status,
        "fallback": event.fallback,
        "cost_estimate_usd": event.cost_estimate_usd,
    }
    metadata = _redacted_mapping(event.metadata)
    if metadata:
        payload["metadata"] = metadata
    return payload


def append_ledger_event(path: str | Path, event: LedgerEvent) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as ledger_file:
        ledger_file.write(json.dumps(redacted_event(event), sort_keys=True, separators=(",", ":")))
        ledger_file.write("\n")


def _redacted_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in values.items():
        if _is_secret_key(key):
            continue
        safe_value = _redacted_value(value)
        if safe_value is not None:
            redacted[key] = safe_value
    return redacted


def _redacted_value(value: Any) -> Any:
    if isinstance(value, str):
        if _is_signed_url(value):
            return None
        return _LONG_TOKEN_RE.sub("[REDACTED]", value)
    if isinstance(value, Mapping):
        return _redacted_mapping(value)
    if isinstance(value, list):
        redacted_items = (_redacted_value(item) for item in value)
        return [item for item in redacted_items if item is not None]
    if isinstance(value, tuple):
        return tuple(item for item in (_redacted_value(item) for item in value) if item is not None)
    return value


def _is_secret_key(key: str) -> bool:
    return _SECRET_KEY_RE.search(key) is not None


def _is_signed_url(value: str) -> bool:
    if not value.startswith(("http://", "https://")):
        return False
    return _SIGNED_URL_QUERY_RE.search(value) is not None
