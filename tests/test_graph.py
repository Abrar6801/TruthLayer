"""Tests for the LangGraph pipeline — every node's externals are mocked."""

from __future__ import annotations

from typing import Any

import pytest

import truthlayer.graph as graph_module
from truthlayer.db import RetrievedChunk
from truthlayer.graph import build_graph
from truthlayer.verdict import Verdict


def _chunk(text: str = "evidence", url: str = "https://s.example") -> RetrievedChunk:
    return RetrievedChunk(chunk_text=text, source_url=url, similarity=0.8, claim_query="c")


def _verdict(v: str = "false", confidence: float = 0.9) -> Verdict:
    return Verdict(
        verdict=v,  # type: ignore[arg-type]
        confidence=confidence,
        rationale="because",
        supporting_sources=["https://s.example"],
    )


class _Recorder:
    """Tracks calls into the mocked node internals."""

    def __init__(self) -> None:
        self.ingest_calls: list[tuple[str, set[str]]] = []
        self.broaden_calls = 0
        self.judge_calls = 0


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()

    def fake_collect(query: str, skip_urls: set[str] | None = None) -> Any:
        rec.ingest_calls.append((query, set(skip_urls or set())))
        url = f"https://{len(rec.ingest_calls)}.example"
        return [f"chunk from {query}"], [url], [url]

    monkeypatch.setattr(graph_module, "decompose_claim", lambda claim: [f"sub of {claim}"])
    monkeypatch.setattr(graph_module, "collect_chunks_for_query", fake_collect)
    monkeypatch.setattr(
        graph_module, "embed_and_store", lambda chunks, urls, claim_query: len(chunks)
    )
    monkeypatch.setattr(graph_module, "retrieve_evidence", lambda claim: [_chunk()])
    monkeypatch.setattr(graph_module, "broaden_query", lambda claim, prev: rec_broaden(rec, claim))
    return rec


def rec_broaden(rec: _Recorder, claim: str) -> str:
    rec.broaden_calls += 1
    return f"broadened {rec.broaden_calls}: {claim}"


def test_happy_path_no_retry(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder) -> None:
    def fake_judge(claim: str, evidence: Any, max_attempts: int = 2) -> Verdict:
        recorder.judge_calls += 1
        return _verdict(confidence=0.9)

    monkeypatch.setattr(graph_module, "generate_verdict", fake_judge)

    state = build_graph().invoke({"claim": "the sky is green", "llm_calls_used": 0})

    assert state["verdict"].verdict == "false"
    assert state["low_confidence"] is False
    assert state.get("retry_count", 0) == 0
    assert recorder.judge_calls == 1
    assert recorder.broaden_calls == 0
    assert len(recorder.ingest_calls) == 1  # one sub-claim, one pass


