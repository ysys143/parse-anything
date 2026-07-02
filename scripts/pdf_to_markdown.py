"""PDF -> Markdown pipeline CLI (target contract: docs/pdf-pipeline-requirements.md).

Renders pages, triages processing depth, runs deterministic extraction or VLM per page
(batching page-spanning tables), applies the born-digital value oracle gate, and writes
per-page Markdown + document.md + ledger.jsonl + results.jsonl.

VLM is used only when a GEMINI_API_KEY is configured and --no-vlm is not passed; otherwise
pages route deterministically and VLM-needed pages degrade to the text layer with a flag.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from parse_anything.cli_support import Runtime, safe_client  # noqa: E402
from parse_anything.config import load_settings  # noqa: E402
from parse_anything.pipeline.output import document_dir, write_outputs  # noqa: E402
from parse_anything.pipeline.run import run_document  # noqa: E402

_FIG_DESCRIBE_PROMPT = (
    "You are shown a small image cropped from a document page. Decide what it is.\n"
    "If it is DECORATION -- an icon, bullet or marker, logo, divider or rule line, background "
    "texture/gradient, page-number badge, or a purely ornamental graphic that carries no information "
    "-- reply with exactly the single word: DECORATION\n"
    "Otherwise it is CONTENT -- a chart, plot, diagram, photograph, illustration, screenshot, map, or "
    "table. Describe it for a reader who cannot see it, in 2-4 sentences: what it depicts, its axes and "
    "units if any, and the main trend or the most important values. Respond in the SAME language as the "
    "figure's own labels. Output only the description -- no preamble, no markdown, no heading, and do "
    "NOT use the word DECORATION."
)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def run_cli(argv, runtime: Runtime, *, env_file: Path | None = None) -> int:
    args = _parse_args(argv)
    settings = load_settings(env_file=env_file or _REPO / ".env", environ=runtime.environ)
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
        primary=args.primary,
    )

    # PaddleOCR (local-file upload) as the det_vlm primary transcriber (R10 --primary paddle), when configured.
    primary_transcribe = None
    if mode == "det_vlm" and options.primary == "paddle" and settings.paddle_api_key and settings.paddle_base_url:
        from parse_anything.pipeline.paddle_vlm import make_transcriber

        primary_transcribe = make_transcriber(safe_client(runtime), base_url=settings.paddle_base_url,
                                              token=settings.paddle_api_key, model=settings.paddle_model or "PaddleOCR-VL-1.6")

    result = run_document(
        args.pdf, mode=mode, vlm_client=client, api_key=key or "",
        source_id=args.source_id, external_id=args.external_id, ingested_from=args.ingested_from,
        options=options, primary_transcribe=primary_transcribe,
    )
    # Per-document dir = <out_root>/<source_id>/<document_id> (out_root resolved above).
    out_dir = document_dir(out_root, result)

    describe_figure = None  # R14: a VLM text description for each cropped vector chart (det_vlm only)
    if client is not None and key and not args.no_describe_figures:
        from parse_anything.pipeline.vlm import transcribe_image

        def describe_figure(png: bytes, caption: str | None) -> str:
            prompt = _FIG_DESCRIBE_PROMPT + (f"\nThe figure's caption is: {caption}" if caption else "")
            return transcribe_image(png, prompt, api_key=key, client=client)

    from parse_anything.pipeline.ontology import load_ontology  # R15: injected node/zone ontology (family-selectable)

    ontology = load_ontology(args.ontology or "default", _REPO / "ontology")
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
    parser = argparse.ArgumentParser(description="PDF -> Markdown pipeline (diagnose-then-configure modes)")
    parser.add_argument("--pdf", required=True)
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
    parser.add_argument("--prompt", default=None, help="det_vlm: custom base prompt (overrides default)")
    parser.add_argument("--prompt-file", default=None, help="det_vlm: read custom base prompt from a file")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime()))
