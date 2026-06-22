from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from odl_vl.secret_patterns import SECRET_KEY_NAME_RE, SIGNED_URL_QUERY_RE, redact_secrets


# Sentinel distinguishing "drop this key" (secret/signed URL) from a legitimate None.
_DROP = object()


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
        if safe_value is _DROP:
            continue
        redacted[key] = safe_value
    return redacted


def _redacted_value(value: Any) -> Any:
    if isinstance(value, str):
        if _is_signed_url(value):
            return _DROP
        return redact_secrets(value)
    if isinstance(value, Mapping):
        return _redacted_mapping(value)
    if isinstance(value, list):
        return [item for item in (_redacted_value(v) for v in value) if item is not _DROP]
    if isinstance(value, tuple):
        return tuple(item for item in (_redacted_value(v) for v in value) if item is not _DROP)
    return value


def _is_secret_key(key: str) -> bool:
    return SECRET_KEY_NAME_RE.search(key) is not None


def _is_signed_url(value: str) -> bool:
    if not value.startswith(("http://", "https://")):
        return False
    return SIGNED_URL_QUERY_RE.search(value) is not None
