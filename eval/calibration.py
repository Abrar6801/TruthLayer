"""Measure how trustworthy the judge's stated confidence is.

Usage:

    python eval/calibration.py eval/results/<file>.json
    python eval/calibration.py eval/results/<file>.json --report eval/calibration_report.md

Why this exists: the /verify response ships a `confidence` number, but until
it's measured that number is decoration. Calibration asks: *of the verdicts
where the model said 0.9, were ~90% actually right?* A model can be accurate
but miscalibrated (right often, but its 0.95s and 0.6s are interchangeable),
and for a fact-checker the confidence is part of the product — users decide
whether to trust a verdict partly on it.

Two standard numbers, both computed against "was the predicted verdict
correct" as the outcome:

- **Brier score** = mean((confidence − correct)²). 0 is perfect; 0.25 is
  what you'd score by always saying 0.5. Punishes confident wrongness
  quadratically.
- **ECE (expected calibration error)** = the bucket-weighted average gap
  between stated confidence and actual accuracy. "On average, the stated
  confidence is off by X points."

No API calls, no cost — this reads a frozen run_eval.py results file.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERDICTS = ("true", "false", "mixed", "unverifiable")


@dataclass(frozen=True)
class Bin:
    """One confidence bucket of the reliability table."""

    lo: float
    hi: float
    count: int
    avg_confidence: float
    accuracy: float

    @property
    def gap(self) -> float:
        """Signed miscalibration: positive means overconfident."""
        return self.avg_confidence - self.accuracy


def _scored(results: list[dict[str, Any]]) -> list[tuple[float, bool]]:
    """Extract (confidence, was_correct) pairs, skipping unscorable rows."""
    pairs: list[tuple[float, bool]] = []
    for r in results:
        conf = r.get("confidence")
        if conf is None or r.get("predicted_verdict") not in VERDICTS:
            continue
        pairs.append((float(conf), r["predicted_verdict"] == r["expected_verdict"]))
    return pairs


def brier_score(pairs: list[tuple[float, bool]]) -> float:
    """Mean squared error between stated confidence and correctness."""
    if not pairs:
        raise ValueError("no scorable results")
    return statistics.mean((conf - (1.0 if ok else 0.0)) ** 2 for conf, ok in pairs)


def reliability_bins(pairs: list[tuple[float, bool]], width: float = 0.1) -> list[Bin]:
    """Bucket by stated confidence; report avg confidence vs accuracy per bucket.

    Empty buckets are omitted — with a small eval set most of the [0, 0.5)
    range never occurs, and rows of zeros hide the signal.
    """
    if not 0 < width <= 1:
        raise ValueError("width must be in (0, 1]")
    n_bins = round(1 / width)
    grouped: dict[int, list[tuple[float, bool]]] = {}
    for conf, ok in pairs:
        # min() folds confidence == 1.0 into the top bucket instead of a
        # phantom bucket of its own.
        idx = min(int(conf / width), n_bins - 1)
        grouped.setdefault(idx, []).append((conf, ok))
    bins = []
    for idx in sorted(grouped):
        members = grouped[idx]
        bins.append(
            Bin(
                lo=idx * width,
                hi=(idx + 1) * width,
                count=len(members),
                avg_confidence=statistics.mean(c for c, _ in members),
                accuracy=sum(1 for _, ok in members if ok) / len(members),
            )
        )
    return bins


def expected_calibration_error(bins: list[Bin]) -> float:
    """Bucket-weighted mean |confidence − accuracy| over the reliability bins."""
    total = sum(b.count for b in bins)
    if total == 0:
        raise ValueError("no scorable results")
    return sum(abs(b.gap) * b.count for b in bins) / total


def render_report(
    pairs: list[tuple[float, bool]], bins: list[Bin], run_meta: dict[str, Any]
) -> str:
    """Render the calibration analysis as markdown."""
    brier = brier_score(pairs)
    ece = expected_calibration_error(bins)
    overall_conf = statistics.mean(c for c, _ in pairs)
    overall_acc = sum(1 for _, ok in pairs if ok) / len(pairs)
    direction = "overconfident" if overall_conf > overall_acc else "underconfident"

    lines = [
        f"# Confidence calibration — {run_meta.get('run_tag', '?')}",
        "",
        f"Run: `{run_meta.get('timestamp', '?')}` · {len(pairs)} scorable verdicts",
        "",
        "## Headline numbers",
        "",
        f"- **Brier score: {brier:.3f}** (0 = perfect; 0.25 = always answering 0.5)",
        f"- **ECE: {ece:.3f}** — on average the stated confidence is off by "
        f"{ece * 100:.1f} points",
        f"- Mean stated confidence {overall_conf:.2f} vs actual accuracy {overall_acc:.2f} "
        f"→ the judge is **{direction}** overall by "
        f"{abs(overall_conf - overall_acc) * 100:.1f} points",
        "",
        "## Reliability table",
        "",
        "| confidence bin | n | avg stated | actual accuracy | gap (+ = overconfident) |",
        "|---|---|---|---|---|",
    ]
    for b in bins:
        lines.append(
            f"| {b.lo:.1f}–{b.hi:.1f} | {b.count} | {b.avg_confidence:.2f} "
            f"| {b.accuracy:.2f} | {b.gap:+.2f} |"
        )
    lines += [
        "",
        "## How to read this",
        "",
        "- A perfectly calibrated judge has every gap ≈ 0: its 0.9s are right " "90% of the time.",
        "- Overconfidence concentrated in the top bin is the dangerous pattern "
        "for a fact-checker: users trust exactly the verdicts most likely to "
        "betray them.",
        "- With n this small, single-claim swings move bucket accuracy a lot — "
        "treat gaps under ~0.1 as noise and patterns across buckets as signal.",
    ]
    return "\n".join(lines)


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(description="Calibration analysis of a saved eval run.")
    parser.add_argument("results_file", help="A file produced by run_eval.py")
    parser.add_argument("--report", default="eval/calibration_report.md")
    args = parser.parse_args()

    with open(args.results_file, encoding="utf-8") as f:
        run = json.load(f)
    pairs = _scored(run["results"])
    bins = reliability_bins(pairs)
    report = render_report(pairs, bins, run)
    Path(args.report).write_text(report, encoding="utf-8")
    print(report)
    print(f"\nReport written to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
