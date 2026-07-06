"""Deterministic engineering-drawing dimension extraction (FR-5.1).

Classifies dimension callouts from already-extracted text tokens (OCR / text layer) by shape: diameter
(Ø/φ/dia), radius (R), angle (deg), tolerance (±). Pure regex over token text -- no VLM; values are
quoted, never generated (§5-C).

Bare LENGTH numbers (114.5, 50.5) share their shape with page numbers and prices, so they are emitted
ONLY when the token set already carries at least TWO shaped dimensions (a real drawing has many) or the
caller forces it -- a lone stray "R5" in prose cannot cascade every number into a "length" (adversarial
review V4).

WIRE-TIME GATE (V5, blocker): shaped patterns still have prose false positives ("R2" register, "20°C" is
excluded but "R1 note" is not). Do NOT run this over arbitrary pages -- call ``detect_dimensions_gated``
(requires drawing context: >=2 shaped dims) and/or restrict to drawing-kind figures. Residual limits:
a title-block phone/date can split into length pieces; a lone radius token in prose still emits one FP.
"""
from __future__ import annotations

import re

_SHAPED: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("diameter", re.compile(r"(?:Ø|φ|dia\.?)\s*\d+(?:\.\d+)?(?:\s*[-+]\d+(?:\.\d+)?)?", re.IGNORECASE)),
    ("radius", re.compile(r"\bR\s*\d+(?:\.\d+)?\b")),
    ("angle", re.compile(r"\d+(?:\.\d+)?\s*(?:°(?![CFNSEW])|deg(?:rees?)?\b)", re.IGNORECASE)),
    ("tolerance", re.compile(r"±\s*\d+(?:\.\d+)?")),
)
# plain length: comma-grouped OR decimal; never adjacent to a letter/digit/comma/colon/dot (so "12,345"
# stays whole, "16:9" and "12:30" don't split into dimensions, and no signed suffix eats a phone number).
_LENGTH = re.compile(r"(?<![A-Za-z\d.,:°])(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![A-Za-z\d.,:°])")


def _overlaps(s: int, e: int, claimed: list[tuple[int, int]]) -> bool:
    return any(not (e <= cs or s >= ce) for cs, ce in claimed)


def _shaped(tokens: list[dict]) -> tuple[list[dict], list[list[tuple[int, int]]]]:
    out: list[dict] = []
    claimed_by_tok: list[list[tuple[int, int]]] = []
    for tok in tokens:
        text = tok.get("text") or ""
        claimed: list[tuple[int, int]] = []
        for kind, rx in _SHAPED:
            for m in rx.finditer(text):
                if _overlaps(m.start(), m.end(), claimed):
                    continue
                claimed.append((m.start(), m.end()))
                out.append({"value": m.group(0).strip(), "kind": kind, "bbox": tok.get("bbox")})
        claimed_by_tok.append(claimed)
    return out, claimed_by_tok


def _drawing_context(shaped: list[dict]) -> bool:
    """A genuine drawing signal: a DIAMETER (Ø/φ -- essentially never in prose) or >=2 degree-SYMBOL
    angles. Radius (``R2`` = R-squared / revision / section), spelled ``deg``, and ``±`` (mean ± sd) are
    all common in prose, so they do NOT establish drawing context on their own -- otherwise a statistics
    page cascades every bare number into a phantom 'length' (adversarial review, wiring). They are still
    extracted once a real drawing is established."""
    dia = sum(1 for r in shaped if r["kind"] == "diameter")
    ang = sum(1 for r in shaped if r["kind"] == "angle" and "°" in r["value"])
    return dia >= 1 or ang >= 2


def detect_dimensions(tokens: list[dict], *, include_lengths: "bool | str" = "auto") -> list[dict]:
    """``tokens``: ``[{text, bbox?}]``. Returns ``[{value, kind, bbox?}]``. Shaped dimensions are always
    extracted; bare lengths only under drawing context (a diameter or >=2 degree-symbol angles) when
    ``"auto"``, or unconditionally when ``include_lengths=True``. Not doc-type gated -- use
    ``detect_dimensions_gated`` at call sites."""
    out, claimed_by_tok = _shaped(tokens)
    want_lengths = include_lengths is True or (include_lengths == "auto" and _drawing_context(out))
    if want_lengths:
        for tok, claimed in zip(tokens, claimed_by_tok):
            text = tok.get("text") or ""
            for m in _LENGTH.finditer(text):
                if _overlaps(m.start(), m.end(), claimed):
                    continue
                out.append({"value": m.group(0).strip(), "kind": "length", "bbox": tok.get("bbox")})
    return out


def reconcile_dimensions(dims: list[dict], *, chain_window: float = 0.02) -> "dict | None":
    """§5-B arithmetic CANDIDATE: the largest length may be an overall size and the rest its chain, so
    when their sum lands within ``chain_window`` of it, return ``{total, parts, sum, residual}`` -- a
    NUMERIC candidate, NOT a geometrically verified chain. This is deliberately un-authoritative: with no
    collinearity/axis check, coincidentally-equal unrelated features (300 = 100+100+100) or ordinate
    (running) dimensions can produce a spurious candidate, and a real chain in comma or non-max units can
    be missed. A consumer must treat ``residual`` as a hint (0 = clean, nonzero = a discrepancy worth a
    look, e.g. the reference parser's 137+678+715 = 1530 vs 1529), never as proof. Verifying the chain
    geometrically is future work."""
    lengths = sorted(v for d in dims if d.get("kind") == "length" and (v := _leading_number(d["value"])) is not None)
    if len(lengths) < 3:
        return None
    total, parts = lengths[-1], lengths[:-1]
    s = sum(parts)
    residual = abs(s - total)
    if total <= 0 or residual > chain_window * total:     # not a plausible chain to this total -> no claim
        return None
    return {"total": total, "parts": parts, "sum": round(s, 3), "residual": round(residual, 3)}


def _leading_number(value: str) -> "float | None":
    # match the same shape detect_dimensions emits for a length -- keep thousands groups whole (12,345)
    m = re.match(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", value.strip())
    return float(m.group(0).replace(",", "")) if m else None


def detect_dimensions_gated(tokens: list[dict]) -> list[dict]:
    """Wire-safe entry: returns dimensions ONLY when the tokens carry genuine drawing context (a diameter
    or >=2 degree-symbol angles). A prose page with a stray ``R2``/``±``/spelled ``deg`` establishes no
    context -> ``[]``, so statistics/science pages surface no phantom dimensions."""
    shaped, _ = _shaped(tokens)
    return detect_dimensions(tokens, include_lengths=True) if _drawing_context(shaped) else []
