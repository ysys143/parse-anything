from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def find_first_string(value: Any, keys: frozenset[str], *, strip: bool = False) -> str | None:
    """Return the first string found under any of ``keys`` in a nested JSON value.

    Walks mappings (depth-first) and lists. This is the single shared
    implementation used by the library normalizers and both CLIs so that job-id,
    status, and text extraction never diverge.
    """
    if isinstance(value, Mapping):
        for item_key, nested in value.items():
            if item_key in keys and isinstance(nested, str):
                return nested.strip() if strip else nested
            found = find_first_string(nested, keys, strip=strip)
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        for nested in value:
            found = find_first_string(nested, keys, strip=strip)
            if found is not None:
                return found
    return None
