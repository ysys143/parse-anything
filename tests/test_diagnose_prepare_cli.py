from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_prepare.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("diagnose_prepare", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["diagnose_prepare"] = module
    spec.loader.exec_module(module)
    return module


def _pdf(path) -> str:
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, "born-digital prose for the diagnostic bundle")
    c.showPage()
    c.save()
    return str(path)


def test_prepare_cli_writes_bundle_offline(tmp_path):
    cli = _load_cli()
    out = tmp_path / "bundle"
    runtime = cli.Runtime(environ={}, stdout=io.StringIO())
    code = cli.run_cli(["--pdf", _pdf(tmp_path / "d.pdf"), "--out", str(out), "--no-vlm"], runtime, env_file=tmp_path / "absent.env")
    assert code == 0
    assert (out / "bundle.json").exists() and (out / "pages" / "page-000.png").exists()
    assert "vlm_material=no" in runtime.stdout.getvalue()
