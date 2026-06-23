"""End-to-end document run: signals -> triage -> deterministic | VLM -> per-page outcome.

Contract: pdf-pipeline-requirements §2, §7 (per-page output + ledger). This is the minimal
assembly; oracle injection (F8), page-spanning tables (F9), and the full guard stack layer
on top in later slices. The VLM client is injected (testable without keys/network).
"""
from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .deterministic import page_text
from .render import render_page_png
from .signals import document_signals
from .triage import PageSignals, Route, TriagePolicy, decide_route

DEFAULT_PROMPT = (
    "Transcribe this document page into clean GitHub-flavored Markdown. Preserve reading "
    "order, headings, lists, and tables. Render math as LaTeX. Briefly describe non-text "
    "figures in italics. Output ONLY the Markdown."
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
        """Per-page ledger rows (route, vlm usage, size, flags, latency) -- §7 / task #13."""
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


def run_document(
    pdf_path: str,
    *,
    vlm_client: Any | None = None,
    api_key: str = "",
    prompt: str = DEFAULT_PROMPT,
    policy: TriagePolicy = TriagePolicy(),
    signals: Sequence[PageSignals] | None = None,
) -> DocumentResult:
    sigs = list(signals) if signals is not None else document_signals(pdf_path)
    outcomes: list[PageOutcome] = []
    for i, s in enumerate(sigs):
        route = decide_route(s, policy)
        t0 = time.monotonic()
        flags: list[str] = []
        if route == Route.DETERMINISTIC:
            markdown, used_vlm = page_text(pdf_path, i), False
        elif vlm_client is None:
            # VLM needed but unavailable (no client/keys): fall back to the text layer and
            # flag it -- never silently drop the page.
            markdown, used_vlm = page_text(pdf_path, i), False
            flags.append("vlm_unavailable")
        else:
            from .vlm import VlmError, transcribe_image

            try:
                markdown = transcribe_image(render_page_png(pdf_path, i), prompt, api_key=api_key, client=vlm_client)
                used_vlm = True
            except VlmError as exc:
                markdown, used_vlm = page_text(pdf_path, i), False
                flags.append(str(exc))
        latency = (time.monotonic() - t0) * 1000.0
        outcomes.append(PageOutcome(i, route.value, used_vlm, markdown, latency, tuple(flags)))
    return DocumentResult(tuple(outcomes))
