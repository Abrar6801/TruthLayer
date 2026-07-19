"""Tests for eval/calibration.py's scoring math (no API, no files)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from calibration import (  # noqa: E402
    Bin,
    _scored,
    brier_score,
    expected_calibration_error,
    reliability_bins,
)


def _row(conf: float, predicted: str, expected: str) -> dict:
    return {"confidence": conf, "predicted_verdict": predicted, "expected_verdict": expected}


def test_scored_skips_missing_confidence_and_invalid_verdicts() -> None:
    rows = [
        _row(0.9, "true", "true"),
        {"predicted_verdict": "true", "expected_verdict": "true"},  # no confidence
        _row(0.8, "banana", "true"),  # not a real verdict
    ]
    assert _scored(rows) == [(0.9, True)]


def test_brier_perfect_and_worst_cases() -> None:
    assert brier_score([(1.0, True), (0.0, False)]) == 0.0
    assert brier_score([(1.0, False)]) == 1.0
    # Always answering 0.5 scores 0.25 regardless of outcomes.
    assert brier_score([(0.5, True), (0.5, False)]) == pytest.approx(0.25)


def test_brier_punishes_confident_wrongness_quadratically() -> None:
    mildly_wrong = brier_score([(0.6, False)])
    very_wrong = brier_score([(0.95, False)])
    assert very_wrong > mildly_wrong * 2


def test_reliability_bins_group_and_average() -> None:
    pairs = [(0.95, True), (0.92, False), (0.65, True)]
    bins = reliability_bins(pairs, width=0.1)
    assert len(bins) == 2
    top = bins[-1]
    assert top.count == 2
    assert top.avg_confidence == pytest.approx(0.935)
    assert top.accuracy == pytest.approx(0.5)
    assert top.gap == pytest.approx(0.435)


def test_confidence_of_exactly_one_lands_in_top_bin() -> None:
    bins = reliability_bins([(1.0, True)], width=0.1)
    assert len(bins) == 1
    assert bins[0].hi == pytest.approx(1.0)


def test_ece_is_count_weighted() -> None:
    bins = [
        Bin(lo=0.9, hi=1.0, count=3, avg_confidence=0.95, accuracy=0.95),  # gap 0
        Bin(lo=0.6, hi=0.7, count=1, avg_confidence=0.65, accuracy=0.0),  # gap 0.65
    ]
    assert expected_calibration_error(bins) == pytest.approx(0.65 / 4)


def test_empty_inputs_raise() -> None:
    with pytest.raises(ValueError):
        brier_score([])
    with pytest.raises(ValueError):
        expected_calibration_error([])