def test_low_confidence_retries_then_flags(
    monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    def always_unsure(claim: str, evidence: Any, max_attempts: int = 2) -> Verdict:
        recorder.judge_calls += 1
        return _verdict(v="unverifiable", confidence=0.3)

    monkeypatch.setattr(graph_module, "generate_verdict", always_unsure)

    state = build_graph().invoke({"claim": "obscure claim", "retry_count": 0, "llm_calls_used": 0})

    # 2 retries max: judge ran 3 times (initial + 2 retries), broaden twice.
    assert recorder.judge_calls == 3
    assert recorder.broaden_calls == 2
    assert state["retry_count"] == 2
    assert state["low_confidence"] is True
    # Every search pass ran: 1 initial sub-claim + 2 broadened queries.
    assert len(recorder.ingest_calls) == 3


def test_retry_uses_broadened_query_not_same_search(
    monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    confidences = iter([0.2, 0.9])

    def improves(claim: str, evidence: Any, max_attempts: int = 2) -> Verdict:
        return _verdict(confidence=next(confidences))

    monkeypatch.setattr(graph_module, "generate_verdict", improves)

    state = build_graph().invoke({"claim": "my claim", "llm_calls_used": 0})

    assert state["retry_count"] == 1
    assert state["low_confidence"] is False
    queries = [q for q, _ in recorder.ingest_calls]
    assert queries[0] == "sub of my claim"
    assert queries[1].startswith("broadened")  # never the same search twice


def test_dedup_urls_across_passes(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder) -> None:
    confidences = iter([0.2, 0.9])
    monkeypatch.setattr(
        graph_module,
        "generate_verdict",
        lambda claim, evidence, max_attempts=2: _verdict(confidence=next(confidences)),
    )

    build_graph().invoke({"claim": "c", "llm_calls_used": 0})

    # The retry pass must receive the URLs ingested by the first pass.
    _, second_pass_skip = recorder.ingest_calls[1]
    assert "https://1.example" in second_pass_skip


def test_llm_call_budget_is_enforced(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder) -> None:
    cap = 3
    monkeypatch.setenv("MAX_LLM_CALLS_PER_CLAIM", str(cap))
    from truthlayer.config import get_settings

    get_settings.cache_clear()

    monkeypatch.setattr(
        graph_module,
        "generate_verdict",
        lambda claim, evidence, max_attempts=2: _verdict(confidence=0.1),
    )

    state = build_graph().invoke({"claim": "c", "retry_count": 0, "llm_calls_used": 0})

    assert state["llm_calls_used"] <= cap
    assert state["low_confidence"] is True


def test_no_evidence_skips_llm_judge(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder) -> None:
    monkeypatch.setattr(graph_module, "retrieve_evidence", lambda claim: [])

    def should_not_run(claim: str, evidence: Any, max_attempts: int = 2) -> Verdict:
        raise AssertionError("judge LLM must not be called with no evidence")

    monkeypatch.setattr(graph_module, "generate_verdict", should_not_run)

    state = build_graph().invoke({"claim": "c", "llm_calls_used": 0})

    assert state["verdict"].verdict == "unverifiable"
    assert state["low_confidence"] is True


def test_concurrent_fanout_dedups_overlapping_urls(
    monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    """Two sub-claims whose searches return the SAME url: only one copy stored."""
    monkeypatch.setattr(
        graph_module, "decompose_claim", lambda claim: ["sub one", "sub two", "sub three"]
    )

    def overlapping_collect(query: str, skip_urls: set[str] | None = None) -> Any:
        # Every branch returns the same shared URL plus one unique URL.
        shared = "https://shared.example"
        unique = f"https://{query.replace(' ', '-')}.example"
        return (
            [f"shared chunk via {query}", f"unique chunk via {query}"],
            [shared, unique],
            [shared, unique],
        )

    stored_batches: list[list[str]] = []

    def capture_store(chunks: list[str], urls: list[str], claim_query: str) -> int:
        stored_batches.append(list(urls))
        return len(chunks)

    monkeypatch.setattr(graph_module, "collect_chunks_for_query", overlapping_collect)
    monkeypatch.setattr(graph_module, "embed_and_store", capture_store)
    monkeypatch.setattr(
        graph_module,
        "generate_verdict",
        lambda claim, evidence, max_attempts=2: _verdict(confidence=0.9),
    )

    state = build_graph().invoke({"claim": "compound claim", "llm_calls_used": 0})

    # One embed/store batch for the whole fan-out (merged), and the shared
    # URL appears exactly once across everything stored.
    assert len(stored_batches) == 1
    assert stored_batches[0].count("https://shared.example") == 1
    assert state["ingested_urls"].count("https://shared.example") == 1


def test_search_failure_does_not_sink_request(
    monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    def broken_collect(query: str, skip_urls: set[str] | None = None) -> Any:
        raise RuntimeError("tavily down")

    monkeypatch.setattr(graph_module, "collect_chunks_for_query", broken_collect)
    monkeypatch.setattr(
        graph_module,
        "generate_verdict",
        lambda claim, evidence, max_attempts=2: _verdict(confidence=0.9),
    )

    state = build_graph().invoke({"claim": "c", "llm_calls_used": 0, "errors": []})

    assert state["verdict"] is not None  # judged on whatever evidence retrieval found
    assert any("tavily down" in e for e in state["errors"])
