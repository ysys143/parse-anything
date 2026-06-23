from __future__ import annotations

import re
from typing import Final


# Secret-shape definitions used by the pre-commit scanner (scripts/check_no_secrets.py).
# These are detection patterns for a commit-time gate -- they are NOT applied as a
# runtime scrubbing pass over orchestrator output. Keeping secrets out of artifacts is
# a source responsibility (opaque error codes, non-secret metadata) plus a .gitignore on
# the run-artifact files; the scanner is the backstop that fails a commit if one slips in.

# Known provider credential prefixes / shapes, caught regardless of length. The JWT form
# is included because its '.'-separated segments are each under a typical opaque-token
# length and would otherwise slip through a length-based heuristic.
KNOWN_SECRET_PREFIX_RE: Final = re.compile(
    r"(?<![A-Za-z0-9_])(?:AIza[A-Za-z0-9_-]{10,}|hf_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9_-]{10,}|"
    r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,})"
)

# Single vocabulary of secret-bearing key-name fragments, shared by the scanner's
# assignment detector (e.g. API_KEY=..., token: ...).
SECRET_KEY_NAME_PATTERN: Final = r"api[_-]?key|token|secret|signature|authorization|credential|password"

# Secret-bearing key names (matched against assignment names).
SECRET_KEY_NAME_RE: Final = re.compile(rf"({SECRET_KEY_NAME_PATTERN})", re.IGNORECASE)

# Credentials embedded in a URL authority (the user:pass that precedes the @ host).
URL_USERINFO_RE: Final = re.compile(r"([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s:@]+@", re.IGNORECASE)
