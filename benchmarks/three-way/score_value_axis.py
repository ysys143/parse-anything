#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

UPSTREAM_SOURCE_KINDS = frozenset(
    {
        "author_markup",
        "csv",
        "filer_xbrl",
        "html",
        "jats",
        "publisher_xml",
        "sec_xbrl",
        "upstream_xbrl",
        "xbrl",
    }
)

_NUMBER_RE = re.compile(r"(?<!\w)[-+]?\$?\(?\d[\d,]*(?:\.\d+)?\)?(?!\w)")


@dataclass(frozen=True)
class Fact:
    doc: str
    name: str
    value: Decimal
    source_kind: str
    unit: str | None = None


def _require_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"fact field {key!r} must be a non-empty string")
    return value.strip()


def _optional_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"fact field {key!r} must be a non-empty string when present")
    return value.strip()


def normalize_number(value: str) -> Decimal:
    clean = value.strip().replace(",", "").replace("$", "")
    is_parenthesized = clean.startswith("(") and clean.endswith(")")
    if is_parenthesized:
        clean = clean[1:-1]
    if clean.startswith("+"):
        clean = clean[1:]
    try:
        number = Decimal(clean)
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric fact value {value!r}") from exc
    return -number if is_parenthesized else number


def _format_number(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(value.quantize(Decimal(1)))
    return format(value.normalize(), "f")


def extract_numbers(text: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for match in _NUMBER_RE.finditer(text):
        try:
            found.add(normalize_number(match.group(0)))
        except ValueError:
            continue
    return found


def _parse_fact(payload: Mapping[str, object], *, line_number: int) -> Fact:
    source_kind = _require_string(payload, "source_kind")
    if source_kind not in UPSTREAM_SOURCE_KINDS:
        allowed = ", ".join(sorted(UPSTREAM_SOURCE_KINDS))
        raise ValueError(
            f"line {line_number}: source_kind={source_kind!r} is not non-circular upstream GT; "
            f"use one of: {allowed}"
        )
    return Fact(
        doc=_require_string(payload, "doc"),
        name=_require_string(payload, "name"),
        value=normalize_number(_require_string(payload, "value")),
        unit=_optional_string(payload, "unit"),
        source_kind=source_kind,
    )


def load_facts(path: Path) -> list[Fact]:
    facts: list[Fact] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"line {line_number}: fact must be a JSON object")
        facts.append(_parse_fact(payload, line_number=line_number))
    if not facts:
        raise ValueError(f"{path} contains no facts")
    return facts


def _load_pages(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(page, str) for page in payload):
        raise ValueError(f"{path} must contain a JSON list of page strings")
    return payload


def _iter_outputs(run_dir: Path) -> Iterable[tuple[str, str, list[str]]]:
    for pages_file in sorted(run_dir.glob("*/*/pages.json")):
        parser = pages_file.parent.parent.name
        doc = pages_file.parent.name
        yield parser, doc, _load_pages(pages_file)


def _score_pages(pages: Sequence[str], facts: Sequence[Fact]) -> dict[str, object]:
    output_numbers = extract_numbers("\n".join(pages))
    expected_numbers = {fact.value for fact in facts}
    hits = [fact for fact in facts if fact.value in output_numbers]
    unsourced = sorted(output_numbers - expected_numbers)
    return {
        "axis": "value",
        "structure_axis_scored": False,
        "fact_total": len(facts),
        "fact_hits": len(hits),
        "numeric_exact_recall": round(len(hits) / len(facts), 3) if facts else 1.0,
        "output_numeric_total": len(output_numbers),
        "unsourced_number_total": len(unsourced),
        "unsourced_number_rate": round(len(unsourced) / len(output_numbers), 3)
        if output_numbers
        else 0.0,
        "unsourced_numbers": [_format_number(number) for number in unsourced],
        "matched_facts": [fact.name for fact in hits],
        "gt_source_kinds": sorted({fact.source_kind for fact in facts}),
    }


def score_run(run_dir: Path, facts: Sequence[Fact]) -> dict[str, object]:
    facts_by_doc: dict[str, list[Fact]] = defaultdict(list)
    for fact in facts:
        facts_by_doc[fact.doc].append(fact)

    scores: dict[str, object] = {}
    for parser, doc, pages in _iter_outputs(run_dir):
        doc_facts = facts_by_doc.get(doc)
        if not doc_facts:
            continue
        scores[f"{parser}/{doc}"] = _score_pages(pages, doc_facts)

    return {
        "axis_contract": {
            "value_axis": "numeric exact recall and unsourced-number rate against upstream facts",
            "structure_axis": "not scored here; use table/region labels or OmniDocBench-style structure metrics",
            "non_circular_gt": sorted(UPSTREAM_SOURCE_KINDS),
        },
        "scores": scores,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path, help="results/<run> tree from run_compare.py")
    parser.add_argument(
        "--facts",
        required=True,
        type=Path,
        help="JSONL facts from upstream GT such as SEC XBRL, author CSV, or publisher XML",
    )
    parser.add_argument("--out", required=True, type=Path, help="output JSON path")
    args = parser.parse_args(argv)

    payload = score_run(args.run_dir, load_facts(args.facts))
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
