from __future__ import annotations

import importlib.util
import json
import sys
import tomllib
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_BENCH = ROOT / "benchmarks" / "semantic-captioning"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fetcher_rejects_source_url_html_drift() -> None:
    fetch = _load_module("semantic_captioning_fetch", SEMANTIC_BENCH / "fetch.py")

    try:
        fetch._validate_download(b"<!doctype html><html><body>moved</body></html>", "sample.pdf")
    except ValueError as exc:
        assert "unexpected html response" in str(exc)
    else:
        raise AssertionError("HTML drift was accepted as a downloadable corpus artifact")


def test_t4_data_hygiene_labels_exist() -> None:
    expected = {"policy_diagram.json", "handwriting_ko.json"}
    present = {p.name for p in (SEMANTIC_BENCH / "gt").glob("*.json")}
    assert expected <= present


def test_pytest_default_collection_excludes_auxiliary_worktrees() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_config = config["tool"]["pytest"]["ini_options"]
    assert pytest_config["testpaths"] == ["tests"]
    assert "worktree-*" in pytest_config["norecursedirs"]


def test_adapt_surfaces_text_blocks_for_entity_recall() -> None:
    run_bench = _load_module("semantic_captioning_run_bench", SEMANTIC_BENCH / "run_bench.py")
    sys.path.insert(0, str(SEMANTIC_BENCH))
    try:
        score = _load_module("semantic_captioning_score", SEMANTIC_BENCH / "score.py")
    finally:
        sys.path.pop(0)

    output = run_bench._adapt(
        {
            "blocks": [
                {
                    "page": 8,
                    "kind": "text",
                    "bbox": [10, 20, 30, 40],
                    "text": "Transformer (big) reaches 41.8 BLEU; GNMT + RL Ensemble is listed.",
                }
            ],
            "tables": [],
            "figures": [],
        }
    )

    assert output["structured"]["text_blocks"] == [
        {
            "page": 8,
            "kind": "text",
            "text": "Transformer (big) reaches 41.8 BLEU; GNMT + RL Ensemble is listed.",
        }
    ]
    assert ("C_entity", "PASS", "ok") in score.score_one(
        {
            "risk_checks": {
                "C_entity": {
                    "verbatim": ["Transformer (big)", "41.8", "GNMT + RL Ensemble"]
                }
            }
        },
        output,
    )


def _two_page_pdf(path: Path) -> None:
    frames = [Image.new("RGB", (80, 60), color) for color in ("white", "gray")]
    frames[0].save(path, "PDF", save_all=True, append_images=frames[1:])


def test_run_one_slices_deterministic_pdf_to_labelled_page(monkeypatch, tmp_path) -> None:
    run_bench = _load_module("semantic_captioning_run_bench_slice", SEMANTIC_BENCH / "run_bench.py")
    import parse_anything.cli as cli

    sample = tmp_path / "two-page.pdf"
    _two_page_pdf(sample)
    captured_pdf: list[Path] = []
    captured_pages: list[int] = []

    def fake_run_cli(argv, runtime, *, env_file):
        pdf_arg = Path(argv[argv.index("--pdf") + 1])
        out_arg = Path(argv[argv.index("--out") + 1])
        source_id = argv[argv.index("--source-id") + 1]
        captured_pdf.append(pdf_arg)
        pdf_doc = pdfium.PdfDocument(str(pdf_arg))
        try:
            captured_pages.append(len(pdf_doc))
        finally:
            pdf_doc.close()
        doc_dir = out_arg / source_id / "doc"
        doc_dir.mkdir(parents=True)
        (doc_dir / "document.json").write_text(
            json.dumps({"blocks": [], "tables": [], "figures": []}),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(cli, "run_cli", fake_run_cli)

    run_bench._run_one(sample, "sample", "deterministic", tmp_path, page=2)

    assert captured_pdf[0].name == "page.pdf"
    assert captured_pages == [1]


def test_run_one_can_keep_whole_doc_for_diagnostics(monkeypatch, tmp_path) -> None:
    run_bench = _load_module("semantic_captioning_run_bench_whole", SEMANTIC_BENCH / "run_bench.py")
    import parse_anything.cli as cli

    sample = tmp_path / "two-page.pdf"
    _two_page_pdf(sample)
    captured: dict[str, Path] = {}

    def fake_run_cli(argv, runtime, *, env_file):
        pdf_arg = Path(argv[argv.index("--pdf") + 1])
        out_arg = Path(argv[argv.index("--out") + 1])
        source_id = argv[argv.index("--source-id") + 1]
        captured["pdf"] = pdf_arg
        doc_dir = out_arg / source_id / "doc"
        doc_dir.mkdir(parents=True)
        (doc_dir / "document.json").write_text(
            json.dumps({"blocks": [], "tables": [], "figures": []}),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(cli, "run_cli", fake_run_cli)

    run_bench._run_one(sample, "sample", "deterministic", tmp_path, page=2, slice_pages=False)

    assert captured["pdf"] == sample


def test_scorer_requires_units_to_be_attached_to_values() -> None:
    score = _load_module("semantic_captioning_score_units", SEMANTIC_BENCH / "score.py")
    label = {"risk_checks": {"A_unit": {"expected_unit": ["일", "개월"]}}}

    separated = {"caption": "", "structured": {"tokens": ["15 30 45 3", "일 개월"]}}
    attached = {"caption": "", "structured": {"tokens": ["15일", "30일", "45일", "3개월"]}}

    assert score.check_A_unit(label, separated)[1] == "FAIL"
    assert score.check_A_unit(label, attached)[1] == "PASS"


def test_scorer_arithmetic_accepts_explicit_checks() -> None:
    score = _load_module("semantic_captioning_score_arithmetic", SEMANTIC_BENCH / "score.py")
    label = {"risk_checks": {"B_arithmetic": {"relation": "parts sum to total"}}}

    passed = {"structured": {"arithmetic_checks": [{"parts": [13, 50.5, 51], "total": 114.5, "tolerance": 0.5}]}}
    failed = {"structured": {"arithmetic_checks": [{"parts": [13, 50.5, 40], "total": 114.5, "tolerance": 0.5}]}}

    assert score.check_B_arithmetic(label, passed)[1] == "PASS"
    assert score.check_B_arithmetic(label, failed)[1] == "FAIL"


def test_scorer_grounding_uses_iou_when_gt_has_bboxes() -> None:
    score = _load_module("semantic_captioning_score_grounding", SEMANTIC_BENCH / "score.py")
    label = {"elements_expected": [{"kind": "diagram", "bbox": [0, 0, 10, 10]}]}

    far = {"elements": [{"kind": "diagram", "bbox": [100, 100, 110, 110]}]}
    overlap = {"elements": [{"kind": "diagram", "bbox": [1, 1, 9, 9]}]}

    assert score.check_G_grounding(label, far)[1] == "FAIL"
    assert score.check_G_grounding(label, overlap)[1] == "PASS"
