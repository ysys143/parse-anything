"""Numeric-integrity guards (graduated from measurement prototypes).

Evidence: docs/measurement-findings.md F4-F8. Contract: processing-tiers R-V, R-B3.
Each guard is a pure function over already-extracted values; thresholds are arguments
(R-A7 — no hardcoded policy). The guards do not decide escalation by themselves; they
surface signals that the tier-boundary policy and the review tooling consume.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

_NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?")


def normalize_number(token: str) -> str:
    """Canonical form for comparison: strip grouping commas and surrounding space."""
    return token.strip().replace(",", "")


def extract_numbers(text: str, *, min_value: float | None = None) -> list[str]:
    """All numeric tokens in reading order, normalized. Optionally keep only >= min_value."""
    out = []
    for m in _NUMBER_RE.finditer(text):
        norm = normalize_number(m.group(0))
        if min_value is None or _as_float(norm) >= min_value:
            out.append(norm)
    return out


def _as_float(norm: str) -> float:
    try:
        return float(norm)
    except ValueError:
        return float("nan")


def source_gate(values: Iterable[str], source: Iterable[str]) -> list[str]:
    """Born-digital value gate (F5): return the values NOT present in the deterministic
    source (text layer) -- i.e. fabrication-suspect. On born-digital tables this flagged
    every fabricated number with zero false flags. Inputs are normalized before compare.
    """
    src = {normalize_number(s) for s in source}
    return [v for v in values if normalize_number(v) not in src]


def sum_residual(line_items: Sequence[float], total: float) -> float:
    """abs(sum(line_items) - total). A nonzero residual means the extracted line items do
    not reconcile with the stated total (F7) -- only meaningful for tables that HAVE such
    an arithmetic relationship (financial/quotation), never a universal check.
    """
    return abs(sum(line_items) - total)


def ratio_holds(base: float, derived: float, ratio: float, *, rel_tol: float = 5e-4) -> bool:
    """Whether ``derived == base * ratio`` within rel_tol (e.g. VAT-inclusive = exclusive
    * 1.1). A broken ratio across two independently-stated totals is an integrity signal;
    note a model can still fabricate a self-consistent pair, so this is one signal, not a
    proof (F7).
    """
    return abs(derived - base * ratio) <= max(1.0, abs(base * ratio) * rel_tol)
