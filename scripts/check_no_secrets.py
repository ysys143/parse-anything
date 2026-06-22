from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TextIO


_SRC_ROOT: Final = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from odl_vl.secret_patterns import (  # noqa: E402
    KNOWN_SECRET_PREFIX_RE,
    SECRET_KEY_NAME_RE,
    URL_USERINFO_RE,
)


# Google/HF/sk- keys are covered by the shared KNOWN_SECRET_PREFIX_RE; only the
# scanner-specific hex-run heuristic lives here.
_HEX_TOKEN_RE: Final = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])")
_SECRET_ASSIGNMENT_RE: Final = re.compile(
    r"^\s*(?:export\s+)?['\"]?[A-Za-z0-9_.-]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|"
    r"AUTHORIZATION|SIGNATURE)[A-Za-z0-9_.-]*['\"]?\s*[:=]\s*['\"]?([^'\"\s#]+)",
    re.IGNORECASE,
)
# Exact placeholder tokens and template forms that are always safe.
_SAFE_EXACT_RE: Final = re.compile(
    r"(?i)^(?:<[^>]+>|\$\{[^}]+\}|present|absent|none|null|true|false|optional|placeholder)$"
)
# A placeholder marker counts only as a delimited word, never as an embedded
# substring (so "testsecretabc123..." or "realKeyOverride123..." are NOT safe).
_SAFE_PLACEHOLDER_RE: Final = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:placeholder|example|fake|dummy|sample|changeme|redacted|your|xxxx+)(?:[^a-z0-9]|$)"
)
# A credential-shaped value is a contiguous token without code punctuation; this
# excludes code expressions like `self.x.y` or `func(args` that share a secret-ish
# key name, while still matching real opaque keys/tokens (incl. under lowercase keys).
_CREDENTIAL_VALUE_RE: Final = re.compile(r"^[A-Za-z0-9_\-+/=:~]{20,}$")
_SKIPPED_SUFFIXES: Final = frozenset({".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip"})
_SKIPPED_DIRS: Final = frozenset({".git", "__pycache__", ".pytest_cache"})


@dataclass(frozen=True, slots=True)
class Finding:
    path: Path
    line_number: int
    kind: str

    def render(self) -> str:
        return f"{self.path}:{self.line_number}: {self.kind}"


@dataclass(frozen=True, slots=True)
class ScanReport:
    findings: tuple[Finding, ...]

    @property
    def has_findings(self) -> bool:
        return bool(self.findings)


def scan_paths(paths: Sequence[str | Path]) -> ScanReport:
    findings: list[Finding] = []
    for file_path in _iter_files(paths):
        findings.extend(_scan_file(file_path))
    return ScanReport(findings=tuple(findings))


def main(argv: Sequence[str] | None = None, stdout: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(description="Scan supplied paths for accidentally committed secret-like values")
    parser.add_argument("paths", nargs="+", help="Files or directories to scan")
    args = parser.parse_args(argv)
    report = scan_paths([Path(path) for path in args.paths])
    if report.has_findings:
        print("secret scan failed", file=stdout)
        for finding in report.findings:
            print(finding.render(), file=stdout)
        return 1
    print("secret scan passed", file=stdout)
    return 0


def _iter_files(paths: Sequence[str | Path]) -> Iterable[Path]:
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        if path.is_file():
            if _should_scan(path):
                yield path
            continue
        if path.is_dir():
            # Prune skipped directories during the walk so we never stat/sort the
            # contents of .git/__pycache__/.pytest_cache.
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if d not in _SKIPPED_DIRS)
                for name in sorted(files):
                    nested = Path(root) / name
                    if _should_scan(nested):
                        yield nested


def _should_scan(path: Path) -> bool:
    if path.suffix.lower() in _SKIPPED_SUFFIXES:
        return False
    return not any(part in _SKIPPED_DIRS for part in path.parts)


def _scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    # Decode latin-1 (every byte maps to a char) so a non-UTF-8 file is still scanned
    # for secret patterns rather than silently skipped.
    contents = path.read_bytes().decode("latin-1")
    for line_number, line in enumerate(contents.splitlines(), start=1):
        findings.extend(_scan_line(path, line_number, line))
    return findings


def _scan_line(path: Path, line_number: int, line: str) -> list[Finding]:
    findings: list[Finding] = []
    checks = (
        ("known_secret_prefix", KNOWN_SECRET_PREFIX_RE),
        ("url_credentials", URL_USERINFO_RE),
    )
    for kind, pattern in checks:
        if pattern.search(line):
            findings.append(Finding(path=path, line_number=line_number, kind=kind))
    # Bare hex runs are only treated as secrets in a secret-ish context, so git
    # SHAs / SHA-256 checksums / hex UUIDs in prose are not false-flagged.
    if _HEX_TOKEN_RE.search(line) and SECRET_KEY_NAME_RE.search(line):
        findings.append(Finding(path=path, line_number=line_number, kind="hex_token"))
    if _has_secret_assignment(line):
        findings.append(Finding(path=path, line_number=line_number, kind="secret_assignment"))
    return findings


def _has_secret_assignment(line: str) -> bool:
    match = _SECRET_ASSIGNMENT_RE.search(line)
    if match is None:
        return False
    value = match.group(1).strip().rstrip(",")
    # Only a credential-shaped value (no code punctuation) counts, so that a
    # secret-ish key name assigned a code expression is not a false positive.
    if _CREDENTIAL_VALUE_RE.fullmatch(value) is None:
        return False
    return not _is_safe_value(value)


def _is_safe_value(value: str) -> bool:
    if _SAFE_EXACT_RE.fullmatch(value) is not None:
        return True
    # A known credential prefix (AIza/hf_/sk-) is never whitelisted.
    if KNOWN_SECRET_PREFIX_RE.search(value):
        return False
    # A delimited placeholder word (fake/example/dummy/...) marks a placeholder even
    # when the value is long; real secrets do not embed such delimited words.
    return _SAFE_PLACEHOLDER_RE.search(value) is not None


if __name__ == "__main__":
    raise SystemExit(main())
