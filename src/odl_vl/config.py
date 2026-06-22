from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


_PADDLE_API_KEY_ALIAS = "PADDLEOCR_API_KEY"
_PADDLE_BASE_URL_ALIAS = "PADDLEOCR_BASE_URL"


@dataclass(frozen=True, slots=True)
class Settings:
    gemini_api_key: str | None = field(default=None, repr=False)
    paddle_api_key: str | None = field(default=None, repr=False)
    paddle_base_url: str | None = field(default=None, repr=False)
    paddle_model: str | None = None

    @property
    def has_gemini(self) -> bool:
        return self.gemini_api_key is not None

    @property
    def has_paddle(self) -> bool:
        return self.paddle_api_key is not None and self.paddle_base_url is not None

    def __repr__(self) -> str:
        return (
            "Settings("
            f"has_gemini={self.has_gemini}, "
            f"has_paddle={self.has_paddle}, "
            f"paddle_model={self.paddle_model!r}"
            ")"
        )


def load_settings(
    env_file: str | Path | None = ".env",
    environ: Mapping[str, str] | None = None,
) -> Settings:
    env_values = _load_env_file(env_file)
    env_values.update(dict(os.environ if environ is None else environ))

    return Settings(
        gemini_api_key=_non_empty(env_values.get("GEMINI_API_KEY")),
        paddle_api_key=_first_present(env_values, "PADDLE_API_KEY", _PADDLE_API_KEY_ALIAS),
        paddle_base_url=_first_present(env_values, "PADDLE_BASE_URL", _PADDLE_BASE_URL_ALIAS),
        paddle_model=_non_empty(env_values.get("PADDLE_MODEL")),
    )


def _load_env_file(env_file: str | Path | None) -> dict[str, str]:
    if env_file is None:
        return {}

    path = Path(env_file)
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is not None:
            key, value = parsed
            values[key] = value
    return values


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").lstrip()

    key, separator, value = stripped.partition("=")
    if separator == "" or key.strip() == "":
        return None

    value = value.strip()
    if value[:1] in {"'", '"'}:
        # Quoted value: keep as-is so a '#' inside the quotes is preserved.
        return key.strip(), _strip_quotes(value)
    return key.strip(), _strip_inline_comment(value)


def _strip_inline_comment(value: str) -> str:
    # Drop an unquoted trailing comment introduced by whitespace + '#'. A leading
    # '#' (index 0) is part of the value, not a comment, so it is preserved.
    for index, char in enumerate(value):
        if char == "#" and index > 0 and value[index - 1].isspace():
            return value[:index].rstrip()
    return value


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _first_present(values: Mapping[str, str], canonical: str, alias: str) -> str | None:
    canonical_value = _non_empty(values.get(canonical))
    if canonical_value is not None:
        return canonical_value
    return _non_empty(values.get(alias))


def _non_empty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    return stripped
