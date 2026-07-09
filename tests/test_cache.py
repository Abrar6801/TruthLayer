"""Tests for the semantic verdict cache.

Two groups: logic tests (DB and embedding call mocked) and opt-in threshold
probes that use the REAL production embedding model (OpenAI) to verify the
configured cutoff (settings.cache_similarity_threshold) separates dangerous
near-misses (negations, entity swaps) from legitimate paraphrase hits.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

import pytest

import truthlayer.cache as cache_module
from truthlayer.cache import check_cache, store_verdict
from truthlayer.config import get_settings

# ---------------------------------------------------------------------------
# Logic tests (mocked)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _FakeConnection:
    def __init__(self, store: _FakeDB) -> None:
        self._store = store

    def execute(self, sql: str, params: Any = None) -> _FakeResult:
        self._store.executed.append((sql, params))
        return _FakeResult(self._store.hit_row)


class _FakeDB:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.hit_row: tuple[Any, ...] | None = None

    @contextmanager
    def connection(self) -> Any:
        yield _FakeConnection(self)


@pytest.fixture()
def fake_db(monkeypatch: pytest.MonkeyPatch) -> _FakeDB:
    db = _FakeDB()
    monkeypatch.setattr(cache_module, "get_pool", lambda: db)
    monkeypatch.setattr(cache_module, "embed_text", lambda text: [0.1, 0.2])
    return db


def test_cache_miss_returns_none(fake_db: _FakeDB) -> None:
    assert check_cache("some claim") is None


def test_cache_hit_returns_payload(fake_db: _FakeDB) -> None:
    payload = {"claim": "c", "verdict": "true", "confidence": 0.9}
    fake_db.hit_row = (payload, "cached claim", 0.99)
    assert check_cache("some claim") == payload


def test_cache_query_enforces_threshold_and_ttl(fake_db: _FakeDB) -> None:
    check_cache("some claim")
    sql, params = fake_db.executed[0]
    assert "created_at > now() - make_interval" in sql  # TTL: stale verdicts expire
    assert params["threshold"] == get_settings().cache_similarity_threshold
    assert params["ttl"] == get_settings().cache_ttl_hours


def test_cache_disabled_skips_db(fake_db: _FakeDB, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CACHE_ENABLED", "false")
    get_settings.cache_clear()
    assert check_cache("some claim") is None
    assert fake_db.executed == []


def test_store_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_pool() -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(cache_module, "get_pool", broken_pool)
    monkeypatch.setattr(cache_module, "embed_text", lambda text: [0.1])
    store_verdict("claim", {"verdict": "true"})  # must not raise


# ---------------------------------------------------------------------------
# Threshold probes against the REAL production embedding model (OpenAI).
#
# These are the tests the whole cache design leans on: negation pairs are
# exactly where embedding similarity is misleadingly high, because flipping
# one word barely moves the vector. If any of these creep above the
# threshold, serving cached verdicts becomes actively dangerous.
#
# Opt-in only (TRUTHLAYER_LIVE_EMBEDDINGS=1 + a real OPENAI_API_KEY): they
# call the actual embed_texts() production path, not a mock, because a
# mocked embedding can't tell you anything about the real model's geometry —
# and after the embedding.py swap from local sentence-transformers to hosted
# OpenAI embeddings, re-running these against the real API is exactly how you
# catch a threshold that silently stopped being valid for the new model.
# ---------------------------------------------------------------------------

_LIVE_EMBEDDINGS = os.environ.get("TRUTHLAYER_LIVE_EMBEDDINGS") == "1"
_skip_unless_live = pytest.mark.skipif(
    not _LIVE_EMBEDDINGS,
    reason="live OpenAI embeddings test; run with TRUTHLAYER_LIVE_EMBEDDINGS=1 and a real key",
)

NEAR_MISS_PAIRS = [
    # negation: opposite truth values, high lexical overlap
    ("The earth is round.", "The earth is flat."),
    ("Vaccines cause autism.", "Vaccines do not cause autism."),
    ("The Great Wall is visible from space.", "The Great Wall is not visible from space."),
    # entity swap: one word changes who the claim is about
    ("Einstein won the Nobel Prize in Physics.", "Newton won the Nobel Prize in Physics."),
]

#: Realistic "same claim resubmitted" cases — typos, casing, minor rewording.
#: This is the cache's actual use case (someone re-checks a claim they, or
#: someone else, already submitted), not arbitrary paraphrase rewriting —
#: which scores lower in this embedding space and is intentionally NOT
#: guaranteed to hit (a missed cache hit just re-runs the pipeline; it's not
#: a safety issue, unlike the near-miss pairs above).
PARAPHRASE_PAIRS = [
    ("Tokyo is the capital of Japan.", "Tokyo is the capital of Japan"),
    ("Tokyo is the capital of Japan.", "tokyo is the capital of japan."),
    (
        "The Eiffel Tower is located in Paris, France.",
        "The Eiffel Tower is located in Paris, France",
    ),
    (
        "Water boils at 100 degrees Celsius at sea level.",
        "Water boils at 100 C at sea level.",
    ),
]


def _real_similarity(a: str, b: str) -> float:
    from truthlayer.embedding import embed_texts
    from truthlayer.retrieval import cosine_similarity

    va, vb = embed_texts([a, b])
    return cosine_similarity(va, vb)


@_skip_unless_live
@pytest.mark.parametrize(("claim_a", "claim_b"), NEAR_MISS_PAIRS)
def test_dangerous_near_misses_stay_below_threshold(claim_a: str, claim_b: str) -> None:
    similarity = _real_similarity(claim_a, claim_b)
    threshold = get_settings().cache_similarity_threshold
    assert similarity < threshold, (
        f"{claim_a!r} vs {claim_b!r} scored {similarity:.3f} — at threshold "
        f"{threshold} the cache would serve one claim's verdict for its opposite"
    )


@_skip_unless_live
@pytest.mark.parametrize(("claim_a", "claim_b"), PARAPHRASE_PAIRS)
def test_tight_paraphrases_hit(claim_a: str, claim_b: str) -> None:
    similarity = _real_similarity(claim_a, claim_b)
    threshold = get_settings().cache_similarity_threshold
    assert similarity >= threshold, (
        f"{claim_a!r} vs {claim_b!r} scored only {similarity:.3f} — the cache "
        f"would never hit on obvious paraphrases at threshold {threshold}"
    )
