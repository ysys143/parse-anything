"""`parse-anything` console entry point (target contract: docs/pdf-pipeline-requirements.md).

Renders pages, triages processing depth, runs deterministic extraction or VLM per page (batching
page-spanning tables), applies the born-digital value-oracle gate, and writes the layered artifacts
(document.md / document.json / structure / semantic / provenance / chunks.jsonl) + tables/ + assets/.

VLM is used only when a GEMINI_API_KEY is configured and the mode is det_vlm; otherwise the run stays
deterministic. The mode is the lever -- det_vlm without a key is a loud error, never a silent downgrade.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from parse_anything.cli_support import Runtime, safe_client
from parse_anything.config import load_settings
from parse_anything.pipeline.output import document_dir, write_outputs
from parse_anything.pipeline.run import run_document

_FIG_DESCRIBE_PROMPT = (
    "You are shown an image region from a document page. It may be a crop or the whole page. Decide what it is.\n"
    "If it is DECORATION -- an icon, bullet or marker, logo, divider or rule line, background "
    "texture/gradient, page-number badge, or a purely ornamental graphic that carries no information "
    "-- reply with exactly the single word: DECORATION\n"
    "Otherwise it is CONTENT. On the FIRST line output exactly `KIND: X` where X is ONE of: chart, plot, "
    "diagram, photo, map, screenshot, illustration. On the following lines describe it for a reader who "
    "cannot see it, in 2-4 sentences: what it depicts, its axes and units if any, and the main trend or "
    "the most important values. Write the description in the SAME language as the figure's own labels "
    "(keep the KIND line in English). Output only the KIND line and the description -- no other preamble, "
    "no markdown, no extra heading, and do NOT use the word DECORATION."
)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _wrap_image_input(args, runtime: Runtime) -> str | None:
    """FR-1: if ``--pdf`` is actually an image, wrap it into a thin 1-page PDF and repoint ``args`` at it,
    keeping the ORIGINAL image path as provenance (``ingested_from``) and filename (``original_filename``,
    so document.json shows the image, not the throwaway temp). Returns the temp PDF path for the caller to
    clean up, or None when the input is already a PDF. Raises on an undecodable image, but never leaks the
    temp file it created (cleaned up before the raise propagates). Warns when a multi-frame image drops
    pages (only frame 1 is wrapped)."""
    from .pipeline.imagewrap import image_to_pdf, is_image

    if not is_image(args.pdf):
        return None
    original = args.pdf
    fd, wrapped = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        n_frames = image_to_pdf(original, wrapped)
    except Exception:   # noqa: BLE001 -- corrupt/undecodable image: clean up the mkstemp file, re-raise
        with contextlib.suppress(OSError):
            os.unlink(wrapped)
        raise
    if n_frames > 1:   # data loss must not be silent -- the user gave N pages, we kept one
        print(f"warning: multi-frame image; only frame 1 of {n_frames} wrapped ({Path(original).name})",
              file=runtime.stdout)
    args.ingested_from = args.ingested_from or original   # the image, not the throwaway wrapper, is the origin
    args.original_filename = Path(original).name
    args.pdf = wrapped
    return wrapped


def run_cli(argv, runtime: Runtime, *, env_file: Path | None = None) -> int:
    args = _parse_args(argv)
    try:
        wrapped_pdf = _wrap_image_input(args, runtime)   # FR-1: image input flows through the normal PDF path
    except Exception as exc:   # noqa: BLE001 -- an unreadable image is a clean input error, not a traceback
        print(f"error: could not read image input ({type(exc).__name__})", file=runtime.stdout)
        return 2
    try:
        return _run(args, runtime, env_file=env_file)
    finally:
        if wrapped_pdf is not None:
            with contextlib.suppress(OSError):
                os.unlink(wrapped_pdf)


def _run(args, runtime: Runtime, *, env_file: Path | None = None) -> int:
    settings = load_settings(env_file=env_file or Path(".env"), environ=runtime.environ)
    key = settings.gemini_api_key
    out_root = args.out or (runtime.environ or {}).get("PARSE_ANYTHING_OUT_DIR") or "out"

    # Reprocessing prevention: the document_id is a content hash, so an existing document.json with
    # the same hash means this exact input was already processed. Skip (no re-run) unless --force.
    if not args.force:
        from parse_anything.pipeline.docmeta import document_id

        short_id, full_hash = document_id(args.pdf)
        existing = Path(out_root) / args.source_id / short_id / "document.json"
        if existing.exists():
            try:
                prev_hash = json.loads(existing.read_text(encoding="utf-8")).get("content_sha256")
            except (OSError, ValueError):
                prev_hash = None
            if prev_hash == full_hash:
                print(f"skipped: {args.source_id}/{short_id} already processed (--force to reprocess)", file=runtime.stdout)
                return 0

    profiles_dir = args.profiles_dir or (runtime.environ or {}).get("PARSE_ANYTHING_PROFILE_DIR") or "profiles"
    mode = None
    if args.use_profile:
        # Reuse a stored diagnosis instead of re-running it.
        from parse_anything.pipeline.profile import load_profile

        profile = load_profile(args.source_id, profiles_dir)
        if profile is not None:
            mode = profile.recommended_mode
            print(f"profile: source={args.source_id} mode={mode} tier={profile.tier} (stored)", file=runtime.stdout)
    if mode is None and args.diagnose:
        # D-1 picks the mode by measurement, then the whole run uses it (no per-page routing).
        if not key:
            print("error: --diagnose requires GEMINI_API_KEY (D-1 runs the VLM on sampled pages)", file=runtime.stdout)
            return 2
        from parse_anything.pipeline.diagnose import diagnose_source
        from parse_anything.pipeline.profile import from_d1_diagnosis, load_profile, save_profile

        prior = load_profile(args.source_id, profiles_dir)  # reuse calibrated thresholds if a profile exists
        diag = diagnose_source(args.pdf, vlm_client=safe_client(runtime), api_key=key, sample_size=args.sample_size,
                               thresholds=prior.thresholds if prior else None)
        mode = diag.recommended_mode
        save_profile(from_d1_diagnosis(diag, source_id=args.source_id, created_at=_now()), profiles_dir)
        print(f"diagnosis: mode={mode} confidence={diag.confidence:.2f} reason={diag.reasons[0]} (profile saved)", file=runtime.stdout)
    if mode is None:
        mode = "deterministic" if args.no_vlm else args.mode  # the mode IS the lever (no runtime routing)
    client = None
    if mode == "det_vlm":
        if not key:
            # Don't silently downgrade an explicit choice: a missing key is a misconfiguration.
            print("error: --mode det_vlm requires GEMINI_API_KEY (use --mode deterministic for no-VLM)", file=runtime.stdout)
            return 2
        client = safe_client(runtime)

    from parse_anything.pipeline.assemble import DetVlmOptions

    custom_prompt = args.prompt
    if args.prompt_file:
        custom_prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    options = DetVlmOptions(
        ground=not args.no_ground, spanning=not args.no_spanning,
        arithmetic=not args.no_arithmetic, prompt=custom_prompt,
        primary=args.primary, whole_doc=args.whole_doc,
    )

    # PaddleOCR (local-file upload) as the det_vlm primary transcriber (R10 --primary paddle), when configured.
    primary_transcribe = None
    if mode == "det_vlm" and options.primary == "paddle" and settings.paddle_api_key and settings.paddle_base_url:
        from parse_anything.pipeline.paddle_vlm import make_transcriber

        primary_transcribe = make_transcriber(safe_client(runtime), base_url=settings.paddle_base_url,
                                              token=settings.paddle_api_key, model=settings.paddle_model or "PaddleOCR-VL-1.6")

    # whole-doc: a one-shot multi-image transcriber (OpenAI /v1 at PADDLE_BASE_URL) so a model like
    # Unlimited-OCR (infer_multi) transcribes the whole document in one call and the substrate wraps it.
    primary_transcribe_multi = None
    if mode == "det_vlm" and args.whole_doc and settings.paddle_base_url:
        from parse_anything.pipeline.openai_vlm import make_multi_transcriber

        primary_transcribe_multi = make_multi_transcriber(
            safe_client(runtime), base_url=settings.paddle_base_url,
            token=settings.paddle_api_key or "", model=settings.paddle_model or "model")

    result = run_document(
        args.pdf, mode=mode, vlm_client=client, api_key=key or "",
        source_id=args.source_id, external_id=args.external_id, ingested_from=args.ingested_from,
        original_filename=getattr(args, "original_filename", None),   # set only for image-wrapped input (FR-1)
        options=options, primary_transcribe=primary_transcribe,
        primary_transcribe_multi=primary_transcribe_multi,
    )
    # Per-document dir = <out_root>/<source_id>/<document_id> (out_root resolved above).
    out_dir = document_dir(out_root, result)

    describe_figure: Callable[[bytes, str | None], str] | None = None
    if client is not None and key and not args.no_describe_figures:
        from parse_anything.pipeline.vlm import transcribe_image

        def _describe_figure(png: bytes, caption: str | None) -> str:
            prompt = _FIG_DESCRIBE_PROMPT + (f"\nThe figure's caption is: {caption}" if caption else "")
            return transcribe_image(png, prompt, api_key=key, client=client)
        describe_figure = _describe_figure

    from parse_anything.pipeline.ontology import bundled_ontology_root, load_ontology  # R15: injected node/zone ontology

    ontology = load_ontology(args.ontology or "default", bundled_ontology_root())
    write_outputs(result, out_dir, pdf_path=args.pdf, arithmetic=options.arithmetic,
                  inline_figures=not args.no_inline_figures, headings=not args.no_headings,
                  describe_figure=describe_figure, ontology=ontology, chunk=not args.no_chunks)
    if args.review:
        from parse_anything.pipeline.review import write_review

        write_review(args.pdf, result, out_dir / "review.html")

    n = len(result.pages)
    vlm_pages = sum(1 for p in result.pages if p.used_vlm)
    flagged = sum(1 for p in result.pages if p.flags and p.route != "folded")
    print(
        f"pages={n} mode={mode} doc={result.meta.document_id} vlm_pages={vlm_pages} flagged={flagged} out={out_dir}",
        file=runtime.stdout,
    )
    return 0


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="parse-anything",
                                     description="Deterministic-first, ontology-driven PDF -> agent-ready layered artifacts + RAG chunks")
    parser.add_argument("--pdf", required=True,
                        help="input document: a PDF, or an image (PNG/JPG/TIFF/...) wrapped into a 1-page PDF (FR-1)")
    parser.add_argument("--out", default=None, help="output root; default $PARSE_ANYTHING_OUT_DIR or ./out")
    parser.add_argument("--mode", choices=["deterministic", "det_vlm"], default="det_vlm",
                        help="deterministic (ODL+pypdfium2) or det_vlm (+VLM, value-oracle gated); default det_vlm")
    parser.add_argument("--no-vlm", action="store_true", help="alias for --mode deterministic")
    parser.add_argument("--diagnose", action="store_true", help="run D-1 diagnosis first, save a profile, and use the recommended mode")
    parser.add_argument("--use-profile", action="store_true", help="use a stored SourceProfile's mode (skip diagnosis) if one exists for --source-id")
    parser.add_argument("--profiles-dir", default=None, help="profile store; default $PARSE_ANYTHING_PROFILE_DIR or ./profiles")
    parser.add_argument("--ontology", default=None,
                        help="document ontology family (ontology/<family>.md) driving node role/zone tagging; default 'default'")
    parser.add_argument("--sample-size", type=int, default=4, help="pages D-1 samples when --diagnose (default 4)")
    parser.add_argument("--source-id", default="default", help="source (document stream) id; output groups by it")
    parser.add_argument("--external-id", default=None, help="caller-provided document id, preserved in metadata")
    parser.add_argument("--ingested-from", default=None, help="provenance origin (path/url); defaults to --pdf")
    parser.add_argument("--force", action="store_true", help="reprocess even if this content hash was already produced")
    parser.add_argument("--review", action="store_true", help="also write review.html (source vs extraction + flags)")
    # det_vlm behaviour opt-outs (all ON by default)
    parser.add_argument("--no-ground", action="store_true", help="det_vlm: skip ODL+pypdfium2 deterministic grounding")
    parser.add_argument("--no-spanning", action="store_true", help="det_vlm: skip page-spanning table reconstruction")
    parser.add_argument("--no-arithmetic", action="store_true", help="det_vlm: skip arithmetic-invariant guard")
    parser.add_argument("--no-inline-figures", action="store_true",
                        help="skip interleaving ODL figure (signature/stamp/logo) image refs into the page Markdown")
    parser.add_argument("--no-headings", action="store_true",
                        help="skip the chapter/section/subsection hierarchy (sections[] tree + #/##/### in Markdown)")
    parser.add_argument("--no-describe-figures", action="store_true",
                        help="det_vlm: skip the VLM text description generated for each cropped vector chart")
    parser.add_argument("--no-chunks", action="store_true",
                        help="skip building document.chunks.jsonl (the small-to-big parent/child retrieval chunks)")
    parser.add_argument("--primary", choices=["gemini", "paddle"], default="gemini",
                        help="det_vlm primary transcriber: gemini (grounded) or paddle (doc-specialised)")
    parser.add_argument("--whole-doc", action="store_true",
                        help="det_vlm: transcribe the WHOLE document in ONE multi-image call (OpenAI /v1 at "
                             "PADDLE_BASE_URL) and wrap that one-shot output -- for models like Unlimited-OCR (infer_multi)")
    parser.add_argument("--prompt", default=None, help="det_vlm: custom base prompt (overrides default)")
    parser.add_argument("--prompt-file", default=None, help="det_vlm: read custom base prompt from a file")
    return parser.parse_args(argv)


def main() -> int:
    """Console entry point (`parse-anything`)."""
    return run_cli(sys.argv[1:], Runtime())


if __name__ == "__main__":
    raise SystemExit(main())
