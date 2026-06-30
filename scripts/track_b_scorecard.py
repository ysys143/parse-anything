"""Track B variant scorecard (oracle-based, no labeled golden set).

For born-digital PDFs the pypdfium2 text layer is the value ground truth (F8), so we can measure
each variant's output Markdown WITHOUT hand-labeled answers:

- number_recall: fraction of the PDF's oracle numbers that appear in the output Markdown
- table_preserved: does the output contain a Markdown table (structure survived)?
- chars: output length (rough completeness signal)

Output format differs per variant (ODL json vs document.json), so we score the Markdown, which is
the common comparable surface. Usage:

    python3 scripts/track_b_scorecard.py <pdf> <label>=<out_dir/doc.md> [<label>=<md> ...]

Each md path is a variant's rendered Markdown. Prints a comparison table.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "src")

from odl_vl.pipeline.deterministic import number_tokens  # noqa: E402
from odl_vl.pipeline.render import page_count  # noqa: E402

_NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?")
_MD_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)


def _norm(s: str) -> str:
    return s.replace(",", "")


def oracle_numbers(pdf_path: str, *, min_value: float | None = None) -> set[str]:
    """All normalized numeric tokens from the PDF text layer (the value oracle)."""
    nums: set[str] = set()
    for i in range(page_count(pdf_path)):
        for tok in number_tokens(pdf_path, i, min_value=min_value):
            nums.add(tok.value)
    return nums


def emitted_numbers(markdown: str) -> set[str]:
    return {_norm(m.group(0)) for m in _NUM_RE.finditer(markdown)}


def score(oracle: set[str], markdown: str) -> dict[str, object]:
    """Recall + precision of output numbers vs the oracle/golden set.

    recall = golden numbers found in output (coverage); precision = output numbers that are in
    golden (1 - fabrication/OCR-error rate). On born-digital recall is the value oracle (F8); on
    scans recall+precision against a golden set catch both missed and hallucinated digits.
    """
    emitted = emitted_numbers(markdown)
    hit = oracle & emitted
    recall = len(hit) / len(oracle) if oracle else 1.0
    precision = len(hit) / len(emitted) if emitted else 1.0
    return {
        "recall": round(recall, 3),
        "precision": round(precision, 3),
        "hit": len(hit),
        "golden": len(oracle),
        "fabricated": len(emitted - oracle),
        "table": bool(_MD_TABLE_RE.search(markdown)),
        "chars": len(markdown),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    # Optional --golden <file>: use a golden number list instead of the PDF text-layer oracle
    # (required for scans, which have no text layer).
    golden_file = None
    if argv[0] == "--golden":
        golden_file = argv[1]
        argv = argv[2:]
    pdf_path = argv[0]
    if golden_file:
        with open(golden_file, encoding="utf-8") as fh:
            oracle = {_norm(line.strip()) for line in fh if line.strip()}
    else:
        oracle = oracle_numbers(pdf_path)

    variants = []
    for arg in argv[1:]:
        label, _, md_path = arg.partition("=")
        try:
            with open(md_path, encoding="utf-8") as fh:
                markdown = fh.read()
        except OSError as exc:
            print(f"  [skip] {label}: {type(exc).__name__}")
            continue
        variants.append((label, score(oracle, markdown)))

    if not variants:
        print("no readable variant outputs")
        return 1

    cols = ["recall", "precision", "hit", "golden", "fabricated", "table", "chars"]
    width = max(len(label) for label, _ in variants)
    header = "variant".ljust(width) + "  " + "  ".join(c.rjust(15) for c in cols)
    print(header)
    print("-" * len(header))
    for label, sc in variants:
        row = label.ljust(width) + "  " + "  ".join(str(sc[c]).rjust(15) for c in cols)
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
