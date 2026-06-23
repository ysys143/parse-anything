from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pdf_to_markdown.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("pdf_to_markdown", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pdf_to_markdown"] = module
    spec.loader.exec_module(module)
    return module


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
    runtime = cli.Runtime(environ={}, stdout=io.StringIO())

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
    summary = runtime.stdout.getvalue()
    assert "pages=2" in summary and "mode=deterministic" in summary
