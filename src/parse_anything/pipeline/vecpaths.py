"""Connector-polyline extraction for diagram graphs (FR-5.3 / B4b).

``vecfig`` only reads path BOUNDS (bbox) to cluster figure regions; a diagram's edges need the actual
line geometry. This reaches the pypdfium2 RAW path-segment API (the high-level ``PdfObject`` exposes only
``get_bounds``) to recover, per page, the STROKED, OPEN polylines inside a diagram region -- the
connectors between boxes. Filled shapes (arrowheads, solid boxes) and CLOSED paths (box outlines) are
excluded. Output is direction-agnostic ``{"bbox": [...]}`` per connector: ``build_diagram_graph`` links the
node nearest each end and flags the edge ``direction:"ambiguous"`` (pdfium's segment draw order is not a
reliable arrow direction; arrowhead detection is future work).

Coordinate space: pdfium path points are PDF space (origin bottom-left), the SAME space vecfig already
cross-compares against ODL table/text bboxes, so connector bboxes and diagram node (chart_data) bboxes
share one space -- ``build_diagram_graph._nearest`` (pure distance) is convention-agnostic regardless.
"""
from __future__ import annotations

import ctypes

import pypdfium2 as pdfium
import pypdfium2.raw as pr

BBox = list[float]


def _path_polyline(obj) -> "tuple[list[tuple[float, float]], bool]":
    """The path's segment points and whether ANY subpath is closed (a closed path is a box, not an edge)."""
    n = pr.FPDFPath_CountSegments(obj)
    pts: list[tuple[float, float]] = []
    closed = False
    for i in range(n):
        seg = pr.FPDFPath_GetPathSegment(obj, i)
        if not seg:
            continue
        x, y = ctypes.c_float(), ctypes.c_float()
        if pr.FPDFPathSegment_GetPoint(seg, ctypes.byref(x), ctypes.byref(y)):
            pts.append((x.value, y.value))
        if pr.FPDFPathSegment_GetClose(seg):
            closed = True
    return pts, closed


def _classify_polyline(pts: "list[tuple[float, float]]", *, closed: bool, stroked: bool,
                       filled: bool) -> "dict | None":
    """Pure connector test -> ``{"bbox":[...], "points":[first, last]}`` or None. A connector is STROKED,
    NOT filled (a filled shape is a box or an arrowhead), OPEN (a closed subpath is a box outline), with
    >=2 points. ``points`` are the ACTUAL first/last terminal points of the polyline (NOT bbox corners):
    an orthogonal L-connector's endpoints lie on the anti-diagonal, so bbox corners would name a phantom
    point and link the wrong nodes -- the real terminals must drive node linking. ``bbox`` is for region
    filtering only. Direction is NOT implied (pdfium segment order is not arrow direction)."""
    if not stroked or filled or closed or len(pts) < 2:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return {"bbox": [min(xs), min(ys), max(xs), max(ys)], "points": [list(pts[0]), list(pts[-1])]}


def _is_connector(obj) -> "dict | None":
    """``_classify_polyline`` over one pdfium path object (reads its draw mode + segments)."""
    fill, stroke = ctypes.c_int(), ctypes.c_int()
    if not pr.FPDFPath_GetDrawMode(obj, ctypes.byref(fill), ctypes.byref(stroke)):
        return None
    pts, closed = _path_polyline(obj)
    return _classify_polyline(pts, closed=closed, stroked=bool(stroke.value), filled=bool(fill.value))


def _in_region(bbox: BBox, region: BBox) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]


def detect_connectors(pdf_path: str, page_index: int, region: BBox) -> list[dict]:
    """``[{"bbox":[...], "points":[first,last]}, ...]`` for the connector polylines whose centre falls
    inside ``region`` (a diagram figure's bbox) on ``page_index``. Direction-agnostic by design (see
    module docstring). Best-effort: an unloadable PDF / out-of-range page yields ``[]`` -- never raises --
    so this additive graph step can never abort the export."""
    out: list[dict] = []
    try:
        doc = pdfium.PdfDocument(pdf_path)
    except Exception:                                  # noqa: BLE001 -- a PDF pdfium can't open must not abort
        return out
    try:
        if not (0 <= page_index < len(doc)):           # ODL/pdfium page-count mismatch -> nothing, not a crash
            return out
        page = doc[page_index]
        for obj in page.get_objects():
            if obj.type != 2:  # type: ignore[attr-defined]  # 2 = path (vector); text/image handled elsewhere
                continue
            try:
                rec = _is_connector(obj)
            except Exception:                          # noqa: BLE001 -- a malformed object must not abort
                rec = None
            if rec is not None and _in_region(rec["bbox"], region):
                out.append(rec)
        return out
    except Exception:                                  # noqa: BLE001 -- page load / object walk failure -> []
        return out
    finally:
        doc.close()
