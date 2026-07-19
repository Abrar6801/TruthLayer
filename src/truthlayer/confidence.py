"""Post-hoc confidence calibration: map stated confidence → empirical accuracy.

The calibration analysis (eval/calibration_report.md, baseline run
20260708T182007Z) measured that the judge's stated confidence runs ~16
points hot: verdicts stating 0.9+ were right only 79% of the time. This
module corrects the *displayed* number by interpolating through the
measured (stated confidence → actual accuracy) anchor points, so a shown
"79%" means "verdicts like this were right 79% of the time".

Two boundaries matter:

- The remap is applied ONLY at the API response layer. The graph's internal
  broaden-and-retry gate keeps comparing the judge's RAW confidence against
  its threshold — those two were tuned together, and silently feeding the
  gate remapped values would change retry behavior (and cost) untested.
- Responses carry both `confidence` (remapped) and `raw_confidence`, so
  future eval runs can re-measure calibration on the raw signal and refit.

The anchors are a point-in-time fit on n=40 — coarse by construction. They
must be refit whenever the judge prompt or model changes (the current
anchors predate the 2026-07-18 taxonomy-fix prompt, noted in the constant's
provenance comment). A wrong-but-close mapping still beats displaying a
number measured to be meaningless.
"""

from __future__ import annotations

#: (stated_confidence, measured_accuracy) anchors, monotone non-decreasing.
#: Provenance: reliability table of eval/calibration_report.md — bins
#: 0.7-0.8 → 0.50 (n=2), 0.8-0.9 → 0.75 (n=4), 0.9-1.0 → 0.79 (n=34),
#: anchored at each bin's average stated confidence. The top is held flat at
#: the top bin's accuracy: no measurement supports displaying more than 0.79
#: however sure the judge claims to be. Refit after any judge prompt/model
#: change (fitted on the pre-2026-07-18 prompt).
CALIBRATION_ANCHORS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (0.75, 0.50),
    (0.84, 0.75),
    (0.96, 0.79),
    (1.0, 0.79),
)


def remap_confidence(raw: float, anchors: tuple[tuple[float, float], ...] | None = None) -> float:
    """Map a raw stated confidence to calibrated (empirical-accuracy) scale.

    Piecewise-linear interpolation through the measured anchors; inputs are
    clamped into [0, 1] first. Monotone by construction, so remapping never
    reorders two verdicts by confidence.
    """
    points = anchors if anchors is not None else CALIBRATION_ANCHORS
    x = min(1.0, max(0.0, raw))
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if x <= x1:
            if x1 == x0:  # duplicate anchor x — take the right-hand value
                return round(y1, 4)
            fraction = (x - x0) / (x1 - x0)
            return round(y0 + fraction * (y1 - y0), 4)
    return round(points[-1][1], 4)
