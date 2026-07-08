"""Tests for the Postgres/pgvector wrapper — the connection pool is mocked."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

import truthlayer.db as db_module
from truthlayer.db import insert_chunks, query_nearest


class _FakeCursor:
    def __init__(self, store: _FakeDB) -> None:
        self._store = store
        self.rowcount = -1

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        self._store.executed.append((sql, rows))
        self.rowcount = len(rows)

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        pass


class _FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _FakeConnection:
    def __init__(self, store: _FakeDB) -> None:
        self._store = store

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._store)

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _FakeResult:
        self._store.executed.append((sql, params))
        return _FakeResult(self._store.query_rows)


class _FakeDB:
    """Stands in for the psycopg connection pool; records every statement."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.query_rows: list[tuple[Any, ...]] = []

    @contextmanager
    def connection(self) -> Any:
        yield _FakeConnection(self)


@pytest.fixture()
def fake_db(monkeypatch: pytest.MonkeyPatch) -> _FakeDB:
    db = _FakeDB()
    monkeypatch.setattr(db_module, "get_pool", lambda: db)
    return db


def test_insert_chunks_parameterizes_rows(fake_db: _FakeDB) -> None:
    count = insert_chunks(
        chunks=["text one", "text two"],
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
        source_urls=["https://a.example", "https://b.example"],
        claim_query="test claim",
    )
    assert count == 2
    sql, rows = fake_db.executed[0]
    # Values travel as parameters — never interpolated into the SQL string.
    assert "%s" in sql
    assert "text one" not in sql
    assert rows[0][0] == "text one"
    assert rows[0][2] == "https://a.example"
    assert rows[0][3] == "test claim"


def test_insert_chunks_rejects_mismatched_lengths(fake_db: _FakeDB) -> None:
    with pytest.raises(ValueError, match="same length"):
        insert_chunks(
            chunks=["one"],
            embeddings=[[0.1], [0.2]],
            source_urls=["https://a.example"],
            claim_query="claim",
        )


def test_insert_chunks_empty_is_noop(fake_db: _FakeDB) -> None:
    assert insert_chunks([], [], [], claim_query="claim") == 0
    assert fake_db.executed == []


def test_query_nearest_parses_rows(fake_db: _FakeDB) -> None:
    fake_db.query_rows = [("evidence", "https://a.example", 0.91, "claim")]

    chunks = query_nearest([0.1, 0.2], top_k=5, min_similarity=0.3)

    assert len(chunks) == 1
    assert chunks[0].chunk_text == "evidence"
    assert chunks[0].similarity == pytest.approx(0.91)
    sql, params = fake_db.executed[0]
    assert "ORDER BY embedding <=>" in sql
    assert params["k"] == 5
    assert params["min_sim"] == 0.3


def test_query_nearest_threshold_in_sql(fake_db: _FakeDB) -> None:
    query_nearest([0.5], top_k=3, min_similarity=0.7)
    sql, _ = fake_db.executed[0]
    assert ">= %(min_sim)s" in sql  # filtering happens server-side, not in Python
