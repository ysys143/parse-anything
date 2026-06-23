"""Document run: shared result types + prompts, and the mode-driven entry point.

Architecture (processing-tiers P7/§2.6): there is NO runtime per-page auto-routing. A source
profile picks an execution mode and the run is predictable. The per-page assembly lives in
``assemble.py`` (deterministic = ODL + pypdfium2; det_vlm = + VLM, reconciled). ``triage.py``
/ ``signals.py`` survive only as *diagnostic* signals, not runtime gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_PROMPT = (
    "Transcribe this page into clean GitHub-flavored Markdown. Transcribe ONLY text that is "
    "actually printed on the page, verbatim -- never invent, paraphrase, or summarize. Preserve "
    "reading order, headings, lists, tables, and any printed figure/table captions. Render math "
    "as LaTeX. For a figure or chart, emit a single placeholder line `[figure]` and do NOT "
    "describe or interpret its contents. Output ONLY the Markdown."
)
# F14: an earlier prompt asked the model to "describe non-text figures in italics", which made
# it fabricate an italic figure description on every figure page. Transcription stays verbatim;
# figure interpretation is the oracle's/human's job.

SPANNING_PROMPT = (
    "These are consecutive pages of one document; a single table spans them (continuation "
    "pages have no repeated header). Reconstruct the COMPLETE table as one Markdown table, "
    "carrying the header across pages and including any subtotal/total rows. Output ONLY the "
    "Markdown table."
)

LOW_QUALITY_SENTINEL = "IMAGE_TOO_LOW_QUALITY"

# Scans have no text-layer value oracle, so a degraded scan is where the VLM fabricates most
# (F4). A whole-image legibility gate (F6) turns that into a safe abstention.
SCAN_PROMPT = (
    "First judge whether this scanned page is legible enough to transcribe reliably. If it "
    "is too low-resolution or blurry to read the characters with certainty, reply with "
    f"EXACTLY `{LOW_QUALITY_SENTINEL}` and nothing else. Otherwise transcribe the page into "
    "clean GitHub-flavored Markdown. Output ONLY that."
)


@dataclass(frozen=True, slots=True)
class PageOutcome:
    page_index: int
    route: str  # execution mode for the page ("deterministic" / "det_vlm")
    used_vlm: bool
    markdown: str
    latency_ms: float
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentResult:
    pages: tuple[PageOutcome, ...]
    structure: Any = None  # OdlDocument (tables/figures/text with bbox) for rich output (R2)
    meta: Any = None       # DocumentMeta (id, source, provenance) for document.json (R2)

    def ledger(self) -> list[dict[str, Any]]:
        return [
            {
                "page_index": p.page_index,
                "route": p.route,  # now the execution mode ("deterministic" / "det_vlm")
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
    mode: str = "det_vlm",
    vlm_client: Any | None = None,
    api_key: str = "",
    odl_runner: Any | None = None,
    source_id: str = "default",
    external_id: str | None = None,
    ingested_from: str | None = None,
) -> DocumentResult:
    """Run a document in a configured mode (no runtime routing). Delegates to assemble."""
    from .assemble import assemble_document

    return assemble_document(
        pdf_path, mode=mode, vlm_client=vlm_client, api_key=api_key, odl_runner=odl_runner,
        source_id=source_id, external_id=external_id, ingested_from=ingested_from,
    )
