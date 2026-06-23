"""Mode-driven document assembly (replaces runtime per-page auto-routing).

Two execution modes, both using ODL + pypdfium2 together (processing-tiers §2.6, F17):
- ``deterministic``: ODL structure/clean-text + pypdfium2 value-completeness backstop. No VLM.
- ``det_vlm``: + VLM, reconciled, value-oracle gating VLM numbers (R1.3).

Reconciliation precedence (R-M1): values = pypdfium2 (+ value oracle); structure = VLM / ODL;
clean text = ODL. The mode is chosen by the source profile, not per-page at runtime.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .deterministic import page_text
from .guards import extract_numbers
from .odl_extract import OdlDocument, OdlPage, OdlTable
from .odl_extract import extract as odl_extract
from .render import page_count
from .run import DocumentResult, PageOutcome

ExecutionMode = Literal["deterministic", "det_vlm"]


@dataclass(frozen=True, slots=True)
class DetVlmOptions:
    """det_vlm behaviour toggles -- all default ON (opt-out), double_pass only fires on scans."""
    ground: bool = True        # R8.3 inject ODL + pypdfium2 deterministic grounding
    spanning: bool = True      # R8.2 reconstruct page-spanning tables via multi-image VLM
    double_pass: bool = True   # R8.6 dual-provider pass on oracle-less scan pages
    arithmetic: bool = True    # R8.7 arithmetic-invariant guard on totals/subtotals
    prompt: str | None = None  # R8.4 custom base prompt (overrides DEFAULT/SCAN)
    input_quality_min: float = 50.0  # R8.8 Laplacian-variance blur threshold (per-domain tunable)
    primary: str = "gemini"    # R10 primary VLM: "gemini" | "paddle" | "combined" (reconcile both)


def _table_markdown(table: OdlTable) -> str:
    if not table.cells:
        return ""
    width = max(len(r) for r in table.cells)
    rows = [list(r) + [""] * (width - len(r)) for r in table.cells]
    lines = ["| " + " | ".join(c.replace("|", r"\|") for c in rows[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    for r in rows[1:]:
        lines.append("| " + " | ".join(c.replace("|", r"\|") for c in r) + " |")
    return "\n".join(lines)


def _page_markdown(odl_page: OdlPage, tables: list[OdlTable]) -> str:
    parts: list[str] = []
    if odl_page.text.strip():
        parts.append(odl_page.text.strip())
    parts.extend(_table_markdown(t) for t in tables)
    return "\n\n".join(p for p in parts if p)


def _recurring_numbers(pypdf_texts: list[str], *, min_fraction: float = 0.5) -> set[str]:
    """Numbers appearing on many pages are running headers/footers (e.g. a report number or
    year); exclude them from the completeness check so it surfaces real dropped data."""
    n = len(pypdf_texts)
    if n < 2:
        return set()
    freq: Counter[str] = Counter()
    for text in pypdf_texts:
        freq.update(set(extract_numbers(text)))
    threshold = max(2, int(n * min_fraction))
    return {num for num, count in freq.items() if count >= threshold}


def _completeness_flags(pypdf_text: str, odl_text: str, recurring: set[str], *, cap: int = 12) -> list[str]:
    """ODL drops a real number for cleanliness (F17 'A100 40GB'); pypdfium2 is the value
    authority. Flag pypdfium2 numbers (minus recurring header noise) missing from ODL text."""
    dropped = sorted((set(extract_numbers(pypdf_text)) - recurring) - set(extract_numbers(odl_text)))
    flags = [f"odl_dropped_number:{v}" for v in dropped[:cap]]
    if len(dropped) > cap:
        flags.append(f"odl_dropped_number_truncated:{len(dropped) - cap}")
    return flags


def assemble_document(
    pdf_path: str,
    *,
    mode: ExecutionMode = "deterministic",
    vlm_client: Any | None = None,
    api_key: str = "",
    odl_runner: Callable[[str], dict] | None = None,
    source_id: str = "default",
    external_id: str | None = None,
    ingested_from: str | None = None,
    options: DetVlmOptions = DetVlmOptions(),
    second_pass: Any | None = None,
    primary_transcribe: Any | None = None,
) -> DocumentResult:
    from .docmeta import build_meta

    odl_doc: OdlDocument = odl_extract(pdf_path, runner=odl_runner)
    n = page_count(pdf_path)
    pypdf_texts = [page_text(pdf_path, i) for i in range(n)]
    recurring = _recurring_numbers(pypdf_texts)

    # det_vlm reconstructs page-spanning tables in ONE multi-image VLM request (R8.2, F9); other
    # pages (and all of deterministic mode) are processed singly.
    spanning = mode == "det_vlm" and options.spanning and options.primary in ("gemini", "combined") and vlm_client is not None
    groups = _spanning_groups(odl_doc, n) if spanning else [[i] for i in range(n)]

    outcomes: list[PageOutcome] = []
    for group in groups:
        if len(group) > 1:
            outcomes.extend(_assemble_spanning(pdf_path, group, pypdf_texts, recurring,
                                               vlm_client=vlm_client, api_key=api_key, options=options))
            continue
        i = group[0]
        odl_page = odl_doc.pages[i] if i < len(odl_doc.pages) else OdlPage(i, "", (), ())
        if mode == "deterministic":
            outcomes.append(_assemble_deterministic(i, odl_page, pypdf_texts[i], recurring))
        elif mode == "det_vlm":
            outcomes.append(
                _assemble_det_vlm(pdf_path, i, odl_page, pypdf_texts[i], recurring, vlm_client=vlm_client,
                                  api_key=api_key, options=options, second_pass=second_pass,
                                  primary_transcribe=primary_transcribe)
            )
        else:
            raise ValueError(f"unknown mode: {mode!r}")
    meta = build_meta(pdf_path, source_id=source_id, external_id=external_id, ingested_from=ingested_from, mode=mode, n_pages=n)
    return DocumentResult(tuple(outcomes), structure=odl_doc, meta=meta)


def _continues(odl_doc: OdlDocument, a: int, b: int) -> bool:
    """Page b continues page a if a table on b links back (ODL previous_table_id) to one on a."""
    if a >= len(odl_doc.pages) or b >= len(odl_doc.pages):
        return False
    ids_a = {t.table_id for t in odl_doc.pages[a].tables if t.table_id}
    return any(t.previous_table_id in ids_a for t in odl_doc.pages[b].tables if t.previous_table_id)


def _spanning_groups(odl_doc: OdlDocument, n: int) -> list[list[int]]:
    """Group consecutive pages joined by a page-spanning table; standalone pages are singletons."""
    groups: list[list[int]] = []
    i = 0
    while i < n:
        group = [i]
        while i + 1 < n and _continues(odl_doc, i, i + 1):
            i += 1
            group.append(i)
        groups.append(group)
        i += 1
    return groups


def _assemble_spanning(
    pdf_path: str, group: list[int], pypdf_texts: list[str], recurring: set[str], *,
    vlm_client: Any, api_key: str, options: DetVlmOptions,
) -> list[PageOutcome]:
    """Reconstruct a page-spanning table from ALL its pages in one multi-image VLM request (F9).
    The merged table is attributed to the start page; continuation pages are folded."""
    from .deterministic import number_tokens
    from .odl_extract import extract_caption_labels
    from .oracle import fabrication_flags
    from .render import render_page_png
    from .run import SPANNING_PROMPT
    from .vlm import VlmError, transcribe_images

    start = group[0]
    pngs = [render_page_png(pdf_path, j) for j in group]
    prompt = SPANNING_PROMPT
    if options.ground:  # ground the spanning prompt with the group's combined text layer
        from .grounding import build_grounded_prompt

        prompt = build_grounded_prompt(SPANNING_PROMPT, "\n".join(pypdf_texts[j] for j in group), None)
    try:
        markdown = transcribe_images(pngs, prompt, api_key=api_key, client=vlm_client)
    except VlmError:  # degrade: per-page deterministic for the whole group, never drop
        from .odl_extract import substantial_tables

        out = []
        for j in group:
            page = OdlPage(j, pypdf_texts[j], (), ())
            out.append(PageOutcome(j, "det_vlm", False, _page_markdown(page, list(substantial_tables(page))), 0.0,
                                   ("spanning_vlm_failed",)))
        return out

    source = [t.value for j in group for t in number_tokens(pdf_path, j, min_value=1000)]
    flags = [f"unsourced_number:{v}" for v in fabrication_flags(markdown, source, min_value=1000)]
    flags.append("spanning_pages:" + "-".join(str(j) for j in group))
    outcomes = [PageOutcome(start, "det_vlm", True, markdown, 0.0, tuple(flags), extract_caption_labels(markdown))]
    outcomes += [PageOutcome(j, "folded", False, "", 0.0, (f"folded_into:{start}",)) for j in group[1:]]
    return outcomes


def _assemble_deterministic(page_index: int, odl_page: OdlPage, pypdf_text: str, recurring: set[str]) -> PageOutcome:
    from .odl_extract import substantial_tables

    tables = substantial_tables(odl_page)
    markdown = _page_markdown(odl_page, tables)
    flags = _completeness_flags(pypdf_text, odl_page.text, recurring)
    return PageOutcome(page_index, "deterministic", False, markdown, 0.0, tuple(flags))


def _assemble_det_vlm(
    pdf_path: str, page_index: int, odl_page: OdlPage, pypdf_text: str, recurring: set[str], *, vlm_client: Any, api_key: str,
    options: DetVlmOptions = DetVlmOptions(), second_pass: Any | None = None,
    primary_transcribe: Any | None = None,
) -> PageOutcome:
    """Accuracy mode: VLM is the visual-structure source; pypdfium2 is the value authority
    (value oracle gates VLM numbers -- R-M1); ODL structure is available for rich output (R2).
    A page is never dropped -- when VLM is unavailable or fails it degrades to the deterministic
    assembly with a flag (R-B3 escalation signal)."""
    from .deterministic import number_tokens
    from .odl_extract import extract_caption_labels
    from .oracle import fabrication_flags
    from .quality import is_low_quality
    from .render import render_page_png
    from .run import DEFAULT_PROMPT, LOW_QUALITY_SENTINEL, SCAN_PROMPT
    from .vlm import VlmError, transcribe_image

    needs_gemini = options.primary in ("gemini", "combined")
    if needs_gemini and vlm_client is None:
        det = _assemble_deterministic(page_index, odl_page, pypdf_text, recurring)
        return PageOutcome(page_index, "det_vlm", False, det.markdown, 0.0, (*det.flags, "vlm_unavailable"))

    flags: list[str] = []
    png = render_page_png(pdf_path, page_index)
    if is_low_quality(png, min_laplacian_variance=options.input_quality_min):
        flags.append("low_quality_input")
    # No text layer == scan-like: use the legibility-gate prompt (F6) so a degraded scan
    # abstains (IMAGE_TOO_LOW_QUALITY) instead of fabricating. Prompt choice by deterministic
    # signal is not routing -- the VLM still runs on every page. A custom prompt (R8.4) overrides.
    base_prompt = options.prompt or (SCAN_PROMPT if not pypdf_text.strip() else DEFAULT_PROMPT)
    if options.ground:  # R8.3 ODL + pypdfium2 dual injection (no-op on scans with no text layer)
        from .grounding import build_grounded_prompt

        prompt = build_grounded_prompt(base_prompt, pypdf_text, odl_page)
    else:
        prompt = base_prompt
    if options.primary == "paddle":  # R10 doc-specialised VLM as the primary transcriber (no prompt/sentinel)
        if primary_transcribe is None:
            det = _assemble_deterministic(page_index, odl_page, pypdf_text, recurring)
            return PageOutcome(page_index, "det_vlm", False, det.markdown, 0.0, (*flags, "paddle_unavailable"))
        try:
            markdown = primary_transcribe(png)
        except Exception:
            det = _assemble_deterministic(page_index, odl_page, pypdf_text, recurring)
            return PageOutcome(page_index, "det_vlm", False, det.markdown, 0.0, (*flags, "paddle_failed"))
    else:  # gemini (grounded) -- optionally reconciled with paddle tables (combined)
        try:
            markdown = transcribe_image(png, prompt, api_key=api_key, client=vlm_client)
        except VlmError as exc:
            det = _assemble_deterministic(page_index, odl_page, pypdf_text, recurring)
            return PageOutcome(page_index, "det_vlm", False, det.markdown, 0.0, (*flags, str(exc)))
        if markdown.strip() == LOW_QUALITY_SENTINEL:
            return PageOutcome(page_index, "det_vlm", True, "", 0.0, (*flags, "illegible_low_quality"))
        if options.primary == "combined" and primary_transcribe is not None:  # R10 gemini text + paddle tables
            from .reconcile import merge_outputs
            try:
                markdown = merge_outputs(markdown, primary_transcribe(png))
            except Exception:
                flags.append("combine_secondary_unavailable")
    source = [t.value for t in number_tokens(pdf_path, page_index, min_value=1000)]
    flags.extend(f"unsourced_number:{v}" for v in fabrication_flags(markdown, source, min_value=1000))
    # Scans have NO value oracle (no text layer), so a second independent provider pass is the
    # only consistency check -- flag numbers the two passes disagree on (F4, R8.6). Provider-agnostic.
    if options.double_pass and second_pass is not None and not pypdf_text.strip():
        from .guards import dual_pass_disagreements, extract_numbers
        try:
            other = second_pass(png)
            disagree = dual_pass_disagreements(extract_numbers(markdown), extract_numbers(other))
            flags.extend(f"dual_pass_disagree:{v}" for v in sorted(disagree))
        except Exception:  # second provider failed -- flag, never drop the page (R-B3)
            flags.append("double_pass_unavailable")
    labels = extract_caption_labels(markdown)  # VLM reads captions ODL misses (R4.3)
    return PageOutcome(page_index, "det_vlm", True, markdown, 0.0, tuple(flags), labels)
