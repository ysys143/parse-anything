from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "benchmarks" / "three-way" / "score_value_axis.py"


def _load_score_value_axis():
    spec = importlib.util.spec_from_file_location("score_value_axis", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["score_value_axis"] = module
    spec.loader.exec_module(module)
    return module


def _write_pages(run_dir: Path, parser: str, doc: str, pages: list[str]) -> None:
    doc_dir = run_dir / parser / doc
    doc_dir.mkdir(parents=True)
    (doc_dir / "pages.json").write_text(json.dumps(pages), encoding="utf-8")
    (doc_dir / "meta.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")


def test_value_axis_rejects_pdf_derived_ground_truth(tmp_path):
    mod = _load_score_value_axis()
    facts = tmp_path / "facts.jsonl"
    facts.write_text(
        json.dumps(
            {
                "doc": "sec_10q",
                "name": "us-gaap:Revenue",
                "value": "125000",
                "source_kind": "pdf_extractor",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        mod.load_facts(facts)
    except ValueError as exc:
        assert "non-circular" in str(exc)
    else:
        raise AssertionError("pdf-derived fact source must be rejected")


def test_value_axis_scores_upstream_facts_without_structure_claim(tmp_path):
    mod = _load_score_value_axis()
    run_dir = tmp_path / "run"
    _write_pages(run_dir, "pa", "sec_10q", ["Revenue was $125,000. Net income was 10,500. Extra 999."])
    _write_pages(run_dir, "paddle", "sec_10q", ["Revenue was 125000. Net income was omitted."])

    facts = tmp_path / "facts.jsonl"
    facts.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "doc": "sec_10q",
                        "name": "us-gaap:Revenue",
                        "value": "125000",
                        "unit": "USD",
                        "source_kind": "xbrl",
                    }
                ),
                json.dumps(
                    {
                        "doc": "sec_10q",
                        "name": "us-gaap:NetIncomeLoss",
                        "value": "10500",
                        "unit": "USD",
                        "source_kind": "xbrl",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = mod.score_run(run_dir, mod.load_facts(facts))

    pa = payload["scores"]["pa/sec_10q"]
    assert pa["axis"] == "value"
    assert pa["structure_axis_scored"] is False
    assert pa["fact_total"] == 2
    assert pa["fact_hits"] == 2
    assert pa["numeric_exact_recall"] == 1.0
    assert pa["unsourced_number_total"] == 1
    assert pa["unsourced_numbers"] == ["999"]

    paddle = payload["scores"]["paddle/sec_10q"]
    assert paddle["fact_hits"] == 1
    assert paddle["numeric_exact_recall"] == 0.5


def test_value_axis_cli_writes_payload(tmp_path):
    mod = _load_score_value_axis()
    run_dir = tmp_path / "run"
    _write_pages(run_dir, "pa", "sec_10q", ["Revenue was 125000."])
    facts = tmp_path / "facts.jsonl"
    facts.write_text(
        json.dumps(
            {
                "doc": "sec_10q",
                "name": "us-gaap:Revenue",
                "value": "125000",
                "source_kind": "sec_xbrl",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "scores.json"

    assert mod.main(["--run-dir", str(run_dir), "--facts", str(facts), "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["scores"]["pa/sec_10q"]["numeric_exact_recall"] == 1.0
