"""Tests for the CLI entry point — pipeline stages mocked."""

from __future__ import annotations

import pytest

import truthlayer.ingest
import truthlayer.retrieval
import truthlayer.verdict
from truthlayer.cli import MAX_CLAIM_LENGTH, main, run_pipeline
from truthlayer.db import RetrievedChunk
from truthlayer.verdict import Verdict


def test_empty_claim_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["   "])


def test_overlong_claim_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["x" * (MAX_CLAIM_LENGTH + 1)])


def test_no_search_results_reports_unverifiable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(truthlayer.ingest, "gather_evidence", lambda claim: 0)
    assert run_pipeline("some claim") == 0
    assert "UNVERIFIABLE" in capsys.readouterr().out


def test_no_relevant_chunks_reports_unverifiable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(truthlayer.ingest, "gather_evidence", lambda claim: 12)
    monkeypatch.setattr(truthlayer.retrieval, "retrieve_evidence", lambda claim: [])
    assert run_pipeline("some claim") == 0
    out = capsys.readouterr().out
    assert "UNVERIFIABLE" in out
    assert "threshold" in out


def test_full_pipeline_prints_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    chunk = RetrievedChunk(
        chunk_text="evidence", source_url="https://s.example", similarity=0.8, claim_query="c"
    )
    verdict = Verdict(
        verdict="false",
        confidence=0.9,
        rationale="Evidence contradicts the claim.",
        supporting_sources=["https://s.example"],
    )
    monkeypatch.setattr(truthlayer.ingest, "gather_evidence", lambda claim: 5)
    monkeypatch.setattr(truthlayer.retrieval, "retrieve_evidence", lambda claim: [chunk])
    monkeypatch.setattr(truthlayer.verdict, "generate_verdict", lambda claim, evidence: verdict)

    assert run_pipeline("the moon is made of cheese") == 0
    out = capsys.readouterr().out
    assert "FALSE" in out
    assert "90%" in out
    assert "https://s.example" in out
