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


def detect_dimensions(tokens: list[dict], *, include_lengths: "bool | str" = "auto") -> list[dict]:
    """``tokens``: ``[{text, bbox?}]``. Returns ``[{value, kind, bbox?}]``. Shaped dimensions are always
    extracted; bare lengths only when >=2 shaped dims exist (``"auto"``) or ``include_lengths=True``.
    Not doc-type gated -- use ``detect_dimensions_gated`` at call sites (V5)."""
    out, claimed_by_tok = _shaped(tokens)
    want_lengths = include_lengths is True or (include_lengths == "auto" and len(out) >= 2)
    if want_lengths:
        for tok, claimed in zip(tokens, claimed_by_tok):
            text = tok.get("text") or ""
            for m in _LENGTH.finditer(text):
                if _overlaps(m.start(), m.end(), claimed):
                    continue
                out.append({"value": m.group(0).strip(), "kind": "length", "bbox": tok.get("bbox")})
    return out


def detect_dimensions_gated(tokens: list[dict], *, min_shaped: int = 2) -> list[dict]:
    """Wire-safe entry (V5): returns dimensions only when the tokens carry drawing context -- at least
    ``min_shaped`` shaped dimensions. A prose page with a stray "R5"/"20°" yields fewer -> ``[]``."""
    shaped, _ = _shaped(tokens)
    return detect_dimensions(tokens, include_lengths=True) if len(shaped) >= min_shaped else []
