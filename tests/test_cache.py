"""Tests for the semantic verdict cache.

Two groups: logic tests (DB and model mocked) and threshold probes that use
the REAL local embedding model to verify the 0.97 cutoff separates dangerous
near-misses (negations, entity swaps) from legitimate paraphrase hits.
"""

from __future__ import annotations

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
# Threshold probes with the real embedding model.
#
# These are the tests the whole cache design leans on: negation pairs are
# exactly where embedding similarity is misleadingly high, because flipping
# one word barely moves the vector. If any of these creep above the
# threshold, serving cached verdicts becomes actively dangerous.
# ---------------------------------------------------------------------------

NEAR_MISS_PAIRS = [
    # negation: opposite truth values, high lexical overlap
    ("The earth is round.", "The earth is flat."),
    ("Vaccines cause autism.", "Vaccines do not cause autism."),
    ("The Great Wall is visible from space.", "The Great Wall is not visible from space."),
    # entity swap: one word changes who the claim is about
    ("Einstein won the Nobel Prize in Physics.", "Newton won the Nobel Prize in Physics."),
]

PARAPHRASE_PAIRS = [
    (
        "Water boils at 100 degrees Celsius at sea level.",
        "At sea level, water boils at 100 degrees Celsius.",
    ),
    ("Tokyo is the capital of Japan.", "Tokyo is the capital city of Japan."),
]


def _real_similarity(a: str, b: str) -> float:
    from truthlayer.retrieval import cosine_similarity

    sentence_transformers = pytest.importorskip("sentence_transformers")
    model = sentence_transformers.SentenceTransformer(get_settings().embedding_model_name)
    va, vb = model.encode([a, b], normalize_embeddings=True)
    return cosine_similarity([float(x) for x in va], [float(x) for x in vb])


@pytest.mark.parametrize(("claim_a", "claim_b"), NEAR_MISS_PAIRS)
def test_dangerous_near_misses_stay_below_threshold(claim_a: str, claim_b: str) -> None:
    similarity = _real_similarity(claim_a, claim_b)
    threshold = get_settings().cache_similarity_threshold
    assert similarity < threshold, (
        f"{claim_a!r} vs {claim_b!r} scored {similarity:.3f} — at threshold "
        f"{threshold} the cache would serve one claim's verdict for its opposite"
    )


@pytest.mark.parametrize(("claim_a", "claim_b"), PARAPHRASE_PAIRS)
def test_tight_paraphrases_hit(claim_a: str, claim_b: str) -> None:
    similarity = _real_similarity(claim_a, claim_b)
    threshold = get_settings().cache_similarity_threshold
    assert similarity >= threshold, (
        f"{claim_a!r} vs {claim_b!r} scored only {similarity:.3f} — the cache "
        f"would never hit on obvious paraphrases at threshold {threshold}"
    )
