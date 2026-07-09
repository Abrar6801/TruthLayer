"""Tests for the embedding step — the OpenAI client is mocked."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

import truthlayer.embedding as embedding_module
from truthlayer.embedding import embed_text, embed_texts


@dataclass
class _FakeEmbeddingItem:
    embedding: list[float]


@dataclass
class _FakeEmbeddingResponse:
    data: list[_FakeEmbeddingItem]


@dataclass
class _FakeEmbeddingsAPI:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> _FakeEmbeddingResponse:
        self.calls.append(kwargs)
        # Deterministic per-text vector so order can be verified.
        return _FakeEmbeddingResponse(
            data=[
                _FakeEmbeddingItem(embedding=[float(len(text)), 1.0, 0.0])
                for text in kwargs["input"]
            ]
        )


class _FakeClient:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddingsAPI()


@pytest.fixture()
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient()
    monkeypatch.setattr(embedding_module, "_get_client", lambda: client)
    return client


def test_embed_texts_preserves_order(fake_client: _FakeClient) -> None:
    vectors = embed_texts(["a", "bb", "cccc"])
    assert [v[0] for v in vectors] == [1.0, 2.0, 4.0]


def test_embed_texts_batches(fake_client: _FakeClient) -> None:
    embed_texts(["x"] * 10, batch_size=4)
    calls = fake_client.embeddings.calls
    assert len(calls) == 3  # 10 items at batch_size=4 -> batches of 4,4,2
    assert [len(c["input"]) for c in calls] == [4, 4, 2]


def test_embed_texts_requests_configured_dimensions(fake_client: _FakeClient) -> None:
    embed_texts(["hello"])
    call = fake_client.embeddings.calls[0]
    assert call["dimensions"] == 384
    assert call["model"] == "text-embedding-3-small"


def test_embed_empty_list_skips_api_call(fake_client: _FakeClient) -> None:
    assert embed_texts([]) == []
    assert fake_client.embeddings.calls == []


def test_embed_text_returns_single_vector(fake_client: _FakeClient) -> None:
    vector = embed_text("hello")
    assert vector == [5.0, 1.0, 0.0]
