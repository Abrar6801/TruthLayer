"""Tests for the FastAPI service — the graph is mocked, auth/limits are real."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

import truthlayer.graph
from truthlayer.config import get_settings
from truthlayer.verdict import Verdict

API_KEY = "test-service-key"  # pragma: allowlist secret


def _state(**overrides: Any) -> dict[str, Any]:
    verdict = Verdict(
        verdict="false",
        confidence=0.9,
        rationale="Evidence contradicts the claim.",
        supporting_sources=["https://s.example"],
    )
    state: dict[str, Any] = {
        "claim": "c",
        "sub_claims": ["c"],
        "verdict": verdict,
        "confidence": 0.9,
        "low_confidence": False,
        "retry_count": 0,
        "errors": [],
    }
    state.update(overrides)
    return state


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("TRUTHLAYER_API_KEY", API_KEY)
    monkeypatch.setenv("VERIFY_RATE_LIMIT", "3/minute")
    get_settings.cache_clear()

    # create_app builds a fresh limiter per app, so limit state can't leak
    # across tests.
    import truthlayer.cache
    from truthlayer.api import create_app

    monkeypatch.setattr(truthlayer.graph, "verify_claim", lambda claim: _state(claim=claim))
    # Default: cache misses and writes are no-ops (no real model/DB in tests).
    monkeypatch.setattr(truthlayer.cache, "check_cache", lambda claim: None)
    monkeypatch.setattr(truthlayer.cache, "store_verdict", lambda claim, payload: None)
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_health_needs_no_auth(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_without_key_is_401(client: TestClient) -> None:
    response = client.post("/verify", json={"claim": "the sky is green"})
    assert response.status_code == 401


def test_verify_with_wrong_key_is_401(client: TestClient) -> None:
    response = client.post(
        "/verify", json={"claim": "the sky is green"}, headers={"X-API-Key": "nope"}
    )
    assert response.status_code == 401


def test_verify_happy_path(client: TestClient) -> None:
    response = client.post(
        "/verify",
        json={"claim": "the sky is green"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "false"
    assert body["confidence"] == pytest.approx(0.9)
    assert body["sources"] == ["https://s.example"]
    assert body["low_confidence"] is False


def test_verify_rejects_empty_claim(client: TestClient) -> None:
    response = client.post("/verify", json={"claim": ""}, headers={"X-API-Key": API_KEY})
    assert response.status_code == 422


def test_verify_rejects_overlong_claim(client: TestClient) -> None:
    response = client.post("/verify", json={"claim": "x" * 2000}, headers={"X-API-Key": API_KEY})
    assert response.status_code == 422


def test_rate_limit_kicks_in(client: TestClient) -> None:
    headers = {"X-API-Key": API_KEY}
    for _ in range(3):
        assert client.post("/verify", json={"claim": "abc def"}, headers=headers).status_code == 200
    response = client.post("/verify", json={"claim": "abc def"}, headers=headers)
    assert response.status_code == 429


def test_errors_do_not_leak_internals(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(claim: str) -> dict[str, Any]:
        raise RuntimeError("secret internal detail: db password is hunter2")

    monkeypatch.setattr(truthlayer.graph, "verify_claim", explode)
    response = client.post(
        "/verify", json={"claim": "the sky is green"}, headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 500
    text = response.text
    assert "hunter2" not in text
    assert "RuntimeError" not in text
    assert "Traceback" not in text
    assert "Internal server error" in text


def test_cache_hit_short_circuits_pipeline(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import truthlayer.cache

    cached_payload = {
        "claim": "the sky is green",
        "verdict": "false",
        "confidence": 0.95,
        "rationale": "cached rationale",
        "sources": ["https://cached.example"],
        "sub_claims": ["the sky is green"],
        "low_confidence": False,
        "retries": 0,
    }
    monkeypatch.setattr(truthlayer.cache, "check_cache", lambda claim: cached_payload)

    def pipeline_must_not_run(claim: str) -> Any:
        raise AssertionError("pipeline ran despite a cache hit")

    monkeypatch.setattr(truthlayer.graph, "verify_claim", pipeline_must_not_run)

    response = client.post(
        "/verify", json={"claim": "the sky is green"}, headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["served_from_cache"] is True
    assert body["rationale"] == "cached rationale"


def test_cache_miss_stores_fresh_verdict(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import truthlayer.cache

    stored: dict[str, Any] = {}
    monkeypatch.setattr(
        truthlayer.cache, "store_verdict", lambda claim, payload: stored.update(payload)
    )

    response = client.post(
        "/verify", json={"claim": "the sky is green"}, headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 200
    assert response.json()["served_from_cache"] is False
    assert stored["verdict"] == "false"
    assert "served_from_cache" not in stored  # the flag is per-response, not cached


def test_openapi_docs_generate(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/verify" in schema["paths"]
    assert "/health" in schema["paths"]
