"""Deterministic form key-value pairing (FR-4.3).

A form label (a short, colon-terminated field name) is paired with its value block by geometry: the
nearest block to its RIGHT on the same row (the dominant form layout), else the nearest block directly
BELOW within a bounded distance. Purely geometric + the colon signal -- no VLM. Values are quoted
verbatim from the deterministic OCR / text layer, never generated, so entity fidelity (§5-C) holds for
the value *text*; the label->value *relation* is only as good as the layout, hence the guards below.

Precision guards (adversarial review V1-V4): short/non-URL/non-note label names; right-search stops at
the next field's label (a value can't lie beyond it); below-search is distance- and column-bounded;
empty values are dropped; ordering is deterministic.

WIRE-TIME GATE (V5, blocker): a lone colon in prose is shape-indistinguishable from a field. Do NOT run
the raw detector over arbitrary pages -- call ``detect_form_fields_gated`` (a density gate: a real form
has several aligned fields) and/or restrict to form-kind pages. AcroForm digital fields are a separate
future source (pypdfium2 exposes only a render-oriented PdfFormEnv; see backlog).
"""
from __future__ import annotations

import re

_LABEL_RE = re.compile(r"[:：]\s*$")  # a form label ends with a colon (ASCII or fullwidth)
_NOTE_LABELS = {"참고", "주의", "출처", "비고", "주", "예", "note", "caution", "cf", "ps"}  # notes, not fields


def _row_overlap(a: list[float], b: list[float]) -> float:
    """Vertical-overlap fraction of the SHORTER box -- how much two boxes share a row."""
    inter = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return inter / max(1e-6, min(a[3] - a[1], b[3] - b[1]))


def _col_overlap(a: list[float], b: list[float]) -> float:
    """Horizontal-overlap fraction of the NARROWER box -- how much two boxes share a column."""
    inter = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    return inter / max(1e-6, min(a[2] - a[0], b[2] - b[0]))


def _nonempty(b: dict) -> bool:
    return bool((b.get("text") or "").strip())


def _is_label(text: str) -> bool:
    """A colon-TERMINATED, short, field-name-like text. Rejects sentence-ending colons, URLs, and common
    notes ('참고:'/'주의:') -- a form field name is a short noun phrase (<=24 chars, <=4 words), not a
    clause or a note. Even so the CALLER must gate on form context (see ``detect_form_fields_gated``)."""
    t = (text or "").strip()
    if not _LABEL_RE.search(t) or "://" in t:
        return False
    body = _LABEL_RE.sub("", t).strip()
    if not body or len(body) > 24 or len(body.split()) > 4:
        return False
    return body.lower() not in _NOTE_LABELS


def detect_form_fields(blocks: list[dict], *, max_below_factor: float = 2.0) -> list[dict]:
    """``blocks``: ``[{text, bbox:[x0,y0,x1,y1], id?}]`` on ONE page. Returns
    ``[{label, value, label_bbox, value_bbox, label_id?, value_id?}]``. Pairing is deterministic and
    bounded; see module docstring. NOT form-gated -- use ``detect_form_fields_gated`` at call sites."""
    fields: list[dict] = []
    for lab in blocks:
        if not _is_label(lab.get("text", "")):
            continue
        _, _, lx1, ly1 = lab["bbox"]
        lh = max(lab["bbox"][3] - lab["bbox"][1], 1.0)
        # 1) same row, to the right -- but a value cannot lie beyond the NEXT field's label (V2d)
        right = sorted((b for b in blocks if b is not lab and b["bbox"][0] >= lx1 - 1
                        and _row_overlap(lab["bbox"], b["bbox"]) >= 0.5),
                       key=lambda b: (b["bbox"][0], b["bbox"][1], b.get("text", "")))
        val = None
        for b in right:
            if _is_label(b.get("text", "")):
                break                                   # next field starts here; this label has no right value
            if _nonempty(b):
                val = b
                break
        # 2) else the nearest non-empty block directly below, bounded in distance and column band (V3)
        if val is None:
            below = sorted((b for b in blocks if b is not lab and not _is_label(b.get("text", ""))
                            and _nonempty(b) and 0 <= b["bbox"][1] - ly1 <= max_below_factor * lh
                            and _col_overlap(lab["bbox"], b["bbox"]) >= 0.3),
                           key=lambda b: (b["bbox"][1], b["bbox"][0], b.get("text", "")))
            val = below[0] if below else None
        if val is None:
            continue
        fields.append({
            "label": _LABEL_RE.sub("", lab["text"]).strip(),
            "value": (val.get("text") or "").strip(),
            "label_bbox": lab["bbox"], "value_bbox": val["bbox"],
            "label_id": lab.get("id"), "value_id": val.get("id"),
        })
    return fields


def detect_form_fields_gated(blocks: list[dict], *, min_fields: int = 3) -> list[dict]:
    """Wire-safe entry (V5): only returns fields when the page actually looks like a form -- at least
    ``min_fields`` aligned KV pairs. A page of prose with an incidental colon yields fewer -> ``[]``."""
    fields = detect_form_fields(blocks)
    return fields if len(fields) >= min_fields else []
