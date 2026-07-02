from __future__ import annotations

import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, TextIO

from parse_anything.providers import ProviderHttpClient, SafeTransport, Transport, UrllibTransport


class Sleeper(Protocol):
    def __call__(self, seconds: float) -> None: ...


@dataclass(frozen=True, slots=True)
class Runtime:
    """Injectable I/O seams shared by the CLI entry points (testable in-process)."""

    environ: Mapping[str, str] | None = None
    transport: Transport = field(default_factory=UrllibTransport)
    stdout: TextIO = sys.stdout
    sleep: Sleeper = time.sleep


def safe_client(runtime: Runtime) -> ProviderHttpClient:
    """Build a client whose HTTP/URL errors surface as status codes, not exceptions."""
    return ProviderHttpClient(SafeTransport(runtime.transport))
