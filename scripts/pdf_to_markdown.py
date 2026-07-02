"""Legacy script path -> the packaged CLI (`parse_anything.cli`).

Prefer the `parse-anything` console command (installed via `[project.scripts]`). This shim keeps the
`python scripts/pdf_to_markdown.py ...` invocation working from a source checkout without an install.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from parse_anything.cli import main, run_cli  # noqa: E402,F401  (run_cli re-exported for legacy callers/tests)

if __name__ == "__main__":
    raise SystemExit(main())
