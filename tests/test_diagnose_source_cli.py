from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_source.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("diagnose_source", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["diagnose_source"] = module
    spec.loader.exec_module(module)
    return module


def _pdf(path) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, "page")
    c.showPage()
    c.save()
    return str(path)


def test_diagnose_cli_requires_api_key(tmp_path):
    cli = _load_cli()
    runtime = cli.Runtime(environ={}, stdout=io.StringIO())  # no GEMINI_API_KEY
    code = cli.run_cli(["--pdf", _pdf(tmp_path / "d.pdf")], runtime, env_file=tmp_path / "absent.env")
    assert code == 2 and "GEMINI_API_KEY required" in runtime.stdout.getvalue()
