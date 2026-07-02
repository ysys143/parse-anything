"""D-2 diagnostic bundle CLI (processing-tiers §2.5).

Assembles the review material a flagship coding agent (the oracle position) examines by hand to
write a SourceProfile for a hard source: sample page images + per-sample deterministic text,
structure, and (when a key is available) the D-1 VLM divergence. This does NOT decide the mode
-- it only gathers what the agent looks at. See docs/diagnostic-d2.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from parse_anything.cli_support import Runtime, safe_client  # noqa: E402
from parse_anything.config import load_settings  # noqa: E402
from parse_anything.pipeline.diagnose import prepare_bundle  # noqa: E402


def run_cli(argv, runtime: Runtime, *, env_file: Path | None = None) -> int:
    args = _parse_args(argv)
    settings = load_settings(env_file=env_file or _REPO / ".env", environ=runtime.environ)
    key = settings.gemini_api_key
    client = safe_client(runtime) if (key and not args.no_vlm) else None
    bundle = prepare_bundle(args.pdf, args.out, sample_size=args.sample_size, vlm_client=client, api_key=key or "")
    print(
        f"bundle written: {args.out} ({bundle['n_sampled']} samples, vlm_material={'yes' if client else 'no'}) "
        f"-- review per docs/diagnostic-d2.md and write a SourceProfile",
        file=runtime.stdout,
    )
    return 0


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="D-2 diagnostic bundle: assemble sample review material")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--out", required=True, help="bundle output directory")
    parser.add_argument("--sample-size", type=int, default=4)
    parser.add_argument("--no-vlm", action="store_true", help="skip VLM material (images + deterministic text only)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime()))
