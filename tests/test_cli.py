"""Tests for the CLI entry point — the graph is mocked."""

from __future__ import annotations

import pytest

import truthlayer.graph
from truthlayer.cli import MAX_CLAIM_LENGTH, main, run_pipeline
from truthlayer.verdict import Verdict


def _state(**overrides: object) -> dict[str, object]:
    verdict = Verdict(
        verdict="false",
        confidence=0.9,
        rationale="Evidence contradicts the claim.",
        supporting_sources=["https://s.example"],
    )
    state: dict[str, object] = {
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


def test_empty_claim_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["   "])


def test_overlong_claim_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["x" * (MAX_CLAIM_LENGTH + 1)])


def test_full_pipeline_prints_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(truthlayer.graph, "verify_claim", lambda claim: _state())

    assert run_pipeline("the moon is made of cheese") == 0
    out = capsys.readouterr().out
    assert "FALSE" in out
    assert "90%" in out
    assert "https://s.example" in out


def test_low_confidence_is_flagged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    unsure = Verdict(
        verdict="unverifiable", confidence=0.3, rationale="thin evidence", supporting_sources=[]
    )
    monkeypatch.setattr(
        truthlayer.graph,
        "verify_claim",
        lambda claim: _state(verdict=unsure, confidence=0.3, low_confidence=True, retry_count=2),
    )

    assert run_pipeline("obscure claim") == 0
    out = capsys.readouterr().out
    assert "UNVERIFIABLE" in out
    assert "low confidence" in out
    assert "Retries" in out


def test_missing_verdict_is_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(truthlayer.graph, "verify_claim", lambda claim: _state(verdict=None))

    assert run_pipeline("claim") == 1
    assert "ERROR" in capsys.readouterr().out


def test_sub_claims_are_listed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        truthlayer.graph,
        "verify_claim",
        lambda claim: _state(sub_claims=["part one", "part two"]),
    )

    assert run_pipeline("compound claim") == 0
    out = capsys.readouterr().out
    assert "part one" in out
    assert "part two" in out
