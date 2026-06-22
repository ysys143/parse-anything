from __future__ import annotations

import re
from typing import Final


# Shared secret-shape definitions used by the ledger redactor and the pre-commit
# scanner. The scanner keeps a couple of stricter, scanner-specific patterns (hex
# runs) on top of these; these definitions cover the credential shapes both agree on.

# Any opaque 32+ char token (including purely-alphabetic ones).
LONG_TOKEN_RE: Final = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_-])")

# Known provider credential prefixes, caught regardless of length.
KNOWN_SECRET_PREFIX_RE: Final = re.compile(
    r"(?<![A-Za-z0-9_])(?:AIza[A-Za-z0-9_-]{10,}|hf_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9_-]{10,})"
)

# Single vocabulary of secret-bearing key-name fragments, shared by the ledger
# key-dropper and the pre-commit scanner's assignment detector.
SECRET_KEY_NAME_PATTERN: Final = r"api[_-]?key|token|secret|signature|authorization|credential|password"

# Secret-bearing key names (matched against mapping keys / assignment names).
SECRET_KEY_NAME_RE: Final = re.compile(rf"({SECRET_KEY_NAME_PATTERN})", re.IGNORECASE)

# Single source for the signing/auth query-parameter names, shared by both the
# "is this a signed URL" detector and the value redactor so they cannot diverge.
_SIGNED_URL_PARAM_NAMES: Final = (
    r"x-amz-signature|x-goog-signature|x-goog-credential|signature|sig|sas|"
    r"token|access[_-]?token|credential|auth"
)

# Query parameters that mark a URL as a signed/pre-authenticated URL.
SIGNED_URL_QUERY_RE: Final = re.compile(rf"({_SIGNED_URL_PARAM_NAMES})=", re.IGNORECASE)

# Credentials embedded in a URL authority (the user:pass that precedes the @ host).
URL_USERINFO_RE: Final = re.compile(r"([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s:@]+@", re.IGNORECASE)

# A signing/auth query parameter together with its value, e.g. "X-Goog-Signature=abc".
SIGNED_URL_PARAM_VALUE_RE: Final = re.compile(rf"(?i)\b({_SIGNED_URL_PARAM_NAMES})=([^&\s\"']+)")


def _redact_urls(value: str) -> str:
    value = URL_USERINFO_RE.sub(r"\1[REDACTED]@", value)
    return SIGNED_URL_PARAM_VALUE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def redact_secrets(value: str) -> str:
    """Redact secret shapes from any persisted string: opaque tokens, known prefixes, URLs.

    Security-first: applied uniformly to ledger fields, results.jsonl error/route_reason,
    and metadata so a credential can never survive into a shared artifact. This can
    over-redact a long non-secret identifier, which is the accepted trade-off for the
    "no secrets in outputs" guarantee.
    """
    value = LONG_TOKEN_RE.sub("[REDACTED]", value)
    value = KNOWN_SECRET_PREFIX_RE.sub("[REDACTED]", value)
    return _redact_urls(value)
