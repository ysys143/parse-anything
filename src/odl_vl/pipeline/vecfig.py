"""Vector-figure detection (R14): chart regions the raster-figure detector misses.

ODL only flags EMBEDDED RASTER images (signatures, stamps, logos) as figures; a line/bar chart drawn
with vector paths -- the common case in white papers and reports -- is invisible to it, so the VLM
just emits a bare ``[figure]`` placeholder. Here we recover those regions geometrically: cluster a
page's vector path objects (pypdfium2 ``get_objects`` type 2) by proximity, drop clusters that fall
inside a known ODL table (its cell borders are paths too), and keep only DENSE clusters -- a chart is
many path segments in a confined area; a lone separator rule is a single path. Each surviving cluster
bbox (padded to take in the axis labels, which are text objects just outside the path cluster) is a
figure to crop and caption. Thresholds are document-relative (path COUNT, proximity GAP), not tuned
to one document's pixel coordinates.
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


def detect_vector_figures(pdf_path: str, tables_by_page: dict[int, list[BBox]], *,
                          min_paths: int = 8, gap: float = 12.0, pad: float = 14.0) -> dict[int, list[BBox]]:
    """``{page_index: [bbox, ...]}`` of vector chart regions (PDF space, origin bottom-left), padded
    to include axis labels. A cluster needs >= ``min_paths`` paths to count as a chart (filters rules)."""
    out: dict[int, list[BBox]] = {}
    doc = pdfium.PdfDocument(pdf_path)
    try:
        for pi in range(len(doc)):
            page = doc[pi]
            width, height = page.get_size()
            tables = tables_by_page.get(pi, [])
            paths: list[BBox] = []
            for obj in page.get_objects():
                if obj.type != 2:  # 2 = path (vector); 1 = text, 3 = image (raster, ODL handles those)
                    continue
                try:
                    box = tuple(obj.get_bounds())  # (left, bottom, right, top)
                except Exception:  # noqa: BLE001 -- a malformed object must not abort detection
                    continue
                if not _in_table(box, tables):
                    paths.append(box)  # type: ignore[arg-type]
            figs: list[BBox] = []
            for cluster in _cluster(paths, gap):
                if len(cluster) < min_paths:
                    continue
                x0 = max(0.0, min(p[0] for p in cluster) - pad)
                y0 = max(0.0, min(p[1] for p in cluster) - pad)
                x1 = min(width, max(p[2] for p in cluster) + pad)
                y1 = min(height, max(p[3] for p in cluster) + pad)
                figs.append((x0, y0, x1, y1))
            if figs:
                out[pi] = sorted(figs, key=lambda b: -b[3])  # top-to-bottom
        return out
    finally:
        doc.close()
