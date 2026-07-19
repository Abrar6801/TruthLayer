# Directional eval — judge taxonomy fix (run `20260719T015451Z`)

A targeted re-run of dataset ids 27–38 (every MIXED and UNVERIFIABLE claim,
containing all 9 baseline failures) against production after the 2026-07-18
judge-prompt change (`fix: sharpen verdict taxonomy decision rules`,
`8617aeb`). 12 claims ≈ 1/3 the cost of a full run — a cheap directional
read, not a headline number.

## Result: subset accuracy 3/12 → 7/12

| id | expected | baseline | after fix | |
|---|---|---|---|---|
| 27 Tesla/Musk | mixed | false | **mixed** | ✅ recovered |
| 28 Columbus/round Earth | mixed | false | **mixed** | ✅ recovered |
| 29 Berlin Wall/WWII | mixed | false | **mixed** | ✅ recovered |
| 30 | mixed | mixed | mixed | held |
| 31 Einstein Nobel | mixed | false | false | ❌ still wrong |
| 32 | mixed | mixed | mixed | held |
| 33 Titanic survivors | mixed | false | **mixed** | ✅ recovered |
| 34 exact fish count | unverifiable | false | false | ❌ still wrong |
| 35 pyramid aliens | unverifiable | false | false | ❌ still wrong |
| 36 | unverifiable | unverifiable | unverifiable | held |
| 37 butterfly/Katrina | unverifiable | false | false | ❌ still wrong |
| 38 Bacon/Shakespeare | unverifiable | false | false | ❌ still wrong |

## Reading it honestly

- **The compound-claim rule worked**: 4 of 5 MIXED→FALSE failures recovered,
  and no previously-correct claim in the subset regressed. The one hold-out
  (#31, Einstein's Nobel) arguably has the *smallest* true part — "won the
  1921 Prize" is true, "for relativity" is false — and the judge still reads
  the false attribution as dominant.
- **The unverifiable rule did NOT land**: 0 of 4 recovered. The judge keeps
  collapsing "no evidence could settle this" into FALSE, even with the
  explicit decision rule and few-shot. Two of these (#35 aliens, #38 Bacon)
  were already flagged in `error_analysis.md` as arguable labels — scholarly
  consensus *rejecting* a fringe theory is reasonably read as refutation. The
  label review should settle the policy before more prompt-engineering chases
  a possibly-wrong target. #34/#37 remain genuine misses.
- **Implied full-dataset accuracy ~87.5%** (28 unchanged correct + 7),
  *IF* the untested 28 true/false claims didn't regress — plausible
  (the changed rules only bear on mixed/unverifiable boundaries) but
  unverified until a full run. Do not quote 87.5% as measured.

## Next actions

1. Label review (already owed): decide the unverifiable-vs-false policy for
   fringe-theory claims; re-label #35/#38 if needed.
2. Full 40-claim run to (a) confirm no true/false regressions and (b) refit
   the confidence-remap anchors on the new prompt's raw confidences.
3. Only then, if #34/#37-style claims still miss: another prompt iteration
   aimed specifically at "unfalsifiable by construction" claims.
