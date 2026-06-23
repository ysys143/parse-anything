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
from odl_vl.pipeline.output import write_outputs  # noqa: E402
from odl_vl.pipeline.run import run_document  # noqa: E402


def run_cli(argv, runtime: Runtime) -> int:
    args = _parse_args(argv)
    settings = load_settings(env_file=_REPO / ".env", environ=runtime.environ)
    key = settings.gemini_api_key
    use_vlm = (not args.no_vlm) and key is not None
    client = safe_client(runtime) if use_vlm else None

    result = run_document(args.pdf, vlm_client=client, api_key=key or "")
    write_outputs(result, args.out)

    n = len(result.pages)
    vlm_pages = sum(1 for p in result.pages if p.used_vlm)
    flagged = sum(1 for p in result.pages if p.flags and p.route != "folded")
    print(
        f"pages={n} vlm_pages={vlm_pages} flagged={flagged} vlm_enabled={use_vlm} out={args.out}",
        file=runtime.stdout,
    )
    return 0


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="PDF -> Markdown pipeline")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-vlm", action="store_true", help="deterministic only (skip VLM/OCR)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime()))
