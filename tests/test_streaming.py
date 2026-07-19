"""Tests for SSE progress streaming — graph internals mocked."""

from __future__ import annotations

import json
from typing import Any

import pytest

import truthlayer.graph as graph_module
from truthlayer.db import RetrievedChunk
from truthlayer.streaming import stream_verification
from truthlayer.verdict import Verdict


def _parse(frames: list[str]) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for frame in frames:
        lines = frame.strip().split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event, data))
    return events


@pytest.fixture()
def happy_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    chunk = RetrievedChunk(
        chunk_text="evidence",
        source_url="https://www.nasa.gov/wall",
        similarity=0.8,
        claim_query="c",
    )
    verdict = Verdict(
        verdict="false", confidence=0.93, rationale="because", supporting_sources=[chunk.source_url]
    )
    monkeypatch.setattr(graph_module, "decompose_claim", lambda claim: ["sub a", "sub b"])
    monkeypatch.setattr(
        graph_module,
        "collect_chunks_for_query",
        lambda query, skip_urls=None: (
            ["chunk"],
            ["https://www.nasa.gov/wall"],
            ["https://www.nasa.gov/wall"],
            [None],
        ),
    )
    monkeypatch.setattr(
        graph_module,
        "embed_and_store",
        lambda c, u, claim_query, published_dates=None: len(c),
    )
    monkeypatch.setattr(graph_module, "retrieve_evidence", lambda claim: [chunk])
    monkeypatch.setattr(
        graph_module, "generate_verdict", lambda claim, evidence, max_attempts=2: verdict
    )
    # Fresh graph so the mocks are baked into the compiled nodes.
    monkeypatch.setattr("truthlayer.streaming.get_graph", graph_module.build_graph)


def test_stream_emits_progress_then_result(happy_graph: None) -> None:
    events = _parse(list(stream_verification("the wall is visible from space")))
    names = [name for name, _ in events]

    assert names[0] == "sub_claims"
    assert "evidence" in names
    assert "judging" in names
    assert names[-1] == "result"

    result = events[-1][1]
    assert result["verdict"] == "false"
    assert result["sources"] == ["https://www.nasa.gov/wall"]

    evidence = dict(events)["evidence"]
    assert evidence["source_domains"] == ["nasa.gov"]  # domains, not full urls


def test_stream_error_frame_on_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("kaboom")

    monkeypatch.setattr("truthlayer.streaming.get_graph", boom)
    events = _parse(list(stream_verification("claim")))
    assert events[-1][0] == "error"
    assert "kaboom" not in json.dumps(events)  # internals never leak
