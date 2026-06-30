"""B-1 / B-2: reuse ODL's official docling-fast server, swap only the VLM via monkeypatch.

The official server (``opendataloader_pdf.hybrid_server``) already speaks ODL's hybrid protocol
(multipart/page_ranges in, DoclingDocument out) and builds a Docling ``DocumentConverter`` in
``create_converter``. ``create_app``'s lifespan calls ``create_converter(...)`` via the module
global, so replacing ``hs.create_converter`` swaps the VLM without forking 1000+ lines.

- **B-1** (``install_b1``): Docling ``VlmPipeline`` + ``ApiVlmOptions`` pointed at Gemini's
  OpenAI-compatible endpoint -> the VLM transcribes the whole page to Markdown.
- **B-2** (``install_b2``): the standard ``PdfPipelineOptions`` (layout + TableFormer + OCR) but
  with ``picture_description_options`` set to ``PictureDescriptionApiOptions(Gemini)`` -> only
  figure descriptions go to our VLM; text/tables stay Docling.

Gemini key comes from ``load_settings`` (.env / env). ``enable_remote_services=True`` is required
for Docling to call an external API.
"""
from __future__ import annotations

import argparse
import logging
from typing import Any, Callable

logger = logging.getLogger("odl_vl_track_b.backend_docling")

from odl_vl.providers import DEFAULT_GEMINI_MODEL

GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_MODEL = DEFAULT_GEMINI_MODEL  # keep in lockstep with the rest of the repo (providers.py)

B1_PROMPT = (
    "Convert this page to clean, faithful GitHub-Flavored Markdown. Preserve reading order, "
    "headings, lists, and tables (Markdown table syntax). Do not invent text or numbers. "
    "Output only the Markdown."
)
B2_PROMPT = "Describe this image or chart concisely (1-2 sentences), including any axis labels or key values."


def _gemini_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _b1_create_converter(api_key: str, model: str, prompt: str) -> Callable[..., Any]:
    def create_converter(**_kwargs: Any) -> Any:
        # OCR/enrichment kwargs from the official lifespan are ignored: VlmPipeline transcribes
        # the page image directly, so layout/OCR/TableFormer do not apply.
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import VlmPipelineOptions
        from docling.datamodel.pipeline_options_vlm_model import ApiVlmOptions, ResponseFormat
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.pipeline.vlm_pipeline import VlmPipeline

        vlm_options = ApiVlmOptions(
            url=GEMINI_OPENAI_URL,
            headers=_gemini_headers(api_key),
            params={"model": model},
            prompt=prompt,
            response_format=ResponseFormat.MARKDOWN,
            scale=2.0,
            timeout=120,
        )
        options = VlmPipelineOptions(enable_remote_services=True, vlm_options=vlm_options)
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_cls=VlmPipeline, pipeline_options=options)}
        )

    return create_converter


def _b2_create_converter(api_key: str, model: str, prompt: str) -> Callable[..., Any]:
    def create_converter(
        *,
        disable_ocr: bool = False,
        picture_description_prompt: str | None = None,
        **_kwargs: Any,
    ) -> Any:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            PictureDescriptionApiOptions,
            TableFormerMode,
            TableStructureOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption

        picture_options = PictureDescriptionApiOptions(
            url=GEMINI_OPENAI_URL,
            headers=_gemini_headers(api_key),
            params={"model": model},
            prompt=picture_description_prompt or prompt,
            timeout=120,
        )
        options = PdfPipelineOptions(
            do_ocr=not disable_ocr,
            do_table_structure=True,
            table_structure_options=TableStructureOptions(mode=TableFormerMode.ACCURATE),
            do_picture_description=True,
            picture_description_options=picture_options,
            generate_picture_images=True,
            enable_remote_services=True,
        )
        return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})

    return create_converter


def install_b1(api_key: str, *, model: str = DEFAULT_MODEL, prompt: str = B1_PROMPT) -> Any:
    """Patch the official server's create_converter to the B-1 VlmPipeline+Gemini variant."""
    from opendataloader_pdf import hybrid_server as hs

    hs.create_converter = _b1_create_converter(api_key, model, prompt)  # type: ignore[attr-defined]
    return hs


def install_b2(api_key: str, *, model: str = DEFAULT_MODEL, prompt: str = B2_PROMPT) -> Any:
    """Patch the official server's create_converter to the B-2 picture-description+Gemini variant."""
    from opendataloader_pdf import hybrid_server as hs

    hs.create_converter = _b2_create_converter(api_key, model, prompt)  # type: ignore[attr-defined]
    return hs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Track B (B-1/B-2): official docling-fast server with Gemini VLM")
    parser.add_argument("--variant", choices=["b1", "b2"], required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--b2-ocr", action="store_true",
                        help="B-2: enable Docling OCR (for scanned inputs; off by default)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from odl_vl.config import load_settings

    settings = load_settings()
    if not settings.has_gemini:
        raise SystemExit("GEMINI_API_KEY required for B-1/B-2 (Gemini VLM backend)")

    if args.variant == "b1":
        hs = install_b1(settings.gemini_api_key, model=args.model)  # type: ignore[arg-type]
        app = hs.create_app()
    else:
        hs = install_b2(settings.gemini_api_key, model=args.model)  # type: ignore[arg-type]
        # OCR off by default: born-digital text layer needs no OCR, and this env's OCR engine
        # (PP-OCRv6) is misconfigured. Pass --b2-ocr to re-enable for scanned inputs.
        app = hs.create_app(enrich_picture_description=True, disable_ocr=not args.b2_ocr)

    import uvicorn

    logger.info("%s docling-fast backend on http://%s:%d (model=%s)", args.variant.upper(), args.host, args.port, args.model)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
