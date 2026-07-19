# Confidence calibration — baseline

Run: `20260708T182007Z` · 40 scorable verdicts

## Headline numbers

- **Brier score: 0.195** (0 = perfect; 0.25 = always answering 0.5)
- **ECE: 0.165** — on average the stated confidence is off by 16.5 points
- Mean stated confidence 0.94 vs actual accuracy 0.78 → the judge is **overconfident** overall by 16.4 points

## Reliability table

| confidence bin | n | avg stated | actual accuracy | gap (+ = overconfident) |
|---|---|---|---|---|
| 0.7–0.8 | 2 | 0.75 | 0.50 | +0.25 |
| 0.8–0.9 | 4 | 0.84 | 0.75 | +0.09 |
| 0.9–1.0 | 34 | 0.96 | 0.79 | +0.17 |

## How to read this

- A perfectly calibrated judge has every gap ≈ 0: its 0.9s are right 90% of the time.
- Overconfidence concentrated in the top bin is the dangerous pattern for a fact-checker: users trust exactly the verdicts most likely to betray them.
- With n this small, single-claim swings move bucket accuracy a lot — treat gaps under ~0.1 as noise and patterns across buckets as signal.