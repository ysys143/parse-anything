from __future__ import annotations

import re
from typing import Final


# Single source of truth shared by the ledger redactor and the pre-commit secret
# scanner so the two never disagree on what counts as secret-like.

# Any opaque 32+ char token (including purely-alphabetic ones).
LONG_TOKEN_RE: Final = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_-])")

# Known provider credential prefixes, caught regardless of length.
KNOWN_SECRET_PREFIX_RE: Final = re.compile(
    r"(?<![A-Za-z0-9_])(?:AIza[A-Za-z0-9_-]{10,}|hf_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9_-]{10,})"
)

# Secret-bearing key names (matched against mapping keys / assignment names).
SECRET_KEY_NAME_RE: Final = re.compile(
    r"(api[_-]?key|token|secret|signature|authorization|credential|password)", re.IGNORECASE
)

# Query parameters that mark a URL as a signed/pre-authenticated URL.
SIGNED_URL_QUERY_RE: Final = re.compile(
    r"(x-amz-signature|signature|token|expires|x-goog-signature)", re.IGNORECASE
)


def redact_secrets(value: str) -> str:
    """Replace long opaque tokens and known credential prefixes with [REDACTED]."""
    value = LONG_TOKEN_RE.sub("[REDACTED]", value)
    return KNOWN_SECRET_PREFIX_RE.sub("[REDACTED]", value)
