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
                "secret_hex=" + ("c" * 32),  # hex only flagged in a secret-ish context
                "SERVICE_TOKEN=" + ("safe" * 8),
            ]
        ),
        encoding="utf-8",
    )

    # When
    report = module.scan_paths([sample])

    # Then
    assert report.has_findings is True
    # AIza/hf_ keys are reported via the shared known-prefix check (no separate
    # google/hf regexes); the hex value and the long token assignment are also flagged.
    assert {finding.kind for finding in report.findings} == {
        "known_secret_prefix",
        "hex_token",
        "secret_assignment",
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


def test_scanner_flags_lowercase_named_secret_assignment(tmp_path):
    # Given a lowercase-named key with a long opaque secret value.
    module = _load_secret_scan_module()
    sample = tmp_path / "conf.py"
    sample.write_text("my_password = " + repr("a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7"), encoding="utf-8")

    # When
    report = module.scan_paths([sample])

    # Then: a lowercase key is flagged just like the uppercase form would be.
    assert "secret_assignment" in {finding.kind for finding in report.findings}


def test_scanner_flags_url_embedded_credentials(tmp_path):
    # Given a base URL with embedded basic-auth credentials.
    module = _load_secret_scan_module()
    sample = tmp_path / "config.txt"
    sample.write_text("PADDLE_BASE_URL=https://user:" + "secretpw123" + "@host.example/api", encoding="utf-8")

    # When
    report = module.scan_paths([sample])

    # Then
    assert "url_credentials" in {finding.kind for finding in report.findings}


def test_scanner_does_not_flag_bare_git_sha_or_checksum(tmp_path):
    # Given hex hashes in prose with no secret-ish context on the line.
    module = _load_secret_scan_module()
    sample = tmp_path / "NOTES.md"
    sample.write_text(
        "\n".join(
            [
                "Pinned at commit " + ("a" * 40) + " for reproducibility.",
                "sha256 digest: " + ("b" * 64),
            ]
        ),
        encoding="utf-8",
    )

    # When
    report = module.scan_paths([sample])

    # Then: hashes in prose are not false-flagged as secrets.
    assert report.has_findings is False


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
