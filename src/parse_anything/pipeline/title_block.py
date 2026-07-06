"""Deterministic engineering-drawing title-block extraction (FR-5.2).

A title block is the ruled grid in the bottom-right of a drawing frame holding scale, material, sheet,
date, drawing number, etc. Unlike a form field it usually has NO colon -- label and value sit in adjacent
grid cells -- so pairing is driven by a dictionary of KNOWN, multilingual field keys (Maßstab / Scale /
축척 …) plus B1's geometry (value in the adjacent cell to the right, else below). Values are quoted, never
generated (§5-C).

WIRE-TIME GATE: use ``detect_title_block_gated`` (auto bottom-right region + field-density gate) so a
stray 'Material' heading in body text is not read as a title-block field. Limitations (B3b): a value
split across several OCR tokens keeps only the nearest one, and a right-aligned block (value LEFT of its
label) is not paired -- value-right / value-below is assumed.
"""
from __future__ import annotations

from .forms import _col_overlap, _row_overlap

# canonical field -> alias set (lowercased, punctuation/space stripped). Kept specific to avoid matching
# ordinary body words; generic aliases ("name") are intentionally omitted.
_TITLE_KEYS: dict[str, tuple[str, ...]] = {
    "scale": ("maßstab", "massstab", "masstab", "scale", "축척", "尺度"),
    "material": ("werkstoff", "material", "재질", "재료"),
    "sheet": ("blatt", "sheet", "장", "시트"),
    "date": ("datum", "date", "날짜", "일자"),
    "drawn_by": ("gezeichnet", "drawn", "작성", "작성자"),
    "drawing_no": ("zeichnungsnr", "dwgno", "도번", "도면번호", "drawingno"),
    "title": ("benennung", "품명", "명칭"),
    "tolerance_std": ("allgemeintoleranz", "generaltolerance", "일반공차"),
}
_ALIAS_TO_KEY = {a: k for k, aliases in _TITLE_KEYS.items() for a in aliases}
# generic English words ("scale"/"material"/…) collide with prose headings, so they only count when a
# spatial ``region`` pins the title block; drawing-specific terms (Maßstab/Werkstoff/축척/재질/…) are safe
# anywhere. This is the per-alias half of the wire-time gate.
_GENERIC_ALIASES = frozenset({"scale", "date", "material", "sheet", "drawn", "title", "generaltolerance"})


def _norm(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum() or "가" <= ch <= "힣")


def _in_region(bbox: list[float], region: "list[float] | None") -> bool:
    if region is None:
        return True
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]


def _matched_key(text: str, region: "list[float] | None") -> "str | None":
    alias = _norm(text)
    key = _ALIAS_TO_KEY.get(alias)
    if key is None or (alias in _GENERIC_ALIASES and region is None):  # generic words need spatial context
        return None
    return key


def detect_title_block(blocks: list[dict], *, region: "list[float] | None" = None,
                       max_below_factor: float = 3.0) -> dict:
    """``blocks``: ``[{text, bbox, id?}]``. Returns ``{canonical_key: {value, label_bbox, value_bbox}}``
    for each known title-block field whose value cell can be located (right on the row, else below in the
    column band, bounded in distance). ``region`` (bottom-right frame rect) restricts what counts as the
    title block AND enables the generic English aliases; without it only drawing-specific terms match."""
    scoped = [b for b in blocks if _in_region(b["bbox"], region)]
    keys = {id(b): k for b in scoped if (k := _matched_key(b.get("text", ""), region)) is not None}
    fields: dict = {}
    for lab in scoped:
        canonical = keys.get(id(lab))
        if canonical is None or canonical in fields:
            continue
        _, _, lx1, ly1 = lab["bbox"]
        lh = max(lab["bbox"][3] - lab["bbox"][1], 1.0)
        # same row, to the right -- but a value cannot lie beyond the NEXT field's key (V2d)
        right = sorted((b for b in scoped if b is not lab and b["bbox"][0] >= lx1 - 1
                        and _row_overlap(lab["bbox"], b["bbox"]) >= 0.5),
                       key=lambda b: (b["bbox"][0], b["bbox"][1]))
        val = None
        for b in right:
            if id(b) in keys:
                break                                   # next field's key; this key's value isn't past it
            if (b.get("text") or "").strip():
                val = b
                break
        if val is None:  # nearest non-key value below, within a bounded distance (V3) and column band
            below = sorted((b for b in scoped if id(b) not in keys and (b.get("text") or "").strip()
                            and 0 <= b["bbox"][1] - ly1 <= max_below_factor * lh
                            and _col_overlap(lab["bbox"], b["bbox"]) >= 0.3),
                           key=lambda b: (b["bbox"][1], b["bbox"][0]))
            val = below[0] if below else None
        if val is None:
            continue
        fields[canonical] = {"value": (val.get("text") or "").strip(),
                             "label_bbox": lab["bbox"], "value_bbox": val["bbox"]}
    return fields


def _bottom_right_region(blocks: list[dict]) -> "list[float] | None":
    """The bottom-right quadrant of the blocks' bounding box -- where a title block conventionally sits."""
    xs = [b["bbox"][0] for b in blocks] + [b["bbox"][2] for b in blocks]
    ys = [b["bbox"][1] for b in blocks] + [b["bbox"][3] for b in blocks]
    if not xs:
        return None
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    return [x0 + (x1 - x0) * 0.55, y0 + (y1 - y0) * 0.6, x1, y1]


def detect_title_block_gated(blocks: list[dict], *, region: "list[float] | None" = None,
                             min_fields: int = 2) -> dict:
    """Wire-safe entry (V4): never scans globally. Falls back to the bottom-right quadrant when no
    ``region`` is given, and requires ``min_fields`` matched fields (a real title block has several) so a
    stray drawing-term in prose does not surface a phantom block."""
    region = region or _bottom_right_region(blocks)
    fields = detect_title_block(blocks, region=region)
    return fields if len(fields) >= min_fields else {}
