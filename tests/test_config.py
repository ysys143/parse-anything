from __future__ import annotations

import os

from odl_vl.config import load_settings


def test_load_settings_prefers_shell_values_over_env_file(tmp_path, monkeypatch):
    # Given
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "GEMINI_API_KEY=env-gemini-placeholder",
                "PADDLE_API_KEY=env-paddle-placeholder",
                "PADDLE_BASE_URL=https://env-placeholder.invalid",
                "PADDLE_MODEL=env-model-placeholder",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GEMINI_API_KEY", "shell-gemini-placeholder")
    monkeypatch.setenv("PADDLE_BASE_URL", "https://shell-placeholder.invalid")

    # When
    settings = load_settings(env_file=env_file)

    # Then
    assert settings.gemini_api_key == "shell-gemini-placeholder"
    assert settings.paddle_api_key == "env-paddle-placeholder"
    assert settings.paddle_base_url == "https://shell-placeholder.invalid"
    assert settings.paddle_model == "env-model-placeholder"


def test_load_settings_uses_paddleocr_aliases_only_as_fallback(tmp_path, monkeypatch):
    # Given
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "PADDLEOCR_API_KEY=alias-key-placeholder",
                "PADDLEOCR_BASE_URL=https://alias-placeholder.invalid",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PADDLE_API_KEY", "canonical-key-placeholder")

    # When
    settings = load_settings(env_file=env_file)

    # Then
    assert settings.paddle_api_key == "canonical-key-placeholder"
    assert settings.paddle_base_url == "https://alias-placeholder.invalid"


def test_load_settings_accepts_missing_optional_env_file(tmp_path, monkeypatch):
    # Given
    missing_env = tmp_path / "missing.env"
    for name in (
        "GEMINI_API_KEY",
        "PADDLE_API_KEY",
        "PADDLE_BASE_URL",
        "PADDLE_MODEL",
        "PADDLEOCR_API_KEY",
        "PADDLEOCR_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    # When
    settings = load_settings(env_file=missing_env)

    # Then
    assert settings.gemini_api_key is None
    assert settings.paddle_api_key is None
    assert settings.paddle_base_url is None
    assert settings.paddle_model is None
    assert settings.has_gemini is False
    assert settings.has_paddle is False


def test_settings_repr_does_not_reveal_secret_values(tmp_path):
    # Given
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "GEMINI_API_KEY=secret-gemini-placeholder",
                "PADDLE_API_KEY=secret-paddle-placeholder",
                "PADDLE_BASE_URL=https://safe-placeholder.invalid",
            ]
        ),
        encoding="utf-8",
    )

    # When
    rendered = repr(load_settings(env_file=env_file, environ={}))

    # Then
    assert "secret-gemini-placeholder" not in rendered
    assert "secret-paddle-placeholder" not in rendered
    assert "has_gemini=True" in rendered
    assert "has_paddle=True" in rendered


def test_load_settings_does_not_mutate_process_environment(tmp_path, monkeypatch):
    # Given
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=env-gemini-placeholder\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # When
    settings = load_settings(env_file=env_file)

    # Then
    assert settings.gemini_api_key == "env-gemini-placeholder"
    assert "GEMINI_API_KEY" not in os.environ


def test_load_settings_strips_unquoted_inline_comment(tmp_path):
    # Given a .env value with a trailing inline comment.
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=abc123placeholder # prod key\n", encoding="utf-8")

    # When
    settings = load_settings(env_file=env_file, environ={})

    # Then: the comment is not folded into the key value.
    assert settings.gemini_api_key == "abc123placeholder"


def test_load_settings_keeps_hash_inside_quoted_value(tmp_path):
    # Given a quoted value that legitimately contains a '#'.
    env_file = tmp_path / ".env"
    env_file.write_text('GEMINI_API_KEY="abc#123placeholder"\n', encoding="utf-8")

    # When
    settings = load_settings(env_file=env_file, environ={})

    # Then
    assert settings.gemini_api_key == "abc#123placeholder"


def test_empty_process_env_does_not_mask_valid_env_file_value(tmp_path):
    # Given a valid key in .env and an empty same-name var in the process env.
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=valid-gemini-placeholder\n", encoding="utf-8")

    # When
    settings = load_settings(env_file=env_file, environ={"GEMINI_API_KEY": ""})

    # Then: the empty env var is skipped, so the .env value survives.
    assert settings.gemini_api_key == "valid-gemini-placeholder"


def test_load_settings_strips_unbalanced_leading_quote(tmp_path):
    # Given a value with an opening quote but no closing quote (a common typo).
    env_file = tmp_path / ".env"
    env_file.write_text('GEMINI_API_KEY="abc123placeholder\n', encoding="utf-8")

    # When
    settings = load_settings(env_file=env_file, environ={})

    # Then: the stray leading quote is dropped, not folded into the value.
    assert settings.gemini_api_key == "abc123placeholder"


def test_load_settings_keeps_unquoted_value_starting_with_hash(tmp_path):
    # Given an unquoted value that legitimately starts with '#' (not a comment).
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=#abc123placeholder\n", encoding="utf-8")

    # When
    settings = load_settings(env_file=env_file, environ={})

    # Then: a leading '#' is part of the value, not an inline comment.
    assert settings.gemini_api_key == "#abc123placeholder"
