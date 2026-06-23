"""Processing-depth triage: per-page route decision (graduated from prototype).

Evidence: docs/measurement-findings.md F10. Contract: pdf-pipeline-requirements §3.4,
processing-tiers §3 (trigger-based escalation, not a fuzzy score; R-B4).

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
    counting over-fires and pdf-inspector misses merged cells). ``vector_paths`` /
    ``figure_caption`` catch complex VECTOR figures (matplotlib-style plots), which carry no
    raster image object and whose plot grid otherwise trips the table detector."""
    text_chars: int
    table_rows: int
    image_count: int
    vector_paths: int = 0
    figure_caption: bool = False


@dataclass(frozen=True, slots=True)
class TriagePolicy:
    min_text_chars: int = 20      # below this a page is treated as a scan (no usable text layer)
    min_table_rows: int = 3       # at/above this a table is considered present
    min_vector_paths: int = 50    # at/above this a page carries significant vector graphics


def decide_route(signals: PageSignals, policy: TriagePolicy = TriagePolicy()) -> Route:
    """Default to the cheapest sufficient tier; escalate only on a trigger (R-B1).

    Bias is toward VLM: a born-digital page misrouted to ``deterministic`` still keeps
    correct values via the text layer (F10). A complex vector figure (a figure caption plus
    many path objects) routes to FIGURE_VLM *before* the table check, because its plot grid
    otherwise looks like a table and would wrongly invoke the numeric oracle on axis ticks.
    """
    if signals.text_chars < policy.min_text_chars:
        return Route.SCAN_VLM
    heavy_vector = signals.vector_paths >= policy.min_vector_paths
    if signals.figure_caption and heavy_vector:
        return Route.FIGURE_VLM
    if signals.table_rows >= policy.min_table_rows:
        return Route.TABLE_VLM
    if signals.image_count > 0 or heavy_vector:
        return Route.FIGURE_VLM
    return Route.DETERMINISTIC
