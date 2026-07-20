"""Tests for ingestion wiring — search, embedding, and DB all mocked."""

from __future__ import annotations

from typing import Any

import pytest

import truthlayer.ingest as ingest_module
from truthlayer.ingest import collect_chunks_for_query, embed_and_store
from truthlayer.search import SearchResult


def _ingest(claim: str) -> int:
    """Collect + store, the same two calls the graph node makes."""
    chunks, urls, _, dates = collect_chunks_for_query(claim)
    return embed_and_store(chunks, urls, claim_query=claim, published_dates=dates)


@pytest.fixture()
def captured_inserts(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_insert(
        chunks: list[str],
        embeddings: list[list[float]],
        source_urls: list[str],
        claim_query: str,
        published_dates: list[str | None] | None = None,
    ) -> int:
        captured.update(
            chunks=chunks,
            embeddings=embeddings,
            source_urls=source_urls,
            claim_query=claim_query,
            published_dates=published_dates,
        )
        return len(chunks)

    monkeypatch.setattr(ingest_module, "insert_chunks", fake_insert)
    monkeypatch.setattr(ingest_module, "embed_texts", lambda texts: [[0.0, 1.0] for _ in texts])
    return captured


def test_ingest_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest_module, "tavily_search", lambda claim: [])
    assert _ingest("some claim") == 0


def test_ingest_stores_chunks(
    monkeypatch: pytest.MonkeyPatch, captured_inserts: dict[str, Any]
) -> None:
    results = [
        SearchResult(url="https://a.example", title="A", raw_content="Alpha fact. " * 10),
        SearchResult(url="https://b.example", title="B", raw_content="Beta fact. " * 10),
    ]
    monkeypatch.setattr(ingest_module, "tavily_search", lambda claim: results)

    stored = _ingest("test claim")

    assert stored == len(captured_inserts["chunks"]) > 0
    assert captured_inserts["claim_query"] == "test claim"
    # Parallel lists stay aligned: every chunk keeps its own source URL.
    assert len(captured_inserts["chunks"]) == len(captured_inserts["source_urls"])
    assert set(captured_inserts["source_urls"]) == {"https://a.example", "https://b.example"}


def test_ingest_caps_chunk_count(
    monkeypatch: pytest.MonkeyPatch, captured_inserts: dict[str, Any]
) -> None:
    monkeypatch.setenv("MAX_CHUNKS_PER_CLAIM", "5")
    monkeypatch.setenv("CHUNK_SIZE", "100")
    monkeypatch.setenv("CHUNK_OVERLAP", "0")
    from truthlayer.config import get_settings

    get_settings.cache_clear()

    huge_page = SearchResult(
        url="https://big.example",
        title="Big",
        raw_content=" ".join(f"Unique sentence number {i}." for i in range(500)),
    )
    monkeypatch.setattr(ingest_module, "tavily_search", lambda claim: [huge_page])

    stored = _ingest("flood attempt")

    assert stored == 5  # capped, not unbounded
    assert len(captured_inserts["chunks"]) == 5
