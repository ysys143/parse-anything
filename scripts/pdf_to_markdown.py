"""PDF -> Markdown pipeline CLI (target contract: docs/pdf-pipeline-requirements.md).

Renders pages, triages processing depth, runs deterministic extraction or VLM per page
(batching page-spanning tables), applies the born-digital value oracle gate, and writes
per-page Markdown + document.md + ledger.jsonl + results.jsonl.

VLM is used only when a GEMINI_API_KEY is configured and --no-vlm is not passed; otherwise
pages route deterministically and VLM-needed pages degrade to the text layer with a flag.
"""
from __future__ import annotations

import argparse
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


def run_cli(argv, runtime: Runtime) -> int:
    args = _parse_args(argv)
    settings = load_settings(env_file=_REPO / ".env", environ=runtime.environ)
    key = settings.gemini_api_key
    mode = "deterministic" if args.no_vlm else args.mode  # configured mode, no runtime routing
    use_vlm = (mode == "det_vlm") and key is not None
    client = safe_client(runtime) if use_vlm else None

    result = run_document(
        args.pdf, mode=mode, vlm_client=client, api_key=key or "",
        source_id=args.source_id, external_id=args.external_id, ingested_from=args.ingested_from,
    )
    # Output root: --out > $ODL_VL_OUT_DIR > ./out. Per-document dir = <root>/<source_id>/<document_id>.
    out_root = args.out or (runtime.environ or {}).get("ODL_VL_OUT_DIR") or "out"
    out_dir = document_dir(out_root, result)
    write_outputs(result, out_dir, pdf_path=args.pdf)
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
    parser.add_argument("--source-id", default="default", help="source (document stream) id; output groups by it")
    parser.add_argument("--external-id", default=None, help="caller-provided document id, preserved in metadata")
    parser.add_argument("--ingested-from", default=None, help="provenance origin (path/url); defaults to --pdf")
    parser.add_argument("--review", action="store_true", help="also write review.html (source vs extraction + flags)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime()))
