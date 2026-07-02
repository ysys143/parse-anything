"""Scorecard: per-domain metrics from a golden set + a run result.

Contract: pdf-pipeline-requirements §8, processing-tiers R-A5/R-A8. The golden set is the
byproduct of human review in the adaptation harness (review.py). This module turns golden +
DocumentResult into the measurable signals -- numeric recall, routing accuracy, and a flag
summary -- so a domain's error characteristics can be measured rather than assumed.

Metrics that need richer ground truth (reading-order NID, table TEDS) are out of scope here;
this is the tractable core that a simple per-page golden supports.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .guards import normalize_number
from .run import DocumentResult


@dataclass(frozen=True, slots=True)
class PageGold:
    page_index: int
    expected_numbers: tuple[str, ...] = ()
    expected_route: str | None = None


def score_document(golden: Sequence[PageGold], result: DocumentResult) -> dict:
    pages = {p.page_index: p for p in result.pages}
    num_re = re.compile(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?")
    num_hit = num_total = 0
    route_hit = route_total = 0
    for g in golden:
        page = pages.get(g.page_index)
        emitted = {normalize_number(m) for m in num_re.findall(page.markdown)} if page else set()
        for want in g.expected_numbers:
            num_total += 1
            if normalize_number(want) in emitted:
                num_hit += 1
        if g.expected_route is not None and page is not None:
            route_total += 1
            if page.route == g.expected_route:
                route_hit += 1

    flag_counts: dict[str, int] = {}
    flagged_pages = 0
    for p in result.pages:
        if p.flags and p.route != "folded":
            flagged_pages += 1
        for f in p.flags:
            key = f.split(":", 1)[0]
            flag_counts[key] = flag_counts.get(key, 0) + 1

    return {
        "pages": len(result.pages),
        "numeric_recall": _ratio(num_hit, num_total),
        "numeric_hit": num_hit,
        "numeric_total": num_total,
        "routing_accuracy": _ratio(route_hit, route_total),
        "flagged_pages": flagged_pages,
        "flag_counts": flag_counts,
    }


def _ratio(hit: int, total: int) -> float | None:
    return None if total == 0 else hit / total
