"""Deterministic engineering-drawing title-block extraction (FR-5.2).

A title block is the ruled grid in the bottom-right of a drawing frame holding scale, material, sheet,
date, drawing number, etc. Unlike a form field it usually has NO colon -- label and value sit in adjacent
grid cells -- so pairing is driven by a dictionary of KNOWN, multilingual field keys (Maßstab / Scale /
축척 …) plus B1's geometry (value in the adjacent cell to the right, else below). Values are quoted, never
generated (§5-C).

WIRE-TIME GATE: use ``detect_title_block_gated`` (auto bottom-right region + field-density gate) so a
stray 'Material' heading in body text is not read as a title-block field. A value may span several OCR
tokens on the same row (they are merged until the next key / a wide gap). Limitation: value-right and
value-below only -- a RIGHT-ALIGNED title block (value LEFT of its label) is intentionally NOT paired,
since a bare left neighbour can't be distinguished from another field's value without cell borders.
"""
from __future__ import annotations

from .forms import _col_overlap, _merge_column_run, _row_overlap

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
        value_text, value_bbox = None, None
        # (1) same row to the right: a value may span SEVERAL tokens (OCR splits '16MnCr5'), so accumulate
        #     consecutive non-key tokens until the next field's key (V2d), a big x-gap, or a token cap.
        right = sorted((b for b in scoped if b is not lab and b["bbox"][0] >= lx1 - 1
                        and _row_overlap(lab["bbox"], b["bbox"]) >= 0.5),
                       key=lambda b: (b["bbox"][0], b["bbox"][1]))
        run: list[dict] = []
        for b in right:
            if id(b) in keys:
                break
            if not (b.get("text") or "").strip():
                continue
            # tokens of ONE value are tightly spaced; a wide gap is the next cell. 1.5x line height is
            # tighter than a title-block cell gap; the length cap is only a runaway backstop.
            if run and (b["bbox"][0] - run[-1]["bbox"][2] > 1.5 * lh or len(run) >= 8):
                break
            run.append(b)
        if run:
            value_text = " ".join((r.get("text") or "").strip() for r in run)
            value_bbox = [min(r["bbox"][0] for r in run), min(r["bbox"][1] for r in run),
                          max(r["bbox"][2] for r in run), max(r["bbox"][3] for r in run)]
        # (2) else the value cell directly below, merging a vertical stack (B1b helper)
        if value_text is None:
            col = sorted((b for b in scoped if (b.get("text") or "").strip()
                          and b["bbox"][1] >= ly1 - 1 and _col_overlap(lab["bbox"], b["bbox"]) >= 0.3),
                         key=lambda b: (b["bbox"][1], b["bbox"][0]))       # includes keys as barriers
            first = next((b for b in col if id(b) not in keys
                          and b["bbox"][1] - ly1 <= max_below_factor * lh), None)
            if first is not None:
                value_text, value_bbox = _merge_column_run(first, col, lh, stop=lambda b: id(b) in keys)
        # (right-aligned title blocks -- value LEFT of the label -- are NOT paired: a bare left neighbour
        #  can't be told from another field's value without cell borders, and grabbing it cross-pollutes
        #  fields, so it is intentionally unsupported. See module docstring.)
        if value_text is None:
            continue
        fields[canonical] = {"value": value_text, "label_bbox": lab["bbox"], "value_bbox": value_bbox}
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
