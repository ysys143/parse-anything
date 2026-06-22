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
