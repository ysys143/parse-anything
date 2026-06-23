"""D-1 source diagnostic CLI (processing-tiers §2.5).

Samples a few pages, measures how far a VLM diverges from the deterministic text layer and
whether the source is scanned / structurally complex, and prints a recommended execution mode
(deterministic vs det_vlm) with evidence. Run once per source to choose a mode; the run itself
is then predictable. Requires a GEMINI_API_KEY (the diagnosis runs the VLM on the samples).
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
from odl_vl.pipeline.diagnose import diagnose_source  # noqa: E402


def run_cli(argv, runtime: Runtime, *, env_file: Path | None = None) -> int:
    args = _parse_args(argv)
    settings = load_settings(env_file=env_file or _REPO / ".env", environ=runtime.environ)
    key = settings.gemini_api_key
    if not key:
        print("error: GEMINI_API_KEY required for D-1 diagnosis (it runs the VLM on sampled pages)", file=runtime.stdout)
        return 2
    diag = diagnose_source(args.pdf, vlm_client=safe_client(runtime), api_key=key, sample_size=args.sample_size)
    print(json.dumps(diag.to_dict(), ensure_ascii=False, indent=2), file=runtime.stdout)
    return 0


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="D-1 source diagnostic: recommend deterministic vs det_vlm")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--sample-size", type=int, default=4, help="number of pages to sample (default 4)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime()))
