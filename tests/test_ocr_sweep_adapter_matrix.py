from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_adapter_matrix():
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "ocr-sweep" / "adapter_matrix.py"
    spec = importlib.util.spec_from_file_location("ocr_sweep_adapter_matrix", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load adapter_matrix.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _fake_models_file(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "models": [
                    {"id": "model/success", "backend": "vllm_docker", "pipeline": "per_page"},
                    {"id": "model/blocked", "backend": "custom_docker", "pipeline": "whole_doc"},
                ]
            }
        ),
        encoding="utf-8",
    )


def test_build_matrix_marks_fresh_clean_outputs_stable(tmp_path):
    module = _load_adapter_matrix()
    models_file = tmp_path / "models.json"
    _fake_models_file(models_file)
    results = tmp_path / "results"
    out_dir = results / "model_success" / "out_born" / "model_success" / "doc123"
    out_dir.mkdir(parents=True)
    (out_dir / "document.md").write_text("# Clean\n\nbody", encoding="utf-8")
    (out_dir / "document.json").write_text(json.dumps({"markdown": "body"}), encoding="utf-8")
    _write_jsonl(results / "summary.jsonl", [
        {"model": "model/success", "doc": "born", "ok": True},
        {"model": "model/blocked", "status": "runner_timeout"},
    ])
    _write_jsonl(results / "model_success" / "metrics_born.jsonl", [
        {"model": "model/success", "seq": 1, "state": "done", "chars": 12},
        {"model": "model/success", "seq": 0, "batched_wall_s": 1.2},
    ])

    matrix = module.build_matrix(results, models_file)

    rows = {row["model"]: row for row in matrix["models"]}
    assert rows["model/success"]["stable"] is True
    assert rows["model/success"]["status"] == "pass"
    assert rows["model/success"]["docs"][0]["fresh_output"] is True
    assert rows["model/success"]["docs"][0]["leak_tokens"] == []
    assert rows["model/blocked"]["stable"] is False
    assert rows["model/blocked"]["status"] == "runner_timeout"


def test_main_fails_when_final_artifact_leaks_provider_markup(tmp_path):
    module = _load_adapter_matrix()
    models_file = tmp_path / "models.json"
    _fake_models_file(models_file)
    results = tmp_path / "results"
    out_dir = results / "model_success" / "out_scan" / "model_success" / "doc123"
    out_dir.mkdir(parents=True)
    (out_dir / "document.md").write_text('<div data-bbox="1 2 3 4">leak</div>', encoding="utf-8")
    _write_jsonl(results / "summary.jsonl", [{"model": "model/success", "doc": "scan", "ok": True}])
    _write_jsonl(results / "model_success" / "metrics_scan.jsonl", [
        {"model": "model/success", "seq": 1, "state": "done", "chars": 12},
    ])

    matrix_path = results / "adapter_matrix.json"
    code = module.main([
        "--results",
        str(results),
        "--models-file",
        str(models_file),
        "--out",
        str(matrix_path),
        "--fail-on-leak",
    ])

    assert code == 1
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    row = next(row for row in matrix["models"] if row["model"] == "model/success")
    doc = next(doc for doc in row["docs"] if doc["doc"] == "scan")
    assert row["stable"] is False
    assert doc["leak_tokens"] == ["<div", "data-bbox"]
