"""B-4 deterministic augmentation: grounding pre-hook + value-oracle guard post-hook.

B-4 = B-3 proxy + det_vlm's accuracy weapons, re-parsed from the PDF inside the proxy. ODL only
ships the PDF + page range (no 1st-pass md, no prompt), so the proxy reconstructs the
deterministic context itself:

- **grounding pre-hook** (`make_grounding_hook`): pypdfium2 text layer (value authority) + ODL
  structure outline injected into the prompt via ``grounding.build_grounded_prompt``.
- **guard post-hook** (`make_guard_hook`): numbers the VLM emitted that are absent from the
  pypdfium2 text layer get flagged (``oracle.fabrication_flags``) — the born-digital value oracle.

This re-parse (ODL local + pypdfium2) is the duplication Track C would remove by shipping ODL's
1st-pass result in the HybridRequest; its real cost is a scorecard measurement point. ODL parse
is cached per PDF path and fails soft to pypdfium2-only grounding.
"""
from __future__ import annotations

from typing import Any, Callable

from odl_vl.pipeline import deterministic, grounding, odl_extract
from odl_vl.pipeline.oracle import fabrication_flags

OdlRunner = Callable[[str], dict]


def make_grounding_hook(*, use_odl: bool = True, runner: OdlRunner | None = None, use_supplied: bool = True):
    """Pre-hook: inject pypdfium2 text (+ optional ODL structure) into the prompt.

    The ODL document is parsed once per PDF path and cached; parse failure falls back to
    pypdfium2-only grounding (still preserves numeric values). ``runner`` is injectable for tests.

    ``use_supplied`` (Track C): when True and ODL shipped a 1st-pass Markdown, ground on that
    directly (no in-proxy re-parse). False forces B-4's in-proxy re-parse even if md was supplied
    -- the lever for benchmarking Track C (supplied) vs B-4 (re-parse).
    """
    odl_cache: dict[str, Any] = {}

    def _odl_page(pdf_path: str, page_index: int) -> Any | None:
        if not use_odl:
            return None
        if pdf_path not in odl_cache:
            try:
                odl_cache[pdf_path] = odl_extract.extract(pdf_path, runner=runner)
            except Exception:
                odl_cache[pdf_path] = None
        doc = odl_cache[pdf_path]
        if doc is None:
            return None
        for page in doc.pages:
            if page.page_index == page_index:
                return page
        return None

    def hook(pdf_path: str, page_index: int, _png: bytes, prompt: str,
             supplied_md: str | None = None) -> tuple[str, tuple[str, ...]]:
        if use_supplied and supplied_md is not None and supplied_md.strip():
            # Track C: ODL already shipped its 1st-pass deterministic Markdown -- ground on it
            # directly, NO re-parse (the whole point: remove B-4's in-proxy odl_extract/pypdfium2).
            grounded = grounding.build_grounded_prompt(prompt, supplied_md, None)
            return grounded, ()
        # B-4: reconstruct grounding by re-parsing the PDF in-proxy.
        pypdf_text = deterministic.page_text(pdf_path, page_index)
        odl_page = _odl_page(pdf_path, page_index)
        grounded = grounding.build_grounded_prompt(prompt, pypdf_text, odl_page)
        return grounded, ()

    return hook


def make_guard_hook(*, min_value: float | None = None):
    """Post-hook: flag VLM numbers absent from the pypdfium2 value oracle (fabrication-suspect).

    Each flag is ``unsourced_number:<value>`` (mirrors the det_vlm pipeline's flag vocabulary).
    """

    def hook(pdf_path: str, page_index: int, markdown: str) -> tuple[str, ...]:
        source = [t.raw for t in deterministic.number_tokens(pdf_path, page_index, min_value=min_value)]
        flags = fabrication_flags(markdown, source, min_value=min_value)
        return tuple(f"unsourced_number:{v}" for v in flags)

    return hook
