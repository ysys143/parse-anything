"""Page-spanning table detection: does page N's table continue onto N+1?

Evidence: docs/measurement-findings.md F9 -- the discriminating signal is column x-position
match between the bottom-of-A and top-of-B tabular regions (continuation ~0.77 vs adjacent
separate tables ~0.40). Contract: pdf-pipeline-requirements §4.

A positive result is the trigger to batch the two page images into ONE multi-image VLM
request (vlm.transcribe_images). Thresholds live in ``ContinuationPolicy`` (R-A7).
"""
from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

import pypdfium2 as pdfium

from .triage import Route


@dataclass(frozen=True, slots=True)
class ContinuationPolicy:
    min_column_match: float = 0.7
    min_tabular_lines: int = 3
    bottom_fraction: float = 0.45   # region of page A considered (bottom 45%)
    top_skip_fraction: float = 0.10  # skip a running header at the very top of page B
    top_fraction: float = 0.92


@dataclass(frozen=True, slots=True)
class ContinuationResult:
    is_continuation: bool
    column_match: float
    a_tabular_lines: int
    b_tabular_lines: int


def _line_column_starts(page) -> list[tuple[float, list[float]]]:
    """For each text line: (top_y, [token-start x positions])."""
    tp = page.get_textpage()
    chars = []
    for i in range(tp.count_chars()):
        left, bottom, right, top = tp.get_charbox(i)
        ch = tp.get_text_range(i, 1)
        if ch.strip():
            chars.append((left, bottom, right, top))
    if not chars:
        return []
    chars.sort(key=lambda c: (-c[3], c[0]))
    lines: list[list[tuple[float, float, float, float]]] = []
    cur: list[tuple[float, float, float, float]] = []
    cy: float | None = None
    for c in chars:
        if cy is None or abs(c[3] - cy) <= 3:
            cur.append(c)
            cy = c[3] if cy is None else cy
        else:
            lines.append(cur)
            cur = [c]
            cy = c[3]
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda c: c[0])
        widths = [c[2] - c[0] for c in ln if c[2] > c[0]]
        gap = (statistics.median(widths) if widths else 3) * 1.8
        starts = [ln[0][0]]
        for a, b in zip(ln, ln[1:]):
            if b[0] - a[2] > gap:
                starts.append(b[0])
        out.append((ln[0][3], starts))
    return out


def _cluster(xs: list[float], tol: float) -> list[float]:
    xs = sorted(xs)
    clusters: list[list[float]] = []
    for x in xs:
        if clusters and x - clusters[-1][-1] <= tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [sum(c) / len(c) for c in clusters]


def _region_columns(lines, tol: float) -> tuple[list[float], int]:
    tabular = [cols for _, cols in lines if len(cols) >= 3]
    allx = [x for cols in tabular for x in cols]
    return _cluster(allx, tol), len(tabular)


def continues(pdf_path: str, page_a: int, page_b: int, *, policy: ContinuationPolicy = ContinuationPolicy()) -> ContinuationResult:
    doc = pdfium.PdfDocument(pdf_path)
    try:
        la = _line_column_starts(doc[page_a])
        lb = _line_column_starts(doc[page_b])
        width, height = doc[page_a].get_size()
    finally:
        doc.close()
    tol = width * 0.02
    bottom_a = [(y, c) for y, c in la if y < height * policy.bottom_fraction]
    top_b = [(y, c) for y, c in lb if height * policy.top_skip_fraction < y < height * policy.top_fraction]
    cols_a, tab_a = _region_columns(bottom_a, tol)
    cols_b, tab_b = _region_columns(top_b[:18], tol)
    match = (
        sum(1 for cb in cols_b if any(abs(cb - ca) <= tol for ca in cols_a)) / len(cols_b)
        if cols_b
        else 0.0
    )
    is_cont = tab_a >= policy.min_tabular_lines and tab_b >= policy.min_tabular_lines and match >= policy.min_column_match
    return ContinuationResult(is_continuation=is_cont, column_match=match, a_tabular_lines=tab_a, b_tabular_lines=tab_b)


def continuation_groups(pdf_path: str, routes: Sequence[Route], *, policy: ContinuationPolicy = ContinuationPolicy()) -> list[list[int]]:
    """Group consecutive page indices whose tables continue across the boundary. Only table
    pages (Route.TABLE_VLM) can join a group; singletons stay singletons. A multi-page group
    is sent as one multi-image VLM request and merged into the start page (§4)."""
    n = len(routes)
    groups: list[list[int]] = []
    i = 0
    while i < n:
        group = [i]
        while (
            i + 1 < n
            and routes[i] == Route.TABLE_VLM
            and routes[i + 1] == Route.TABLE_VLM
            and continues(pdf_path, i, i + 1, policy=policy).is_continuation
        ):
            group.append(i + 1)
            i += 1
        groups.append(group)
        i += 1
    return groups
