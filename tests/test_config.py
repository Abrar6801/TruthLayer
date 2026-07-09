"""Tests for config loading and fail-fast validation."""

from __future__ import annotations

import pytest

from truthlayer.config import ConfigError, get_settings


def test_settings_load_from_env() -> None:
    settings = get_settings()
    assert settings.anthropic_api_key == "test-anthropic-key"  # pragma: allowlist secret
    assert settings.embedding_model_name == "text-embedding-3-small"
    assert settings.embedding_dim == 384


def test_missing_vars_all_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    # Keep load_dotenv from re-supplying the deleted vars from a local .env.
    monkeypatch.setattr("truthlayer.config.load_dotenv", lambda: None)
    get_settings.cache_clear()

    with pytest.raises(ConfigError) as excinfo:
        get_settings()
    message = str(excinfo.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "TAVILY_API_KEY" in message


def test_tunable_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_TOP_K", "3")
    monkeypatch.setenv("SIMILARITY_THRESHOLD", "0.5")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.retrieval_top_k == 3
    assert settings.similarity_threshold == 0.5
