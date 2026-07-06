"""Tests for the embedding step — the model itself is mocked."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

import truthlayer.embedding as embedding_module
from truthlayer.embedding import embed_text, embed_texts


class _FakeModel:
    """Stands in for SentenceTransformer; records how encode() was called."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def encode(self, texts: list[str], **kwargs: Any) -> np.ndarray:
        self.calls.append({"n_texts": len(texts), **kwargs})
        # Deterministic per-text vector so order can be verified.
        return np.array([[float(len(text)), 1.0, 0.0] for text in texts])


@pytest.fixture()
def fake_model(monkeypatch: pytest.MonkeyPatch) -> _FakeModel:
    model = _FakeModel()
    monkeypatch.setattr(embedding_module, "_get_model", lambda: model)
    return model


def test_embed_texts_preserves_order(fake_model: _FakeModel) -> None:
    vectors = embed_texts(["a", "bb", "cccc"])
    assert [v[0] for v in vectors] == [1.0, 2.0, 4.0]


def test_embed_texts_batches_and_normalizes(fake_model: _FakeModel) -> None:
    embed_texts(["x"] * 10, batch_size=4)
    call = fake_model.calls[0]
    assert call["batch_size"] == 4
    assert call["normalize_embeddings"] is True


def test_embed_empty_list_skips_model(fake_model: _FakeModel) -> None:
    assert embed_texts([]) == []
    assert fake_model.calls == []


def test_embed_text_returns_single_vector(fake_model: _FakeModel) -> None:
    vector = embed_text("hello")
    assert vector == [5.0, 1.0, 0.0]
