"""Tests for cross-encoder reranking — the model is mocked."""

from __future__ import annotations

from typing import Any

import pytest

import truthlayer.reranker as reranker_module
import truthlayer.retrieval as retrieval_module
from truthlayer.config import get_settings
from truthlayer.db import RetrievedChunk
from truthlayer.reranker import rerank


def _chunk(text: str, similarity: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_text=text,
        source_url=f"https://{text[:4]}.example",
        similarity=similarity,
        claim_query="c",
    )


class _FakeCrossEncoder:
    """Scores pairs by a keyword match so tests can control the ordering."""

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0 if "relevant" in chunk else 0.1 for _, chunk in pairs]


@pytest.fixture()
def fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reranker_module, "_get_model", lambda: _FakeCrossEncoder())


def test_rerank_reorders_by_cross_encoder_score(fake_model: None) -> None:
    chunks = [
        _chunk("filler text one", similarity=0.9),  # bi-encoder loved it
        _chunk("the relevant passage", similarity=0.4),  # bi-encoder ranked it low
        _chunk("filler text two", similarity=0.8),
    ]
    ranked = rerank("some claim", chunks, top_k=2)
    assert len(ranked) == 2
    assert ranked[0].chunk_text == "the relevant passage"  # cross-encoder wins


def test_rerank_preserves_original_similarity(fake_model: None) -> None:
    chunks = [_chunk("the relevant passage", similarity=0.4)]
    ranked = rerank("claim", chunks, top_k=1)
    assert ranked[0].similarity == pytest.approx(0.4)  # bi-encoder score kept for reports


def test_rerank_empty_is_noop(fake_model: None) -> None:
    assert rerank("claim", [], top_k=5) == []


def test_retrieval_uses_wide_k_when_rerank_enabled(
    monkeypatch: pytest.MonkeyPatch, fake_model: None
) -> None:
    monkeypatch.setenv("RERANK_ENABLED", "true")
    monkeypatch.setenv("RETRIEVAL_CANDIDATES", "20")
    monkeypatch.setenv("RETRIEVAL_TOP_K", "8")
    get_settings.cache_clear()

    captured: dict[str, Any] = {}

    def fake_nearest(embedding: list[float], top_k: int, min_similarity: float = 0.0) -> list[Any]:
        captured["fetch_k"] = top_k
        return [_chunk(f"the relevant passage {i}") for i in range(top_k)]

    monkeypatch.setattr(retrieval_module, "embed_text", lambda claim: [0.1])
    monkeypatch.setattr(retrieval_module, "query_nearest", fake_nearest)

    result = retrieval_module.retrieve_evidence("claim")

    assert captured["fetch_k"] == 20  # wide candidate pool for the reranker
    assert len(result) == 8  # only reranked top-k reach the judge


def test_retrieval_unchanged_when_rerank_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()  # rerank_enabled defaults to False
    captured: dict[str, Any] = {}

    def fake_nearest(embedding: list[float], top_k: int, min_similarity: float = 0.0) -> list[Any]:
        captured["fetch_k"] = top_k
        return []

    monkeypatch.setattr(retrieval_module, "embed_text", lambda claim: [0.1])
    monkeypatch.setattr(retrieval_module, "query_nearest", fake_nearest)

    retrieval_module.retrieve_evidence("claim")

    assert captured["fetch_k"] == 8  # single-stage: fetch exactly top_k
