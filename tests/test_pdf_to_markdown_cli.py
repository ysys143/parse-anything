from __future__ import annotations

import io
import json

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _load_cli():
    import parse_anything.cli as cli   # the packaged CLI (the `parse-anything` console entry point)
    return cli


def _text_pdf(path) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, "Quarterly notes -- plain prose page one.")
    c.showPage()
    c.drawString(72, 720, "Page two prose content here.")
    c.showPage()
    c.save()
    return str(path)


def test_cli_offline_writes_markdown_and_ledger(tmp_path):
    cli = _load_cli()
    pdf = _text_pdf(tmp_path / "doc.pdf")
    out = tmp_path / "out"
    output = io.StringIO()
    runtime = cli.Runtime(environ={}, stdout=output)

    code = cli.run_cli(["--pdf", pdf, "--out", str(out), "--no-vlm"], runtime)

    assert code == 0
    docdirs = list((out / "default").glob("*"))   # <out>/<source_id>/<document_id>/
    assert len(docdirs) == 1
    docdir = docdirs[0]
    assert (docdir / "document.md").read_text(encoding="utf-8").strip() != ""
    assert (docdir / "pages" / "page-000.md").exists()
    assert (docdir / "document.json").exists()      # rich output written
    ledger = [json.loads(line) for line in (docdir / "ledger.jsonl").read_text().splitlines()]
    assert len(ledger) == 2
    assert all(r["used_vlm"] is False for r in ledger)  # --no-vlm
    summary = output.getvalue()
    assert "pages=2" in summary and "mode=deterministic" in summary


def test_cli_skips_already_processed_unless_forced(tmp_path):
    cli = _load_cli()
    pdf = _text_pdf(tmp_path / "doc.pdf")
    out = tmp_path / "out"
    args = ["--pdf", pdf, "--out", str(out), "--no-vlm", "--source-id", "s"]

    output1 = io.StringIO()
    r1 = cli.Runtime(environ={}, stdout=output1)
    assert cli.run_cli(args, r1, env_file=tmp_path / "absent.env") == 0  # first run processes
    assert "mode=deterministic" in output1.getvalue()

    output2 = io.StringIO()
    r2 = cli.Runtime(environ={}, stdout=output2)
    assert cli.run_cli(args, r2, env_file=tmp_path / "absent.env") == 0  # same input -> skipped
    assert "skipped:" in output2.getvalue()

    output3 = io.StringIO()
    r3 = cli.Runtime(environ={}, stdout=output3)
    assert cli.run_cli([*args, "--force"], r3, env_file=tmp_path / "absent.env") == 0  # --force reprocesses
    out3 = output3.getvalue()
    assert "skipped:" not in out3 and "mode=deterministic" in out3


def test_cli_use_profile_skips_diagnosis(tmp_path):
    from parse_anything.pipeline.profile import SourceProfile, save_profile

    cli = _load_cli()
    pdf = _text_pdf(tmp_path / "doc.pdf")
    save_profile(SourceProfile("csnl", "deterministic", 0.8, "D-2", ("r",), {}, {}, None), tmp_path / "profiles")
    output = io.StringIO()
    runtime = cli.Runtime(environ={}, stdout=output)
    code = cli.run_cli(
        ["--pdf", pdf, "--out", str(tmp_path / "o"), "--source-id", "csnl", "--use-profile", "--profiles-dir", str(tmp_path / "profiles")],
        runtime, env_file=tmp_path / "absent.env",
    )
    assert code == 0
    summary = output.getvalue()
    assert "profile: source=csnl mode=deterministic" in summary and "(stored)" in summary
    assert "mode=deterministic" in summary  # the run used the stored mode


def test_cli_diagnose_requires_api_key(tmp_path):
    cli = _load_cli()
    pdf = _text_pdf(tmp_path / "doc.pdf")
    output = io.StringIO()
    runtime = cli.Runtime(environ={}, stdout=output)  # no GEMINI_API_KEY
    code = cli.run_cli(["--pdf", pdf, "--out", str(tmp_path / "o"), "--diagnose"], runtime, env_file=tmp_path / "absent.env")
    assert code == 2 and "--diagnose requires GEMINI_API_KEY" in output.getvalue()


def test_cli_wires_paddle_transcriber_as_special_ocr(tmp_path, monkeypatch):
    from parse_anything.pipeline.docmeta import DocumentMeta
    from parse_anything.pipeline.odl_extract import OdlDocument, OdlPage
    from parse_anything.pipeline.run import DocumentResult, PageOutcome

    cli = _load_cli()
    pdf = _text_pdf(tmp_path / "doc.pdf")
    def sentinel(image: bytes) -> str:
        return "ocr text"
    captured = {}

    def fake_make_transcriber(client, *, base_url, token, model):
        assert base_url == "https://paddle.example.invalid"
        assert token == "fake-paddle-secret"
        assert model == "PaddleOCR-VL-1.6-test"
        return sentinel

    def fake_run_document(*args, **kwargs):
        meta = DocumentMeta("idcliocr1234567", "idcliocr1234567ff", "doc.pdf", n_pages=1, mode="deterministic")
        page = PageOutcome(0, "deterministic", False, "body", 0.0, ())
        return DocumentResult((page,), structure=OdlDocument(1, (OdlPage(0, "body", (), ()),)), meta=meta)

    def fake_write_outputs(result, out_dir, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("parse_anything.pipeline.paddle_vlm.make_transcriber", fake_make_transcriber)
    monkeypatch.setattr(cli, "run_document", fake_run_document)
    monkeypatch.setattr(cli, "write_outputs", fake_write_outputs)
    runtime = cli.Runtime(
        environ={
            "PADDLE_API_KEY": "fake-paddle-secret",
            "PADDLE_BASE_URL": "https://paddle.example.invalid",
            "PADDLE_MODEL": "PaddleOCR-VL-1.6-test",
        },
        stdout=io.StringIO(),
    )

    code = cli.run_cli(["--pdf", pdf, "--out", str(tmp_path / "out"), "--no-vlm"], runtime,
                       env_file=tmp_path / "absent.env")

    assert code == 0
    assert captured["special_ocr"] is sentinel
