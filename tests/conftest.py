"""Shared test fixtures.

Tests never hit real APIs: fake env vars satisfy config validation, and each
test mocks the network/model boundary it touches. The only exception is the
opt-in live injection test in test_verdict.py, gated on TRUTHLAYER_LIVE_LLM=1.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from truthlayer.config import get_settings

_LIVE = os.environ.get("TRUTHLAYER_LIVE_LLM") == "1"


@pytest.fixture(autouse=True)
def fake_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide fake credentials and a fresh settings cache for every test.

    When TRUTHLAYER_LIVE_LLM=1, real env vars are left in place so the
    opt-in live test can reach the Anthropic API.
    """
    if not _LIVE:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://test:test@localhost:5432/test",  # pragma: allowlist secret
        )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
