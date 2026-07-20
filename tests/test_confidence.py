"""Tests for post-hoc confidence remapping."""

from __future__ import annotations

import pytest

from truthlayer.confidence import CALIBRATION_ANCHORS, remap_confidence


def test_anchor_points_map_to_their_measured_accuracy() -> None:
    for stated, accuracy in CALIBRATION_ANCHORS:
        assert remap_confidence(stated) == pytest.approx(accuracy)


def test_overconfident_top_is_capped_at_measured_accuracy() -> None:
    # The dangerous case from the calibration report: stated 0.95+ was only
    # ~79% accurate. Nothing may display above that.
    assert remap_confidence(0.95) <= 0.79 + 1e-9
    assert remap_confidence(1.0) == pytest.approx(0.79)


def test_interpolation_between_anchors() -> None:
    # Halfway between (0.84, 0.75) and (0.96, 0.79).
    assert remap_confidence(0.90) == pytest.approx(0.77, abs=0.005)


def test_monotone_never_reorders_verdicts() -> None:
    grid = [i / 100 for i in range(101)]
    mapped = [remap_confidence(x) for x in grid]
    assert mapped == sorted(mapped)


def test_out_of_range_inputs_clamped() -> None:
    assert remap_confidence(-0.5) == pytest.approx(0.0)
    assert remap_confidence(1.7) == pytest.approx(0.79)
