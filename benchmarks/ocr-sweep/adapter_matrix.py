#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NotRequired, TypeAlias, TypedDict, assert_never


JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class RegistryModel(TypedDict):
    id: str
    backend: NotRequired[str]
    pipeline: NotRequired[str]


class TotalsRow(TypedDict):
    models: int
    stable: int
    blocked: int
    leaking: int


class MetricCounts(TypedDict):
    done_pages: int
    failed_pages: int
    empty_pages: int


class DocRow(TypedDict):
    doc: str
    fresh_output: bool
    parse_ok: bool
    raw_done_pages: int
    raw_failed_pages: int
    raw_empty_pages: int
    document_paths: list[str]
    leak_tokens: list[str]
    summary_status: str


class ModelRow(TypedDict):
    model: str
    backend: str
    pipeline: str
    stable: bool
    status: str
    blockers: list[str]
    docs: list[DocRow]


class Matrix(TypedDict):
    results: str
    models_file: str
    leak_tokens: list[str]
    totals: TotalsRow
    models: list[ModelRow]


LEAK_TOKENS: Final = (
    "<x_",
    "<y_",
    "<class_",
    "<|ref|>",
    "<|det|>",
    "<div",
    "data-bbox",
    "is_diagram:",
    "<header",
    "<footer",
)
DOC_TAGS: Final = ("born", "scan")


def sanitize(model_id: str) -> str:
    return "".join(char if char.isalnum() or char in "-._" else "_" for char in model_id)


def build_matrix(results: Path, models_file: Path) -> Matrix:
    registry = _load_registry(models_file)
    summary_rows = _read_jsonl(results / "summary.jsonl")
    rows = [_model_row(results, model, summary_rows) for model in registry]
    return {
        "results": str(results),
        "models_file": str(models_file),
        "leak_tokens": list(LEAK_TOKENS),
        "totals": {
            "models": len(rows),
            "stable": sum(1 for row in rows if row["stable"] is True),
            "blocked": sum(1 for row in rows if row["status"] not in ("pass", "leak")),
            "leaking": sum(1 for row in rows if row["status"] == "leak"),
        },
        "models": rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build adapter_matrix.json for ocr-sweep results")
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--models-file", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--fail-on-leak", action="store_true")
    args = parser.parse_args(argv)

    matrix = build_matrix(args.results, args.models_file)
    out = args.out or args.results / "adapter_matrix.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[adapter-matrix] wrote {out}")

    has_leaks = any(row["status"] == "leak" for row in matrix["models"])
    if args.fail_on_leak and has_leaks:
        return 1
    return 0


def _load_registry(models_file: Path) -> list[RegistryModel]:
    payload: JsonValue = json.loads(models_file.read_text(encoding="utf-8"))
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise SystemExit(f"models file has no models list: {models_file}")
    registry: list[RegistryModel] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str):
            continue
        model: RegistryModel = {"id": model_id}
        backend = item.get("backend")
        if isinstance(backend, str):
            model["backend"] = backend
        pipeline = item.get("pipeline")
        if isinstance(pipeline, str):
            model["pipeline"] = pipeline
        registry.append(model)
    return registry


def _model_row(results: Path, model: RegistryModel, summary_rows: list[JsonObject]) -> ModelRow:
    model_id = model["id"]
    model_dir = results / sanitize(model_id)
    model_summary = [row for row in summary_rows if row.get("model") == model_id]
    docs = [_doc_row(model_dir, tag, model_summary) for tag in DOC_TAGS]
    blockers = _blockers(model_summary, docs)
    leaked = any(doc["leak_tokens"] for doc in docs)
    stable = bool(docs) and any(doc["fresh_output"] for doc in docs) and not blockers and not leaked
    return {
        "model": model_id,
        "backend": model.get("backend", "unknown"),
        "pipeline": model.get("pipeline", "per_page"),
        "stable": stable,
        "status": _status(stable, leaked, blockers),
        "blockers": blockers,
        "docs": docs,
    }


def _doc_row(model_dir: Path, tag: str, summary_rows: list[JsonObject]) -> DocRow:
    metrics = _metric_counts(_read_jsonl(model_dir / f"metrics_{tag}.jsonl"))
    documents = _document_paths(model_dir, tag)
    leaks = _leak_tokens(documents)
    summary = next((row for row in summary_rows if row.get("doc") == tag), None)
    parse_ok = summary is not None and summary.get("ok") is True and bool(documents)
    return {
        "doc": tag,
        "fresh_output": metrics["done_pages"] > 0,
        "parse_ok": parse_ok,
        "raw_done_pages": metrics["done_pages"],
        "raw_failed_pages": metrics["failed_pages"],
        "raw_empty_pages": metrics["empty_pages"],
        "document_paths": [str(path) for path in documents],
        "leak_tokens": leaks,
        "summary_status": _summary_status(summary),
    }


def _read_jsonl(path: Path) -> list[JsonObject]:
    if not path.exists():
        return []
    rows: list[JsonObject] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _metric_counts(rows: list[JsonObject]) -> MetricCounts:
    page_rows = [row for row in rows if row.get("seq") != 0]
    done = [row for row in page_rows if row.get("state") == "done"]
    failed = [row for row in page_rows if row.get("state") != "done"]
    empty = [row for row in done if _coerce_int(row.get("chars")) == 0]
    return {"done_pages": len(done), "failed_pages": len(failed), "empty_pages": len(empty)}


def _coerce_int(value: JsonValue) -> int:
    match value:
        case bool() | None | list() | dict():
            return 0
        case int() as number:
            return number
        case float() as number:
            return int(number)
        case str() as text:
            try:
                return int(text)
            except ValueError:
                return 0
        case unreachable:
            assert_never(unreachable)


def _document_paths(model_dir: Path, tag: str) -> list[Path]:
    out_dir = model_dir / f"out_{tag}"
    if not out_dir.exists():
        return []
    return sorted(out_dir.glob("*/*/document.md")) + sorted(out_dir.glob("*/*/document.json"))


def _leak_tokens(paths: list[Path]) -> list[str]:
    seen: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for token in LEAK_TOKENS:
            if token.lower() in text and token not in seen:
                seen.append(token)
    return seen


def _blockers(summary_rows: list[JsonObject], docs: list[DocRow]) -> list[str]:
    explicit: list[str] = []
    for row in summary_rows:
        status = row.get("status")
        if isinstance(status, str):
            explicit.append(status)
    if explicit:
        return explicit
    blockers: list[str] = []
    for doc in docs:
        if doc["fresh_output"] is True and doc["parse_ok"] is not True:
            blockers.append(f"{doc['doc']}:parse_missing")
        if doc["raw_failed_pages"] > 0:
            blockers.append(f"{doc['doc']}:raw_failed_pages")
        if doc["raw_empty_pages"] > 0:
            blockers.append(f"{doc['doc']}:raw_empty_pages")
    if not any(doc["fresh_output"] for doc in docs):
        blockers.append("no_fresh_output")
    return blockers


def _status(stable: bool, leaked: bool, blockers: list[str]) -> str:
    if stable:
        return "pass"
    if leaked:
        return "leak"
    if blockers:
        return blockers[0]
    return "no_evidence"


def _summary_status(row: JsonObject | None) -> str:
    if row is not None and row.get("ok") is True:
        return "ok"
    status = row.get("status") if row is not None else None
    return status if isinstance(status, str) else "missing"


if __name__ == "__main__":
    raise SystemExit(main())
