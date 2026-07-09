"""Shared test fixtures.

Tests never hit real APIs by default: fake env vars satisfy config
validation, and each test mocks the network/model boundary it touches. Two
opt-in live exceptions, each independently gated so one doesn't require the
other's credentials:
- TRUTHLAYER_LIVE_LLM=1 — the injection test in test_verdict.py (real Claude).
- TRUTHLAYER_LIVE_EMBEDDINGS=1 — the cache threshold probes in test_cache.py
  (real OpenAI embeddings — these validate the semantic-cache similarity
  threshold against the actual production embedding model, so a mocked
  embedding would defeat their entire purpose).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from truthlayer.config import get_settings

_LIVE_LLM = os.environ.get("TRUTHLAYER_LIVE_LLM") == "1"
_LIVE_EMBEDDINGS = os.environ.get("TRUTHLAYER_LIVE_EMBEDDINGS") == "1"


@pytest.fixture(autouse=True)
def fake_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide fake credentials and a fresh settings cache for every test.

    Real ANTHROPIC_API_KEY / OPENAI_API_KEY are left in place only when their
    respective live flag is set, so each opt-in live test can reach its real
    API without requiring the other's credentials too.
    """
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://test:test@localhost:5432/test",  # pragma: allowlist secret
    )
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    if not _LIVE_LLM:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    if not _LIVE_EMBEDDINGS:
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
