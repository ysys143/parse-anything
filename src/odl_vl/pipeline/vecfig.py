"""Vector-figure detection (R14): chart regions the raster-figure detector misses.

ODL only flags EMBEDDED RASTER images (signatures, stamps, logos) as figures; a line/bar chart drawn
with vector paths -- the common case in white papers and reports -- is invisible to it, so the VLM
just emits a bare ``[figure]`` placeholder. Here we recover those regions geometrically: cluster a
page's vector path objects (pypdfium2 ``get_objects`` type 2) by proximity, then keep only clusters
that LOOK like a figure, judged by document-agnostic GEOMETRY (no per-document tuning, no keywords):

- not inside a known ODL table (its cell borders are paths too),
- dense enough (>= ``min_paths`` segments; a lone separator rule is one path),
- a meaningful area (drops hairline icons / single rules),
- NOT a text region: a page's section rules + underlines also cluster, so a cluster whose bbox is
  mostly covered by body-text blocks is prose, not a chart (this is what stops an academic page's
  copyright/intro columns from being cropped as a "figure").

Each surviving cluster bbox is padded to take in the axis labels (text just outside the paths).
"""
from __future__ import annotations

import pypdfium2 as pdfium

BBox = tuple[float, float, float, float]


def _cluster(boxes: list[BBox], gap: float) -> list[list[BBox]]:
    """Union-find grouping: boxes whose (gap-expanded) rectangles touch land in the same cluster."""
    parent = list(range(len(boxes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def near(a: BBox, b: BBox) -> bool:
        return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if near(boxes[i], boxes[j]):
                parent[find(i)] = find(j)
    groups: dict[int, list[BBox]] = {}
    for i in range(len(boxes)):
        groups.setdefault(find(i), []).append(boxes[i])
    return list(groups.values())


def _in_table(box: BBox, tables: list[BBox], pad: float = 6.0) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return any(t[0] - pad <= cx <= t[2] + pad and t[1] - pad <= cy <= t[3] + pad for t in tables)


def _text_cover(box: BBox, text_blocks: list[BBox]) -> float:
    """Fraction of ``box`` area covered by text blocks (capped at 1.0). A chart's labels cover a
    small slice; a mistaken text-region cluster is covered by prose paragraphs."""
    area = (box[2] - box[0]) * (box[3] - box[1])
    if area <= 0:
        return 1.0
    covered = 0.0
    for t in text_blocks:
        iw = max(0.0, min(box[2], t[2]) - max(box[0], t[0]))
        ih = max(0.0, min(box[3], t[3]) - max(box[1], t[1]))
        covered += iw * ih
    return min(1.0, covered / area)


def _page_figures(paths: list[BBox], tables: list[BBox], text_blocks: list[BBox], *,
                  width: float, height: float, min_paths: int = 8, gap: float = 12.0, pad: float = 14.0,
                  min_area: float = 2500.0, max_text_cover: float = 0.35,
                  max_area_frac: float = 0.8) -> list[BBox]:
    """Figure bboxes for ONE page (pure -- the testable core). Inputs are path / table / text-block
    bboxes in PDF space (origin bottom-left). Padded output; sorted top-to-bottom."""
    non_table = [b for b in paths if not _in_table(b, tables)]
    figs: list[BBox] = []
    for cluster in _cluster(non_table, gap):
        if len(cluster) < min_paths:                       # too few segments -> a rule, not a chart
            continue
        # Clamp to the page BEFORE the area/text-cover guards: link underlines and decorative strokes
        # can extend off-page, and the off-page area would otherwise dilute the text-coverage fraction.
        x0, y0 = max(0.0, min(p[0] for p in cluster)), max(0.0, min(p[1] for p in cluster))
        x1, y1 = min(width, max(p[2] for p in cluster)), min(height, max(p[3] for p in cluster))
        if (x1 - x0) * (y1 - y0) < min_area:               # hairline / icon -> noise
            continue
        if (x1 - x0) * (y1 - y0) > width * height * max_area_frac:   # covers ~the whole page: a slide or
            continue                                                #   page background, not a chart region
        if _text_cover((x0, y0, x1, y1), text_blocks) > max_text_cover:  # a prose region, not a figure
            continue
        figs.append((max(0.0, x0 - pad), max(0.0, y0 - pad), min(width, x1 + pad), min(height, y1 + pad)))
    return sorted(figs, key=lambda b: -b[3])


def detect_vector_figures(pdf_path: str, tables_by_page: dict[int, list[BBox]],
                          text_by_page: dict[int, list[BBox]] | None = None, *,
                          min_paths: int = 8, gap: float = 12.0, pad: float = 14.0) -> dict[int, list[BBox]]:
    """``{page_index: [bbox, ...]}`` of vector chart regions. ``text_by_page`` = ODL paragraph bboxes
    per page, used to reject text-region clusters."""
    text_by_page = text_by_page or {}
    out: dict[int, list[BBox]] = {}
    doc = pdfium.PdfDocument(pdf_path)
    try:
        for pi in range(len(doc)):
            page = doc[pi]
            width, height = page.get_size()
            paths: list[BBox] = []
            for obj in page.get_objects():
                if obj.type != 2:  # 2 = path (vector); 1 = text, 3 = image (raster, ODL handles those)
                    continue
                try:
                    paths.append(tuple(obj.get_bounds()))  # type: ignore[arg-type]
                except Exception:  # noqa: BLE001 -- a malformed object must not abort detection
                    continue
            figs = _page_figures(paths, tables_by_page.get(pi, []), text_by_page.get(pi, []),
                                 width=width, height=height, min_paths=min_paths, gap=gap, pad=pad)
            if figs:
                out[pi] = figs
        return out
    finally:
        doc.close()
