# Reranking report — Task 4.2 (honest negative result)

Comparison of the frozen baseline (`20260708T182007Z_baseline`, reranking
off) against `20260708T183028Z_rerank_parallel` (cross-encoder
`ms-marco-MiniLM-L-6-v2` reranking pgvector's top-20 down to 8).

**Methodology note:** the "after" run also includes the Task 4.3 concurrent
search fan-out. Concurrency changes *when* work happens, not *which* chunks
are stored or retrieved, so accuracy deltas are attributed to reranking; the
per-stage latency table separates the two effects (reranking lives in
`retrieve`, concurrency in `search_and_embed`).

## Headline: reranking did NOT improve accuracy

| Metric | Baseline (no rerank) | With reranking | Δ |
|---|---|---|---|
| Verdict accuracy | **77.5%** | **75.0%** | **−2.5 pp** |
| Retrieval hit rate (ref domain cited) | 42.9% | 40.0% | −2.9 pp |
| `retrieve` stage latency (avg) | 0.09 s | 1.24 s | **+1.15 s** |
| Cost per verdict | $0.0092 | $0.0090 | ≈ unchanged |

Confusion-matrix delta: the only change is one **mixed** claim now predicted
**false** (mixed row went 2/7 correct → 1/7). True/false rows stayed perfect
(26/26) in both runs.

## The claim that flipped, and why

**#30 — "Mount Everest, located in Japan, is the tallest mountain above sea
level."** (expected MIXED: tallest = true, Japan = false)

- **Baseline** retrieved Wikipedia's Everest page, whose chunks support both
  halves (elevation ranking + actual location). Judge: **mixed (0.90)** ✓
- **Reranked** run promoted chunks from himalayanclub.org about *Japanese
  expeditions climbing Everest* — text with maximal lexical/topical overlap
  with the claim ("Everest" + "Japan" both prominent) but no bearing on
  either the "tallest" or the "located in" fact. The Wikipedia chunk fell
  out of the top-8. Judge, now missing the tallest-mountain evidence:
  **false (0.95)** ✗

This is the instructive failure: the cross-encoder scores *relevance to the
claim text*, not *usefulness for judging the claim*. A passage about
"Japanese Everest expeditions" is extremely relevant to the string "Everest…
Japan" while being evidentially useless — and the reranker has no way to
know the difference.

## Why reranking didn't help here (analysis)

Reranking earns its keep when the candidate pool is polluted — when the
bi-encoder's top-k over a large, heterogeneous corpus contains plausible-
looking off-topic passages. TruthLayer's retrieval doesn't have that shape:
every claim searches the web *for itself*, so the per-claim evidence store is
already small (≤ ~240 chunks) and pre-filtered by the search engine for
topical relevance. The bi-encoder's top-8 over that pool and the
cross-encoder's top-8 over the top-20 are usually the *same chunks in
slightly different order* — so the ceiling on possible gain was low, and the
one systematic difference it did introduce (lexical-overlap promotion) was
harmful for mixed claims.

**Decision: `rerank_enabled` stays `false` by default.** The stage remains in
the codebase behind the config flag — in an architecture with a large shared
corpus (the situation most RAG systems are in), the same code would likely
pay off; on this workload it costs 1.15s and a mixed-claim regression.

A well-understood negative result: the experiment worked, the feature didn't.
