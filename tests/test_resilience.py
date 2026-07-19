"""Integration tests for graceful degradation under upstream outages.

Each test simulates one dependency being fully down (mocked at the module
boundary) and asserts the API returns a clear, fast 503 — never a raw 500,
a hung request, or a confidently-wrong verdict built on no evidence.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

import truthlayer.graph as graph_module
from truthlayer.config import get_settings

API_KEY = "test-service-key"  # pragma: allowlist secret


@pytest.fixture()
def outage_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("TRUTHLAYER_API_KEY", API_KEY)
    get_settings.cache_clear()

    import truthlayer.cache
    from truthlayer.api import create_app

    monkeypatch.setattr(truthlayer.cache, "check_cache", lambda claim: None)
    monkeypatch.setattr(truthlayer.cache, "store_verdict", lambda claim, payload: None)
    # Use a freshly-built graph so node mocks apply (module cache bypassed).
    monkeypatch.setattr("truthlayer.graph._compiled", None)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client
    get_settings.cache_clear()


def _mock_decompose_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graph_module, "decompose_claim", lambda claim: [claim])


def test_tavily_outage_returns_clear_503(
    outage_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_decompose_ok(monkeypatch)

    def tavily_down(query: str, skip_urls: set[str] | None = None) -> Any:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(graph_module, "collect_chunks_for_query", tavily_down)
    monkeypatch.setattr(graph_module, "retrieve_evidence", lambda claim: [])

    response = outage_client.post(
        "/verify",
        json={"claim": "the sky is green"},
        headers={"X-API-Key": API_KEY},
    )

    assert response.status_code == 503
    assert "search" in response.json()["detail"].lower()
    assert response.headers["Retry-After"] == "60"
    assert "ConnectError" not in response.text  # internals never leak


def test_claude_outage_returns_clear_503(
    outage_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from truthlayer.db import RetrievedChunk

    _mock_decompose_ok(monkeypatch)
    chunk = RetrievedChunk(
        chunk_text="evidence", source_url="https://s.example", similarity=0.8, claim_query="c"
    )
    monkeypatch.setattr(
        graph_module,
        "collect_chunks_for_query",
        lambda query, skip_urls=None: (
            ["chunk"],
            ["https://s.example"],
            ["https://s.example"],
            [None],
        ),
    )
    monkeypatch.setattr(
        graph_module,
        "embed_and_store",
        lambda c, u, claim_query, published_dates=None: 1,
    )
    monkeypatch.setattr(graph_module, "retrieve_evidence", lambda claim: [chunk])

    def claude_down(claim: str, evidence: Any, max_attempts: int = 2) -> Any:
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))

    monkeypatch.setattr(graph_module, "generate_verdict", claude_down)

    response = outage_client.post(
        "/verify",
        json={"claim": "the sky is green"},
        headers={"X-API-Key": API_KEY},
    )

    assert response.status_code == 503
    assert "verdict service" in response.json()["detail"].lower()
    assert response.headers["Retry-After"] == "60"


def test_outage_does_not_burn_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """An outage must finalize immediately — no broaden/retry loop against a
    dead dependency."""
    from truthlayer.graph import build_graph

    _mock_decompose_ok(monkeypatch)

    def tavily_down(query: str, skip_urls: set[str] | None = None) -> Any:
        raise httpx.ConnectError("down")

    broadens = {"count": 0}

    def count_broaden(claim: str, prev: list[str]) -> str:
        broadens["count"] += 1
        return "wider query"

    monkeypatch.setattr(graph_module, "collect_chunks_for_query", tavily_down)
    monkeypatch.setattr(graph_module, "retrieve_evidence", lambda claim: [])
    monkeypatch.setattr(graph_module, "broaden_query", count_broaden)

    state = build_graph().invoke({"claim": "c", "llm_calls_used": 0, "errors": []})

    assert state["degraded"] == "search_unavailable"
    assert broadens["count"] == 0  # no retries against a dead search API


def test_deep_health_reports_dependency_status(
    outage_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import truthlayer.db

    class _FakePool:
        def connection(self) -> Any:
            from contextlib import contextmanager

            @contextmanager
            def cm() -> Any:
                class _Conn:
                    def execute(self, sql: str) -> None:
                        pass

                yield _Conn()

            return cm()

    monkeypatch.setattr(truthlayer.db, "get_pool", lambda: _FakePool())

    response = outage_client.get("/health?deep=true")
    assert response.status_code == 200
    body = response.json()
    assert body["dependencies"]["database"] == "ok"
    assert set(body["dependencies"]) == {"database", "anthropic", "tavily"}
