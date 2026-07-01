"""Processing-depth signals: per-page route decision (DIAGNOSTIC use only).

DEMOTED (processing-tiers P7): this is no longer a runtime gate. Real corpora showed
per-page auto-routing is a false-positive gamble (F16), so the runtime uses configured
*modes* (assemble.py), not decide_route. ``decide_route`` survives as a **diagnostic signal**
-- the source-level diagnosis (processing-tiers §2.5) may use it to characterize a source and
recommend a profile. It must not be called from the runtime assembly path.

Evidence: docs/measurement-findings.md F10/F16. Contract: pdf-pipeline-requirements §3.4,
processing-tiers §2.5 / §3.

This module is the *decision* only -- a pure function over already-computed signals.
Signal computation (pypdfium2 text/images + pdf-inspector / ODL table detection) is I/O
and lives elsewhere. Thresholds are in ``TriagePolicy`` (R-A7: calibrated, not hardcoded).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Route(str, Enum):
    DETERMINISTIC = "deterministic"  # born-digital prose: text layer only, skip VLM
    TABLE_VLM = "table_vlm"        # born-digital table: VLM structure + source-value oracle
    FIGURE_VLM = "figure_vlm"        # figures/charts: VLM for semantic description
    SCAN_VLM = "scan_vlm"            # no text layer: OCR/VLM + full guard stack


@dataclass(frozen=True, slots=True)
class PageSignals:
    """Deterministic per-page signals. ``table_rows`` should come from a reliable table
    detector (pdf-inspector for grids; ODL for merged-cell tables -- F2/F10: naive column
    counting over-fires and pdf-inspector misses merged cells). ``vector_paths`` (path-object
    count) is the figure discriminator: complex VECTOR figures (matplotlib-style plots) carry
    hundreds-to-thousands of path objects and no raster image, and their plot grid otherwise
    trips the table detector (F13/F14)."""
    text_chars: int
    table_rows: int
    image_count: int
    vector_paths: int = 0


@dataclass(frozen=True, slots=True)
class TriagePolicy:
    min_text_chars: int = 20       # below this a page is treated as a scan (no usable text layer)
    min_table_rows: int = 3        # at/above this a table is considered present
    min_vector_paths: int = 200    # at/above this a page is a vector figure (F14: figures 365-1018,
    #                                real table ~87, math 3-7 on the measured corpus; domain-calibrated)


def decide_route(signals: PageSignals, policy: TriagePolicy = TriagePolicy()) -> Route:
    """Default to the cheapest sufficient tier; escalate only on a trigger (R-B1).

    Bias is toward VLM: a born-digital page misrouted to ``deterministic`` still keeps correct
    values via the text layer (F10). ``vector_paths`` is checked *before* the table signal: a
    plot-heavy figure page also trips the table detector (F14: 5/6 "table" pages were really
    figures/math), so a clear vector figure routes to FIGURE_VLM rather than have the numeric
    oracle applied to its axis ticks. The threshold sits above a real born-digital table's path
    count, so genuine tables keep the value oracle. (figure_caption was dropped: F14 found the
    caption regex unreliable -- it missed the real captions on every figure page.)
    """
    if signals.text_chars < policy.min_text_chars:
        return Route.SCAN_VLM
    if signals.vector_paths >= policy.min_vector_paths:
        return Route.FIGURE_VLM
    if signals.table_rows >= policy.min_table_rows:
        return Route.TABLE_VLM
    if signals.image_count > 0:
        return Route.FIGURE_VLM
    return Route.DETERMINISTIC
