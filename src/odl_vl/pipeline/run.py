"""End-to-end document run: signals -> triage -> deterministic | VLM -> per-page outcome,
with page-spanning tables batched into one multi-image VLM request.

Contract: pdf-pipeline-requirements §2, §4, §7. Evidence: F8 (oracle gate), F9 (multi-image
spanning tables), F10 (triage). The VLM client is injected (testable without keys/network).
"""
from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .deterministic import number_tokens, page_text
from .render import render_page_png
from .signals import document_signals
from .triage import PageSignals, Route, TriagePolicy, decide_route

DEFAULT_PROMPT = (
    "Transcribe this document page into clean GitHub-flavored Markdown. Preserve reading "
    "order, headings, lists, and tables. Render math as LaTeX. Briefly describe non-text "
    "figures in italics. Output ONLY the Markdown."
)

SPANNING_PROMPT = (
    "These are consecutive pages of one document; a single table spans them (continuation "
    "pages have no repeated header). Reconstruct the COMPLETE table as one Markdown table, "
    "carrying the header across pages and including any subtotal/total rows. Output ONLY the "
    "Markdown table."
)


@dataclass(frozen=True, slots=True)
class PageOutcome:
    page_index: int
    route: str
    used_vlm: bool
    markdown: str
    latency_ms: float
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentResult:
    pages: tuple[PageOutcome, ...]

    def ledger(self) -> list[dict[str, Any]]:
        return [
            {
                "page_index": p.page_index,
                "route": p.route,
                "used_vlm": p.used_vlm,
                "markdown_chars": len(p.markdown),
                "flags": list(p.flags),
                "latency_ms": round(p.latency_ms, 2),
            }
            for p in self.pages
        ]


def _oracle_flags(pdf_path: str, page_indices: Sequence[int], markdown: str, oracle_min_value: float) -> list[str]:
    from .oracle import fabrication_flags

    source: list[str] = []
    for j in page_indices:
        source.extend(t.value for t in number_tokens(pdf_path, j, min_value=oracle_min_value))
    return [f"unsourced_number:{v}" for v in fabrication_flags(markdown, source, min_value=oracle_min_value)]


def _process_single(pdf_path, i, route, *, vlm_client, api_key, prompt, oracle_min_value) -> PageOutcome:
    t0 = time.monotonic()
    flags: list[str] = []
    if route == Route.DETERMINISTIC:
        markdown, used = page_text(pdf_path, i), False
    elif vlm_client is None:
        markdown, used = page_text(pdf_path, i), False
        flags.append("vlm_unavailable")  # VLM-needed page with no client: degrade to text, flag for review
    else:
        from .vlm import VlmError, transcribe_image

        try:
            markdown = transcribe_image(render_page_png(pdf_path, i), prompt, api_key=api_key, client=vlm_client)
            used = True
            if route == Route.ORACLE_VLM:
                flags.extend(_oracle_flags(pdf_path, [i], markdown, oracle_min_value))
        except VlmError as exc:
            markdown, used = page_text(pdf_path, i), False
            flags.append(str(exc))
    return PageOutcome(i, route.value, used, markdown, (time.monotonic() - t0) * 1000.0, tuple(flags))


def _process_group(pdf_path, group, *, vlm_client, api_key, oracle_min_value) -> list[PageOutcome]:
    """A continuation group (>=2 pages, all table routes). Sent as one multi-image request;
    the merged table is attached to the start page, continuation pages are folded."""
    from .vlm import VlmError, transcribe_images

    t0 = time.monotonic()
    flags = [f"spanning_table:{group[0]}-{group[-1]}"]
    try:
        markdown = transcribe_images([render_page_png(pdf_path, j) for j in group], SPANNING_PROMPT, api_key=api_key, client=vlm_client)
        flags.extend(_oracle_flags(pdf_path, group, markdown, oracle_min_value))
        used = True
    except VlmError as exc:
        markdown = "\n\n".join(page_text(pdf_path, j) for j in group)
        used = False
        flags.append(str(exc))
    start = PageOutcome(group[0], Route.ORACLE_VLM.value, used, markdown, (time.monotonic() - t0) * 1000.0, tuple(flags))
    folded = [PageOutcome(j, "folded", False, "", 0.0, (f"folded_into:{group[0]}",)) for j in group[1:]]
    return [start, *folded]


def run_document(
    pdf_path: str,
    *,
    vlm_client: Any | None = None,
    api_key: str = "",
    prompt: str = DEFAULT_PROMPT,
    policy: TriagePolicy = TriagePolicy(),
    signals: Sequence[PageSignals] | None = None,
    oracle_min_value: float = 1000.0,
    detect_spanning_tables: bool = True,
) -> DocumentResult:
    sigs = list(signals) if signals is not None else document_signals(pdf_path)
    routes = [decide_route(s, policy) for s in sigs]
    if detect_spanning_tables and vlm_client is not None:
        from .crosspage import ContinuationPolicy, continuation_groups

        groups = continuation_groups(pdf_path, routes, policy=ContinuationPolicy())
    else:
        groups = [[i] for i in range(len(sigs))]

    outcomes: list[PageOutcome] = []
    for group in groups:
        if len(group) == 1:
            outcomes.append(
                _process_single(pdf_path, group[0], routes[group[0]], vlm_client=vlm_client, api_key=api_key, prompt=prompt, oracle_min_value=oracle_min_value)
            )
        else:
            outcomes.extend(_process_group(pdf_path, group, vlm_client=vlm_client, api_key=api_key, oracle_min_value=oracle_min_value))
    outcomes.sort(key=lambda p: p.page_index)
    return DocumentResult(tuple(outcomes))
