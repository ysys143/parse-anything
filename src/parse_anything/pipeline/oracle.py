"""Born-digital value oracle: verify VLM numbers against the deterministic source.

Evidence: docs/.design/measurement-findings.md F8 -- the text layer is the authoritative source of
numeric values (degradation-independent); a VLM-emitted number absent from it is
fabrication-suspect. On born-digital tables the gate flagged every fabrication with zero
false flags. Contract: processing-tiers R-V1, pdf-pipeline-requirements §6.

This module provides the proven guarantee (the gate). Full bbox-anchored value replacement
-- substituting source values into the VLM's table structure -- is a planned enhancement;
until then, flagged numbers escalate per R-B3 (review/retry), never silently trusted.
"""
from __future__ import annotations

from collections.abc import Iterable

from .guards import extract_numbers, source_gate


def fabrication_flags(markdown: str, source_values: Iterable[str], *, min_value: float | None = None) -> list[str]:
    """Numbers the VLM emitted that are NOT present in the deterministic source. With
    ``min_value`` set, only substantial numbers are checked (page numbers / small counts
    are noise). Each returned value is a hallucination-suspect that should be flagged.
    """
    emitted = extract_numbers(markdown, min_value=min_value)
    return source_gate(emitted, source_values)
