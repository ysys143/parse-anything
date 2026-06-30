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


def _b1_create_converter(
    api_key: str, model: str, prompt: str, *, url: str = GEMINI_OPENAI_URL, headers: dict[str, str] | None = None
) -> Callable[..., Any]:
    def create_converter(**_kwargs: Any) -> Any:
        # OCR/enrichment kwargs from the official lifespan are ignored: VlmPipeline transcribes
        # the page image directly, so layout/OCR/TableFormer do not apply.
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import VlmPipelineOptions
        from docling.datamodel.pipeline_options_vlm_model import ApiVlmOptions, ResponseFormat
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.pipeline.vlm_pipeline import VlmPipeline

        vlm_options = ApiVlmOptions(
            url=url,
            headers=headers if headers is not None else _gemini_headers(api_key),
            params={"model": model},
            prompt=prompt,
            response_format=ResponseFormat.MARKDOWN,
            scale=2.0,
            timeout=600,  # Paddle shim (job poll + retries) can be slow; don't let docling cut it off
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


def install_b1_paddle(settings: Any, *, prompt: str = B1_PROMPT) -> Any:
    """B-1 with Paddle: start an OpenAI-compat shim over the Paddle job API and point docling's
    VlmPipeline at it. Lets docling structure Paddle's transcription the same way it does Gemini's."""
    from opendataloader_pdf import hybrid_server as hs

    import time

    from odl_vl.pipeline import paddle_vlm
    from odl_vl.providers import ProviderHttpClient, SafeTransport, UrllibTransport
    from odl_vl_track_b.paddle_openai_shim import serve_shim_background

    client = ProviderHttpClient(transport=SafeTransport(UrllibTransport(timeout_seconds=90)))

    def _paddle(png: bytes) -> str:
        last = ""
        for _ in range(3):  # Paddle job API is occasionally flaky (http_0); retry
            try:
                return paddle_vlm.transcribe(
                    png, client=client, base_url=settings.paddle_base_url, token=settings.paddle_api_key,
                    model=settings.paddle_model or paddle_vlm._DEFAULT_MODEL, doc_preprocess=True,
                    poll_interval=4, max_polls=90,
                )
            except Exception as exc:
                last = type(exc).__name__
                time.sleep(4)
        raise RuntimeError(f"paddle_retries_exhausted:{last}")

    shim = serve_shim_background(_paddle)
    shim_url = f"http://127.0.0.1:{shim.server_address[1]}/v1/chat/completions"
    hs.create_converter = _b1_create_converter(  # type: ignore[attr-defined]
        "unused", "paddle", prompt, url=shim_url, headers={}
    )
    return hs


def install_b2(api_key: str, *, model: str = DEFAULT_MODEL, prompt: str = B2_PROMPT) -> Any:
    """Patch the official server's create_converter to the B-2 picture-description+Gemini variant."""
    from opendataloader_pdf import hybrid_server as hs

    hs.create_converter = _b2_create_converter(api_key, model, prompt)  # type: ignore[attr-defined]
    return hs


_MROPE_SECTION: list[int] | None = None


def _paddleocr_mrope_section() -> list[int]:
    """mrope_section from PaddleOCR-VL's config.json (transformers strips it under rope_type=default).
    Read once and cached."""
    global _MROPE_SECTION
    if _MROPE_SECTION is None:
        import json

        from huggingface_hub import hf_hub_download

        cfg = json.load(open(hf_hub_download("PaddlePaddle/PaddleOCR-VL-1.6", "config.json"), encoding="utf-8"))
        _MROPE_SECTION = cfg.get("rope_scaling", {}).get("mrope_section", [16, 24, 24])
    return _MROPE_SECTION


def _patch_paddleocr_vl_config() -> None:
    """transformers 5.8.x ships PaddleOCR-VL with a config bug: sub_configs declares
    ``text_config: PaddleOCRTextConfig`` and modeling reads ``config.text_config``, but the model's
    config.json keeps text params at the TOP LEVEL (no ``text_config`` key), so from_pretrained
    never builds the sub-config and ``config.text_config`` is missing.

    Bridge it by deriving a real PaddleOCRTextConfig from the top-level params on demand (cached).
    Returning a proper PaddleOCRTextConfig (which has no sub_configs) avoids the to_dict recursion
    that returning ``self`` caused. Idempotent."""
    import inspect

    from transformers.models.paddleocr_vl.configuration_paddleocr_vl import (
        PaddleOCRTextConfig,
        PaddleOCRVLConfig,
    )

    if isinstance(getattr(PaddleOCRVLConfig, "text_config", None), property):
        return

    _text_params = [
        p for p in inspect.signature(PaddleOCRTextConfig.__init__).parameters if p not in ("self", "kwargs")
    ]

    def _get(self: Any) -> Any:
        cached = self.__dict__.get("_tc_obj")
        if cached is None:
            cached = PaddleOCRTextConfig(**{k: getattr(self, k) for k in _text_params if hasattr(self, k)})
            # transformers drops mrope_section from rope_parameters when rope_type=="default", but
            # PaddleOCR-VL's modeling reads config.rope_parameters["mrope_section"] (mRoPE). Restore it.
            section = _paddleocr_mrope_section()
            for attr in ("rope_parameters", "rope_scaling"):
                rp = getattr(cached, attr, None)
                if isinstance(rp, dict) and "mrope_section" not in rp:
                    rp["mrope_section"] = section
            self.__dict__["_tc_obj"] = cached
        return cached

    def _set(self: Any, value: Any) -> None:
        # from_pretrained / save may assign; keep a real sub-config if given, else ignore.
        if isinstance(value, PaddleOCRTextConfig):
            self.__dict__["_tc_obj"] = value

    PaddleOCRVLConfig.text_config = property(_get, _set)  # type: ignore[attr-defined]


def _paddleocr_vl_local_options() -> Any:
    """docling InlineVlmOptions for PaddleOCR-VL-1.6 run LOCALLY via transformers (no API).
    Same model our official-API path uses (PaddleOCR-VL-1.6), but on-device: ERNIE-4.5 + NaViT,
    ~1.0B, AutoModelForImageTextToText, needs trust_remote_code + transformers>=5."""
    _patch_paddleocr_vl_config()
    from docling.datamodel.pipeline_options_vlm_model import (
        InferenceFramework,
        InlineVlmOptions,
        ResponseFormat,
        TransformersModelType,
    )

    return InlineVlmOptions(
        repo_id="PaddlePaddle/PaddleOCR-VL-1.6",
        prompt="Convert this page to Markdown, preserving tables and reading order.",
        response_format=ResponseFormat.MARKDOWN,
        inference_framework=InferenceFramework.TRANSFORMERS,
        transformers_model_type=TransformersModelType.AUTOMODEL_IMAGETEXTTOTEXT,
        # trust_remote_code=False so docling uses transformers' BUILT-IN PaddleOCRVL classes --
        # the ones our _patch_paddleocr_vl_config patched (remote dynamic classes would bypass it).
        trust_remote_code=False,
        torch_dtype="bfloat16",
    )


def install_b1_local(preset: str = "GRANITEDOCLING_MLX") -> Any:
    """B-1 with docling's BUILT-IN local VLM (no API): VlmPipeline runs an InlineVlmOptions model
    on-device. Built-in presets (GraniteDocling/SmolDocling via MLX) by name; "PADDLEOCR_VL" runs
    PaddleOCR-VL-1.6 locally via transformers. No keys, no network at inference."""
    from opendataloader_pdf import hybrid_server as hs

    from docling.datamodel import vlm_model_specs

    if preset == "PADDLEOCR_VL":
        vlm_options = _paddleocr_vl_local_options()
    else:
        vlm_options = getattr(vlm_model_specs, preset)

    def create_converter(**_kwargs: Any) -> Any:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import VlmPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.pipeline.vlm_pipeline import VlmPipeline

        options = VlmPipelineOptions(vlm_options=vlm_options)  # local model -> no enable_remote_services
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_cls=VlmPipeline, pipeline_options=options)}
        )

    hs.create_converter = create_converter  # type: ignore[attr-defined]
    return hs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Track B (B-1/B-2): official docling-fast server with Gemini VLM")
    parser.add_argument("--variant", choices=["b1", "b2"], required=True)
    parser.add_argument("--provider", choices=["gemini", "paddle", "local"], default="gemini",
                        help="b1 only: paddle=OpenAI-compat shim over job API; local=docling built-in VLM (on-device)")
    parser.add_argument("--local-model", default="GRANITEDOCLING_MLX",
                        help="b1 local: docling vlm_model_specs preset (e.g. GRANITEDOCLING_MLX, SMOLDOCLING_MLX)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--b2-ocr", action="store_true",
                        help="B-2: enable Docling OCR (for scanned inputs; off by default)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from odl_vl.config import load_settings

    settings = load_settings()
    _no_gemini_key = args.variant == "b1" and args.provider in ("paddle", "local")
    if not _no_gemini_key and not settings.has_gemini:
        raise SystemExit("GEMINI_API_KEY required for B-1/B-2 (Gemini VLM backend)")

    if args.variant == "b1":
        if args.provider == "paddle":
            if not settings.has_paddle:
                raise SystemExit("B-1 paddle requires PADDLE_BASE_URL + PADDLE_API_KEY")
            hs = install_b1_paddle(settings)
        elif args.provider == "local":
            hs = install_b1_local(args.local_model)
        else:
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
