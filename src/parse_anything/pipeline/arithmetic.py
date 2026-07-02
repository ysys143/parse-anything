"""Arithmetic-invariant guard (F7, pdf-pipeline-requirements §6).

For tables that HAVE an arithmetic relationship -- a total/subtotal row -- verify that each
numeric column's data rows sum to the stated total. This is NEVER a universal check: it returns
None when no total row is present, so it only fires on financial/quotation-style tables. A broken
sum (residual above tolerance) is a review signal, not a correction.
"""
from __future__ import annotations

from typing import Any

from .guards import normalize_number, sum_residual

_TOTAL_WORDS = ("합계", "총계", "소계", "총합", "계", "total", "subtotal", "sum")


def _to_float(text: str) -> float | None:
    try:
        return float(normalize_number(text))
    except (ValueError, AttributeError):
        return None


def _is_total_label(text: str) -> bool:
    low = (text or "").strip().lower()
    return bool(low) and any(word in low for word in _TOTAL_WORDS)


def check_table_arithmetic(cells: list[list[str]], *, rel_tol: float = 1e-3) -> dict[str, Any] | None:
    """Return a per-column sum check for the table's total row, or None if there is no total row
    (or nothing checkable). ``cells`` is a row-major text grid."""
    rows = [list(r) for r in cells]
    total_idx = next((i for i, r in enumerate(rows) if r and _is_total_label(r[0])), None)
    if not total_idx:  # None or 0 (a total row with no data above it is not checkable)
        return None

    data, total_row = rows[:total_idx], rows[total_idx]
    n_cols = max((len(r) for r in rows), default=0)
    checks: list[dict[str, Any]] = []
    for col in range(1, n_cols):  # column 0 is the label
        total_val = _to_float(total_row[col]) if col < len(total_row) else None
        items = [v for r in data if col < len(r) and (v := _to_float(r[col])) is not None]
        if total_val is None or len(items) < 2:
            continue
        residual = sum_residual(items, total_val)
        tol = max(abs(total_val) * rel_tol, 0.5)
        checks.append({
            "column": col, "total": total_val, "line_sum": round(sum(items), 4),
            "residual": round(residual, 4), "ok": residual <= tol,
        })
    if not checks:
        return None
    return {"kind": "column_sum", "checks": checks, "ok": all(c["ok"] for c in checks)}
