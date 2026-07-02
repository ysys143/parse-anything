"""Derived SQLite catalog CLI: build an index over the document.json store, or query it.

The filesystem stays the source of truth; this index is rebuildable. Examples:
  python scripts/index_catalog.py --out out/ --db catalog.db                 # (re)build
  python scripts/index_catalog.py --db catalog.db --query --source-id csnl   # query
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

from parse_anything.cli_support import Runtime  # noqa: E402
from parse_anything.pipeline.catalog import build_index, query  # noqa: E402


def run_cli(argv, runtime: Runtime) -> int:
    args = _parse_args(argv)
    if args.query:
        rows = query(args.db, source_id=args.source_id, external_id=args.external_id, flagged_only=args.flagged)
        print(json.dumps(rows, ensure_ascii=False, indent=2), file=runtime.stdout)
        return 0
    if not args.out:
        print("error: provide --out <root> to build, or --query to read", file=runtime.stdout)
        return 2
    n = build_index(args.out, args.db)
    print(f"indexed {n} documents -> {args.db}", file=runtime.stdout)
    return 0


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="Derived SQLite catalog over the document.json store")
    parser.add_argument("--db", required=True, help="sqlite db path")
    parser.add_argument("--out", default=None, help="output root to (re)build the index from")
    parser.add_argument("--query", action="store_true", help="query mode")
    parser.add_argument("--source-id", default=None)
    parser.add_argument("--external-id", default=None)
    parser.add_argument("--flagged", action="store_true", help="only documents with >0 flags")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:], Runtime()))
