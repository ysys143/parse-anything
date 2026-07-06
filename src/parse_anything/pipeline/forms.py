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
from collections.abc import Callable

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


def _merge_column_run(first: dict, column: list[dict], lh: float, *,
                      stop: "Callable[[dict], bool] | None" = None, max_lines: int = 3) -> tuple[str, list[float]]:
    """Absorb a vertical stack of value lines (B1b/B3b, e.g. a two-line address): starting at ``first``,
    keep adding the next ``column`` block ONLY if it looks like a continuation of the same value -- sits
    directly under the tail (0..lh gap), is LEFT-ALIGNED with ``first`` (x0 within lh), is not much WIDER
    than it (<=2.5x, so a full-width body paragraph is excluded), stays in the column band, and the run is
    under ``max_lines``. ``column`` is sorted top-to-bottom, contains ``first``, and MAY include the next
    field's label/key as a barrier (``stop(b)`` True ends the run before it). These guards stop a value
    from swallowing an unrelated line below, a different column's value, or the next field (adversarial
    review). Returns the newline-joined text and unioned bbox."""
    fx0 = first["bbox"][0]
    fw = max(first["bbox"][2] - first["bbox"][0], lh)
    run = [first]
    started = False
    for b in column:
        if b is first:
            started = True
            continue
        if not started:
            continue
        if (stop is not None and stop(b)) or len(run) >= max_lines:
            break
        gap = b["bbox"][1] - run[-1]["bbox"][3]
        if gap > lh:
            break                                        # a real gap -> the value stack has ended
        if (gap >= -1.0 and abs(b["bbox"][0] - fx0) <= lh                      # left-aligned continuation
                and (b["bbox"][2] - b["bbox"][0]) <= fw * 2.5                  # not a wide body paragraph
                and _col_overlap(run[-1]["bbox"], b["bbox"]) >= 0.3):
            run.append(b)
    text = "\n".join((r.get("text") or "").strip() for r in run)
    bb = [min(r["bbox"][0] for r in run), min(r["bbox"][1] for r in run),
          max(r["bbox"][2] for r in run), max(r["bbox"][3] for r in run)]
    return text, bb


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
        # 2) else the nearest non-empty block directly below, in the column band (V3 distance-bounded for
        #    the FIRST line; a multi-line value then extends downward by adjacency, B1b)
        value_text, value_bbox = None, None
        if val is not None:
            value_text, value_bbox = (val.get("text") or "").strip(), val["bbox"]
        else:
            col = sorted((b for b in blocks if b is not lab and _nonempty(b) and b["bbox"][1] >= ly1 - 1
                          and _col_overlap(lab["bbox"], b["bbox"]) >= 0.3),
                         key=lambda b: (b["bbox"][1], b["bbox"][0]))       # INCLUDES labels as barriers
            val = next((b for b in col if not _is_label(b.get("text", ""))
                        and b["bbox"][1] - ly1 <= max_below_factor * lh), None)
            if val is not None:                                            # join stacked value lines, but a
                value_text, value_bbox = _merge_column_run(                # value never leaks past the next
                    val, col, lh, stop=lambda b: _is_label(b.get("text", "")))  # field's label

        if val is None:
            continue
        fields.append({
            "label": _LABEL_RE.sub("", lab["text"]).strip(),
            "value": value_text, "label_bbox": lab["bbox"], "value_bbox": value_bbox,
            "label_id": lab.get("id"), "value_id": val.get("id"),
        })
    return fields


def detect_form_fields_gated(blocks: list[dict], *, min_fields: int = 3) -> list[dict]:
    """Wire-safe entry (V5): only returns fields when the page actually looks like a form -- at least
    ``min_fields`` aligned KV pairs. A page of prose with an incidental colon yields fewer -> ``[]``."""
    fields = detect_form_fields(blocks)
    return fields if len(fields) >= min_fields else []
