from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_no_secrets.py"


def _load_secret_scan_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_no_secrets", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_no_secrets"] = module
    spec.loader.exec_module(module)
    return module


def test_scanner_reports_google_hf_hex_and_secret_assignments(tmp_path):
    # Given
    module = _load_secret_scan_module()
    sample = tmp_path / "sample.txt"
    sample.write_text(
        "\n".join(
            [
                "google=" + "AI" + "za" + ("A" * 35),
                "hf=" + "hf" + "_" + ("Z" * 37),
                "hex=" + ("c" * 32),
                "SERVICE_TOKEN=" + ("safe" * 8),
            ]
        ),
        encoding="utf-8",
    )

    # When
    report = module.scan_paths([sample])

    # Then
    assert report.has_findings is True
    assert {finding.kind for finding in report.findings} == {
        "google_api_key",
        "hf_token",
        "hex_token",
        "secret_assignment",
        "known_secret_prefix",  # AIza/hf_ also match the shared known-prefix check
    }
    rendered = "\n".join(finding.render() for finding in report.findings)
    assert "AIza" not in rendered
    assert "Z" * 37 not in rendered
    assert "safe" * 8 not in rendered


def test_scanner_flags_real_secret_that_merely_contains_a_placeholder_word(tmp_path):
    # Given real-looking secrets whose value embeds 'test'/'override' as a substring.
    module = _load_secret_scan_module()
    sample = tmp_path / "sample.env"
    # Values are assembled at runtime so this source file is not itself flagged.
    sample.write_text(
        "\n".join(
            [
                "TEST_API_KEY=" + "test" + "secretabc123def456ghi789xyz",
                "ACCESS_TOKEN=" + "realKey" + "Override1234567890abcd",
            ]
        ),
        encoding="utf-8",
    )

    # When
    report = module.scan_paths([sample])

    # Then: the embedded placeholder substring must NOT whitelist a real secret.
    assert report.has_findings is True
    assert "secret_assignment" in {finding.kind for finding in report.findings}


def test_scanner_ignores_placeholders_and_missing_paths(tmp_path):
    # Given
    module = _load_secret_scan_module()
    docs = tmp_path / "docs"
    docs.mkdir()
    clean_file = docs / "README.md"
    clean_file.write_text(
        "\n".join(
            [
                "GEMINI_API_KEY=<gemini api key>",
                "PADDLE_API_KEY=<paddle official api key>",
                "PADDLE_MODEL=<optional paddle model override>",
                "status=present",
            ]
        ),
        encoding="utf-8",
    )

    # When
    report = module.scan_paths([docs, tmp_path / "missing"])

    # Then
    assert report.has_findings is False
    assert report.findings == ()


def test_cli_returns_nonzero_without_printing_secret_material(tmp_path, capsys):
    # Given
    module = _load_secret_scan_module()
    sample = tmp_path / "sample.env"
    sample.write_text("ACCESS_SECRET=" + ("z" * 24), encoding="utf-8")

    # When
    exit_code = module.main([str(sample)])

    # Then
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "secret_assignment" in output
    assert "z" * 24 not in output
