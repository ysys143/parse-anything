from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TextIO


_GOOGLE_API_KEY_RE: Final = re.compile(r"(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])")
_HF_TOKEN_RE: Final = re.compile(r"(?<![A-Za-z0-9_-])hf_[A-Za-z0-9]{20,}(?![A-Za-z0-9_-])")
_HEX_TOKEN_RE: Final = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])")
_SECRET_ASSIGNMENT_RE: Final = re.compile(
    r"^\s*(?:export\s+)?['\"]?[A-Z0-9_.-]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|"
    r"AUTHORIZATION|SIGNATURE)[A-Z0-9_.-]*['\"]?\s*[:=]\s*['\"]?([^'\"\s#]+)"
)
_SAFE_VALUE_RE: Final = re.compile(
    r"(?i)^(?:<[^>]+>|\$\{[^}]+\}|present|absent|none|null|true|false|optional|placeholder|"
    r".*placeholder.*|.*example.*|.*fake.*|.*override.*|.*dummy.*|.*test.*)$"
)
_MIN_SECRET_ASSIGNMENT_LENGTH: Final = 20
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
            for nested in sorted(path.rglob("*")):
                if nested.is_file() and _should_scan(nested):
                    yield nested


def _should_scan(path: Path) -> bool:
    if path.suffix.lower() in _SKIPPED_SUFFIXES:
        return False
    return not any(part in _SKIPPED_DIRS for part in path.parts)


def _scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        contents = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return findings
    for line_number, line in enumerate(contents.splitlines(), start=1):
        findings.extend(_scan_line(path, line_number, line))
    return findings


def _scan_line(path: Path, line_number: int, line: str) -> list[Finding]:
    findings: list[Finding] = []
    checks = (
        ("google_api_key", _GOOGLE_API_KEY_RE),
        ("hf_token", _HF_TOKEN_RE),
        ("hex_token", _HEX_TOKEN_RE),
    )
    for kind, pattern in checks:
        if pattern.search(line):
            findings.append(Finding(path=path, line_number=line_number, kind=kind))
    if _has_secret_assignment(line):
        findings.append(Finding(path=path, line_number=line_number, kind="secret_assignment"))
    return findings


def _has_secret_assignment(line: str) -> bool:
    match = _SECRET_ASSIGNMENT_RE.search(line)
    if match is None:
        return False
    value = match.group(1).strip().rstrip(",")
    if len(value) < _MIN_SECRET_ASSIGNMENT_LENGTH:
        return False
    return _SAFE_VALUE_RE.fullmatch(value) is None


if __name__ == "__main__":
    raise SystemExit(main())
