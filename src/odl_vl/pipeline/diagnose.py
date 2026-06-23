"""D-1 source diagnostic: pick an execution mode by *measurement*, not per-page guessing.

Processing-tiers §2.5: per-page auto-routing is a false-positive gamble (F16). Instead, run a
cheap built-in-VLM diagnosis ONCE per source -- sample a few pages, measure how far a VLM
diverges from the deterministic text layer and whether the source is scanned / structurally
complex -- and recommend deterministic vs det_vlm with evidence. The chosen mode then runs the
whole source predictably (no runtime routing). The VLM client is injected (testable).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .deterministic import page_text
from .odl_extract import extract as odl_extract
from .odl_extract import substantial_tables
from .render import page_count, render_page_png

_SCAN_TEXT_CHARS = 20      # below this, the page has effectively no text layer (scan/image)
_DIVERGE_TOKEN = 0.35      # mean token divergence above which the VLM materially disagrees
_SCAN_FRACTION = 0.25      # sampled-scan fraction above which OCR (VLM) is mandatory
_TOKEN_RE = re.compile(r"[0-9a-z가-힣]+")


@dataclass(frozen=True, slots=True)
class SourceDiagnosis:
    recommended_mode: str          # "deterministic" | "det_vlm"
    confidence: float              # 0..1
    n_pages: int
    n_sampled: int
    scan_fraction: float
    mean_token_divergence: float
    pages_with_tables: int
    pages_with_figures: int
    reasons: tuple[str, ...]
    samples: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_mode": self.recommended_mode,
            "confidence": round(self.confidence, 2),
            "n_pages": self.n_pages,
            "n_sampled": self.n_sampled,
            "scan_fraction": round(self.scan_fraction, 3),
            "mean_token_divergence": round(self.mean_token_divergence, 3),
            "pages_with_tables": self.pages_with_tables,
            "pages_with_figures": self.pages_with_figures,
            "reasons": list(self.reasons),
            "samples": list(self.samples),
        }


def sample_indices(n_pages: int, k: int) -> list[int]:
    """Evenly spaced page indices (deterministic -- includes first and last)."""
    if n_pages <= 0:
        return []
    if n_pages <= k:
        return list(range(n_pages))
    step = (n_pages - 1) / (k - 1) if k > 1 else 0
    return sorted({round(i * step) for i in range(k)})


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def token_divergence(a: str, b: str) -> float:
    """1 - Jaccard over alphanumeric/Hangul tokens. 0 = identical content, 1 = disjoint.
    Markdown syntax is ignored, so faithful transcription of a born-digital page scores ~0."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 0.0
    union = ta | tb
    return 1.0 - (len(ta & tb) / len(union) if union else 0.0)


def diagnose_source(
    pdf_path: str,
    *,
    vlm_client: Any,
    api_key: str = "",
    sample_size: int = 4,
    odl_runner: Any | None = None,
) -> SourceDiagnosis:
    if vlm_client is None:
        raise ValueError("D-1 diagnosis requires a VLM client (it measures deterministic-vs-VLM divergence)")
    from .run import DEFAULT_PROMPT
    from .vlm import VlmError, transcribe_image

    n = page_count(pdf_path)
    odl_doc = odl_extract(pdf_path, runner=odl_runner)
    # Structure-aware sampling: even-spaced pages PLUS up to 2 pages ODL shows carry tables/
    # figures, so the structure signal is actually measured (even sampling can miss sparse
    # structure -- e.g. a single table page in a 24-page paper).
    base = sample_indices(n, sample_size)
    structure_pages = [i for i, pg in enumerate(odl_doc.pages) if substantial_tables(pg) or pg.images]
    extra = [i for i in structure_pages if i not in base][:2]
    indices = sorted(set(base) | set(extra))

    samples: list[dict[str, Any]] = []
    divergences: list[float] = []
    scans = tables_pages = figures_pages = 0
    for i in indices:
        det_text = page_text(pdf_path, i)
        is_scan = len(det_text.strip()) < _SCAN_TEXT_CHARS
        odl_page = odl_doc.pages[i] if i < len(odl_doc.pages) else None
        n_tables = len(substantial_tables(odl_page)) if odl_page else 0
        n_figures = len(odl_page.images) if odl_page else 0
        try:
            vlm_text = transcribe_image(render_page_png(pdf_path, i), DEFAULT_PROMPT, api_key=api_key, client=vlm_client)
            div: float | None = token_divergence(det_text, vlm_text)
        except VlmError:
            div = None  # a failed sample contributes structure/scan signal but no divergence
        if is_scan:
            scans += 1
        if n_tables:
            tables_pages += 1
        if n_figures:
            figures_pages += 1
        if div is not None:
            divergences.append(div)
        samples.append({
            "page_index": i, "is_scan": is_scan,
            "token_divergence": round(div, 3) if div is not None else None,
            "n_tables": n_tables, "n_figures": n_figures,
        })

    n_sampled = len(indices)
    scan_fraction = scans / n_sampled if n_sampled else 0.0
    mean_div = sum(divergences) / len(divergences) if divergences else 0.0
    mode, confidence, reasons = _recommend(scan_fraction, mean_div, tables_pages, figures_pages)
    return SourceDiagnosis(
        recommended_mode=mode, confidence=confidence, n_pages=n, n_sampled=n_sampled,
        scan_fraction=scan_fraction, mean_token_divergence=mean_div,
        pages_with_tables=tables_pages, pages_with_figures=figures_pages,
        reasons=reasons, samples=tuple(samples),
    )


def _recommend(scan_fraction: float, mean_div: float, tables_pages: int, figures_pages: int) -> tuple[str, float, tuple[str, ...]]:
    if scan_fraction >= _SCAN_FRACTION:
        return "det_vlm", 0.9, (f"scan_fraction={scan_fraction:.2f}: no text layer, OCR needs the VLM",)
    if mean_div >= _DIVERGE_TOKEN:
        return "det_vlm", 0.7, (f"mean_token_divergence={mean_div:.2f}: VLM materially diverges from the text layer",)
    if tables_pages or figures_pages:
        return "det_vlm", 0.6, (
            f"structure present (tables on {tables_pages}, figures on {figures_pages} sampled pages): "
            "VLM helps structure where the deterministic source is weak",
        )
    return "deterministic", 0.75, (
        f"born-digital, low divergence ({mean_div:.2f}), simple structure: deterministic suffices -- VLM adds little",
    )
