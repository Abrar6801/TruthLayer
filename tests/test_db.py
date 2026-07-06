"""Tests for the Supabase wrapper — the client is mocked."""

from __future__ import annotations

from typing import Any

import pytest

import truthlayer.db as db_module
from truthlayer.db import insert_chunks, query_nearest


class _FakeExecuteResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeClient:
    def __init__(self) -> None:
        self.inserted_rows: list[dict[str, Any]] = []
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_response: list[dict[str, Any]] = []

    # supabase-py fluent interface: client.table(...).insert(rows).execute()
    def table(self, name: str) -> _FakeClient:
        return self

    def insert(self, rows: list[dict[str, Any]]) -> _FakeClient:
        self.inserted_rows.extend(rows)
        return self

    def rpc(self, name: str, params: dict[str, Any]) -> _FakeClient:
        self.rpc_calls.append((name, params))
        return self

    def execute(self) -> _FakeExecuteResult:
        return _FakeExecuteResult(self.rpc_response or self.inserted_rows)


@pytest.fixture()
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient()
    monkeypatch.setattr(db_module, "get_client", lambda: client)
    return client


def test_insert_chunks_builds_rows(fake_client: _FakeClient) -> None:
    count = insert_chunks(
        chunks=["text one", "text two"],
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
        source_urls=["https://a.example", "https://b.example"],
        claim_query="test claim",
    )
    assert count == 2
    assert fake_client.inserted_rows[0] == {
        "chunk_text": "text one",
        "embedding": [0.1, 0.2],
        "source_url": "https://a.example",
        "claim_query": "test claim",
    }


def test_insert_chunks_rejects_mismatched_lengths(fake_client: _FakeClient) -> None:
    with pytest.raises(ValueError, match="same length"):
        insert_chunks(
            chunks=["one"],
            embeddings=[[0.1], [0.2]],
            source_urls=["https://a.example"],
            claim_query="claim",
        )


def test_insert_chunks_empty_is_noop(fake_client: _FakeClient) -> None:
    assert insert_chunks([], [], [], claim_query="claim") == 0
    assert fake_client.inserted_rows == []


def test_query_nearest_parses_rows(fake_client: _FakeClient) -> None:
    fake_client.rpc_response = [
        {
            "chunk_text": "evidence",
            "source_url": "https://a.example",
            "similarity": 0.91,
            "claim_query": "claim",
        }
    ]
    chunks = query_nearest([0.1, 0.2], top_k=5, min_similarity=0.3)

    assert len(chunks) == 1
    assert chunks[0].similarity == pytest.approx(0.91)
    rpc_name, rpc_params = fake_client.rpc_calls[0]
    assert rpc_name == "match_evidence_chunks"
    assert rpc_params["match_count"] == 5
    assert rpc_params["min_similarity"] == 0.3
