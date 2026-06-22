from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def find_first_string(value: Any, keys: frozenset[str], *, strip: bool = False) -> str | None:
    """First string under any of ``keys`` in a nested JSON value, shallowest match first.

    Matches at the current mapping level are preferred over deeper ones, so an
    authoritative top-level key (e.g. ``status``) is not shadowed by a nested
    sibling of the same name.
    """

    def accept(item: Any) -> str | None:
        if isinstance(item, str):
            return item.strip() if strip else item
        return None

    return _find_first(value, keys, accept)


def find_first_scalar(value: Any, keys: frozenset[str]) -> str | None:
    """Like :func:`find_first_string` but also accepts numeric values, returned as text.

    Used for fields a provider may encode as a JSON number (e.g. a numeric job id).
    """

    def accept(item: Any) -> str | None:
        if isinstance(item, bool):
            return None
        if isinstance(item, str):
            return item.strip()
        if isinstance(item, (int, float)):
            return str(item)
        return None

    return _find_first(value, keys, accept)


def _find_first(value: Any, keys: frozenset[str], accept: Callable[[Any], str | None]) -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():  # current level first (shallowest match wins)
            if key in keys:
                got = accept(nested)
                if got is not None:
                    return got
        for nested in value.values():  # then recurse into children
            got = _find_first(nested, keys, accept)
            if got is not None:
                return got
        return None
    if isinstance(value, list):
        for nested in value:
            got = _find_first(nested, keys, accept)
            if got is not None:
                return got
    return None
