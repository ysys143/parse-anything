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

from odl_vl.cli_support import Runtime, safe_client  # noqa: E402
from odl_vl.config import load_settings  # noqa: E402
from odl_vl.pipeline.output import document_dir, write_outputs  # noqa: E402
from odl_vl.pipeline.run import run_document  # noqa: E402


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def run_cli(argv, runtime: Runtime, *, env_file: Path | None = None) -> int:
    args = _parse_args(argv)
    settings = load_settings(env_file=env_file or _REPO / ".env", environ=runtime.environ)
    key = settings.gemini_api_key
    out_root = args.out or (runtime.environ or {}).get("ODL_VL_OUT_DIR") or "out"

    # Reprocessing prevention: the document_id is a content hash, so an existing document.json with
    # the same hash means this exact input was already processed. Skip (no re-run) unless --force.
    if not args.force:
        from odl_vl.pipeline.docmeta import document_id

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

    profiles_dir = args.profiles_dir or (runtime.environ or {}).get("ODL_VL_PROFILE_DIR") or "profiles"
    mode = None
    if args.use_profile:
        # Reuse a stored diagnosis instead of re-running it.
        from odl_vl.pipeline.profile import load_profile

        profile = load_profile(args.source_id, profiles_dir)
        if profile is not None:
            mode = profile.recommended_mode
            print(f"profile: source={args.source_id} mode={mode} tier={profile.tier} (stored)", file=runtime.stdout)
    if mode is None and args.diagnose:
        # D-1 picks the mode by measurement, then the whole run uses it (no per-page routing).
        if not key:
            print("error: --diagnose requires GEMINI_API_KEY (D-1 runs the VLM on sampled pages)", file=runtime.stdout)
            return 2
        from odl_vl.pipeline.diagnose import diagnose_source
        from odl_vl.pipeline.profile import from_d1_diagnosis, load_profile, save_profile

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

    from odl_vl.pipeline.assemble import DetVlmOptions

    custom_prompt = args.prompt
    if args.prompt_file:
        custom_prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    options = DetVlmOptions(
        ground=not args.no_ground, spanning=not args.no_spanning,
        double_pass=not args.no_double_pass, arithmetic=not args.no_arithmetic, prompt=custom_prompt,
    )

    # R8.6 scan double-pass: PaddleOCR as the second provider (local-file upload) when configured.
    second_pass = None
    if mode == "det_vlm" and options.double_pass and settings.paddle_api_key and settings.paddle_base_url:
        from odl_vl.pipeline.paddle_vlm import make_transcriber

        second_pass = make_transcriber(
            safe_client(runtime), base_url=settings.paddle_base_url, token=settings.paddle_api_key,
            model=settings.paddle_model or "PaddleOCR-VL-1.6",
        )

    result = run_document(
        args.pdf, mode=mode, vlm_client=client, api_key=key or "",
        source_id=args.source_id, external_id=args.external_id, ingested_from=args.ingested_from,
        options=options, second_pass=second_pass,
    )
    # Per-document dir = <out_root>/<source_id>/<document_id> (out_root resolved above).
    out_dir = document_dir(out_root, result)
    write_outputs(result, out_dir, pdf_path=args.pdf, arithmetic=options.arithmetic)
    if args.review:
        from odl_vl.pipeline.review import write_review

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
    parser.add_argument("--out", default=None, help="output root; default $ODL_VL_OUT_DIR or ./out")
    parser.add_argument("--mode", choices=["deterministic", "det_vlm"], default="det_vlm",
                        help="deterministic (ODL+pypdfium2) or det_vlm (+VLM reconciled); default det_vlm")
    parser.add_argument("--no-vlm", action="store_true", help="alias for --mode deterministic")
    parser.add_argument("--diagnose", action="store_true", help="run D-1 diagnosis first, save a profile, and use the recommended mode")
    parser.add_argument("--use-profile", action="store_true", help="use a stored SourceProfile's mode (skip diagnosis) if one exists for --source-id")
    parser.add_argument("--profiles-dir", default=None, help="profile store; default $ODL_VL_PROFILE_DIR or ./profiles")
    parser.add_argument("--sample-size", type=int, default=4, help="pages D-1 samples when --diagnose (default 4)")
    parser.add_argument("--source-id", default="default", help="source (document stream) id; output groups by it")
    parser.add_argument("--external-id", default=None, help="caller-provided document id, preserved in metadata")
    parser.add_argument("--ingested-from", default=None, help="provenance origin (path/url); defaults to --pdf")
    parser.add_argument("--force", action="store_true", help="reprocess even if this content hash was already produced")
    parser.add_argument("--review", action="store_true", help="also write review.html (source vs extraction + flags)")
    # det_vlm behaviour opt-outs (all ON by default)
    parser.add_argument("--no-ground", action="store_true", help="det_vlm: skip ODL+pypdfium2 deterministic grounding")
    parser.add_argument("--no-spanning", action="store_true", help="det_vlm: skip page-spanning table reconstruction")
    parser.add_argument("--no-double-pass", action="store_true", help="det_vlm: skip dual-provider pass on scans")
    parser.add_argument("--no-arithmetic", action="store_true", help="det_vlm: skip arithmetic-invariant guard")
    parser.add_argument("--prompt", default=None, help="det_vlm: custom base prompt (overrides default)")
    parser.add_argument("--prompt-file", default=None, help="det_vlm: read custom base prompt from a file")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime()))
