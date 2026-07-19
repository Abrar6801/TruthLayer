# Error analysis — baseline run `20260708T182007Z`

Every one of the 9 failures (40 claims, 77.5% accuracy) read individually and
categorized by *root cause*, because the fix for a retrieval miss (better
search/ranking) and the fix for a judgment error (better prompt/policy) are
completely different investments.

## Headline finding

**All 9 failures are judge labeling-policy errors. Zero are retrieval
failures.** In every single failure the retrieved evidence was relevant and
the rationale's *facts* are correct — the judge then mapped those facts to
the wrong verdict label. The pipeline finds the truth and mislabels it.

Two failure modes, and every failure is one of them:

### Mode 1: compound claims — MIXED predicted as FALSE (5 failures)

| id | claim (abbrev.) | what the judge did |
|---|---|---|
| 27 | Tesla founded by Musk in 2003 | correctly found: 2003 ✓, Musk-as-founder complicated → called it FALSE |
| 28 | Columbus 1492, proved Earth round | correctly found: 1492 ✓, "proved round" myth ✗ → FALSE |
| 29 | Berlin Wall fell 1989, ending WWII | correctly found: 1989 ✓, WWII ✗ → FALSE |
| 31 | Einstein's 1921 Nobel for relativity | correctly found: 1921 Nobel ✓, for photoelectric effect ✗ → FALSE |
| 33 | Titanic sank 1912, killing everyone | correctly found: sank ✓, ~710 survived ✗ → FALSE |

The pattern: a true core event plus a false attribution/detail. The dataset
labels these MIXED ("part true, part false"); the judge treats "contains a
falsehood" as sufficient for FALSE. Note its own rationales *say* "the
evidence confirms X but contradicts Y" — the mixed structure is recognized,
then discarded at labeling time.

### Mode 2: unfalsifiable/absence-of-evidence claims — UNVERIFIABLE predicted as FALSE (4 failures)

| id | claim (abbrev.) | what the judge did |
|---|---|---|
| 34 | exactly 3 trillion fish in the Pacific right now | "no source confirms the exact count" → FALSE |
| 35 | aliens visited during pyramid construction | "no credible evidence supports it" → FALSE |
| 37 | a butterfly caused Hurricane Katrina | "no evidence linking any butterfly" → FALSE |
| 38 | Shakespeare secretly written by Bacon | "rejected by mainstream scholars" → FALSE |

The pattern: the judge collapses *"cannot be established either way"* /
*"absence of supporting evidence"* into FALSE. Arguably defensible for #35
and #38 (labels worth a second look in the label review — a reasonable
person could label "fringe theory rejected by scholarship" as false), but
#34 and #37 are cleanly unverifiable: no evidence could ever confirm an
exact real-time fish count, and single-cause attribution of a hurricane to
one butterfly is untestable by construction.

## What this is NOT

- **Not retrieval:** the reference domain or an equivalent source was
  retrieved in effectively every failure; scored retrieval hit rate is
  unaffected by these misses.
- **Not hallucination:** no rationale asserts anything false.
- **Not confidence-gating:** 8/9 failures carried ≥0.85 confidence, so the
  broaden-and-retry loop (triggered below 0.6) never fired — correctly, per
  its design. This links to the calibration finding
  (`calibration_report.md`): the judge is most overconfident precisely on
  taxonomy-boundary claims.

## Actions, in order of expected value

1. **Sharpen the verdict taxonomy in the judge prompt** with explicit
   decision rules: *"if the claim conjoins a true part and a false part →
   MIXED, even though it contains a falsehood"* and *"if no obtainable
   evidence could settle the claim either way → UNVERIFIABLE, reserving
   FALSE for claims the evidence positively refutes."* One or two few-shot
   contrast pairs (Titanic-style compound; fish-count-style unfalsifiable)
   would target both modes directly. Ceiling if both modes are fixed:
   +9 claims → 100% on this dataset — realistically expect part of that.
2. **Label review** (already on the launch checklist): #35 and #38 are
   genuinely arguable UNVERIFIABLE-vs-FALSE labels; decide the policy and
   re-label consistently rather than letting the eval punish a defensible
   judgment.
3. **Do NOT invest in retrieval for accuracy right now** — this analysis
   shows accuracy is not retrieval-bound on this dataset. (Hybrid retrieval
   is still worth building for name/number-heavy claims, but measure it on
   retrieval metrics, not headline accuracy.)

**Measurement cost note:** validating action 1 requires a fresh eval run
(~40 claims ≈ 200–400 Tavily searches of the 1,000/month free quota +
~$0.40 of Claude). Run it with `--limit 10` on the mixed/unverifiable rows
first (`dataset.json` ids 27–38) for a cheap directional signal before
spending a full run.
