from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    provider: str
    model_alias: str
    route_reason: str
    latency_ms: float
    status: str
    cost_estimate_usd: float | None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def event_payload(event: LedgerEvent) -> dict[str, Any]:
    # Faithful serialization: the ledger records exactly what the orchestrator and
    # providers supply. Keeping secrets out of the ledger is a source responsibility
    # (error codes are opaque and providers emit only non-secret metadata) backed by a
    # .gitignore on the run artifacts -- not a runtime scrubbing pass that would also
    # mangle benign long identifiers.
    payload: dict[str, Any] = {
        "provider": event.provider,
        "model_alias": event.model_alias,
        "route_reason": event.route_reason,
        "latency_ms": event.latency_ms,
        "status": event.status,
        "cost_estimate_usd": event.cost_estimate_usd,
    }
    if event.metadata:
        payload["metadata"] = dict(event.metadata)
    return payload


def append_ledger_event(path: str | Path, event: LedgerEvent) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as ledger_file:
        ledger_file.write(json.dumps(event_payload(event), sort_keys=True, separators=(",", ":")))
        ledger_file.write("\n")
