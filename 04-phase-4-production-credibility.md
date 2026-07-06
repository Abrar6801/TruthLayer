# Phase 4 — production credibility (measure, improve, launch)

Goal of this phase: turn a working project into a defensible one. Every task
here exists to generate a specific, quantified claim for interviews and your
resume — a measured quality improvement, a measured latency improvement, and
evidence of real usage. Phases 1-3 built the thing; Phase 4 proves it.

Prerequisite: Phase 3 complete, including the eval dataset (3.1), scoring
script (3.3), and live deployment (3.6). Several tasks below rerun the eval
before and after a change — that before/after delta is the whole point, so
don't skip the "before" measurement.

A note on sequencing: 4.1 → 4.2 must run in order (4.2's eval delta needs
4.1's baseline). 4.3 and 4.4 can happen in either order after that. 4.5
(launch) should come after 4.3 so real visitors don't hit 30-second waits.
4.6 and 4.7 close it out.

---

## Task 4.1 — Baseline snapshot

**Concepts you'll learn:** benchmarking discipline, why you freeze a baseline
before optimizing, cost-per-request accounting for LLM systems.

```
<task>
Before changing anything, capture a complete baseline of TruthLayer's current
quality, latency, and cost so every Phase 4 improvement has a real
before/after comparison.
</task>
<requirements>
- Run the full eval set from Task 3.1 through the scoring script from Task
  3.3 and save the results as eval/baseline_report.md with a date — this
  file never gets overwritten, later runs are saved alongside it.
- Using LangSmith traces from those eval runs, record: p50 and p95
  end-to-end latency, per-stage latency breakdown (decompose, search/embed,
  retrieve, judge), average number of LLM calls per claim, and average token
  usage per claim.
- Compute cost per verdict in dollars from the token counts and current
  Claude API pricing, and record it in the baseline report.
- Add a short make target or script (e.g. make eval) so rerunning this exact
  measurement later is one command, not a manual process.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
why the baseline must be frozen before any optimization work starts, and what
p50 vs p95 latency each tell you that the other doesn't.
```

---

## Task 4.2 — Reranking, measured

**Concepts you'll learn:** cross-encoder rerankers vs bi-encoder retrieval,
two-stage retrieval architecture, reading a confusion matrix delta, honest
reporting when an experiment doesn't help.

```
<task>
Add a reranking stage after pgvector retrieval and measure exactly what it
does to verdict accuracy against the Task 4.1 baseline.
</task>
<requirements>
- After pgvector returns its top-k candidates, rerank them with a local
  cross-encoder model (e.g. a sentence-transformers cross-encoder such as
  ms-marco-MiniLM) scoring each (claim, chunk) pair, and pass only the top
  reranked subset to the judge. Retrieve a wider k from pgvector than
  before (e.g. 20) so the reranker has candidates to actually reorder.
- Make reranking toggleable via config so the with/without comparison can be
  rerun any time.
- Rerun the full eval with reranking on. Save eval/reranking_report.md with:
  accuracy before vs after, the confusion-matrix delta, 2-3 specific claims
  whose verdicts changed and why (pull the retrieved chunks for those claims
  and show what the reranker did differently), and the latency cost the
  reranking stage added.
- If accuracy does NOT improve, that's a legitimate finding — report it
  honestly with your analysis of why, rather than tweaking until the number
  moves. A well-analyzed negative result is a better interview story than a
  suspicious positive one.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
the bi-encoder vs cross-encoder distinction mechanically — why can't we just
use the cross-encoder for everything, and why is the bi-encoder alone weaker
at final-stage relevance? This "how does it actually work" level is exactly
what I'm practicing for interviews.
```

---

## Task 4.3 — Parallel sub-claim retrieval, measured

**Concepts you'll learn:** asyncio concurrency for I/O-bound fan-out,
concurrency limits and semaphores, LangGraph parallel execution, verifying
speedups with traces instead of vibes.

```
<task>
Run sub-claim search/embed/retrieve cycles concurrently instead of
sequentially, and measure the latency improvement against the Task 4.1
baseline.
</task>
<requirements>
- Convert the per-sub-claim fan-out in the search_and_embed node to run
  concurrently (asyncio.gather or LangGraph's parallel branch execution —
  pick one and explain the choice).
- Add a concurrency limit (semaphore) so a claim that decomposes into many
  sub-claims can't fire unbounded simultaneous Tavily/embedding calls —
  respect the rate limits of the free tiers we're on.
- Confirm the total-LLM-calls-per-request cap from CLAUDE.md still holds
  under the concurrent path.
- Rerun the eval and save eval/latency_report.md: p50/p95 before vs after,
  per-stage breakdown showing where the time went, and confirmation that
  verdict accuracy did not change (concurrency should affect speed, not
  results — if accuracy moved, something is wrong, likely shared state
  between concurrent branches; investigate before proceeding).
- Include one LangSmith trace screenshot or link in the report showing the
  parallel spans side by side.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
why this workload benefits from asyncio concurrency specifically (I/O-bound
vs CPU-bound), what the semaphore protects against, and why accuracy changing
under concurrency would signal a bug.
```

---

## Task 4.4 — Semantic caching

**Concepts you'll learn:** semantic caching vs exact-match caching, cache
keys from embeddings, similarity thresholds for cache hits, cache
invalidation tradeoffs, idempotency.

```
<task>
Add a semantic cache so a claim that has already been verified (or a
near-duplicate of one) returns the stored verdict instead of re-running the
full pipeline.
</task>
<requirements>
- A verified_claims table (new migration) storing the claim text, its
  embedding, the full verdict payload, and a timestamp — with RLS enabled
  like the existing table.
- On each /verify request, embed the incoming claim and check for a stored
  claim above a high similarity threshold (start ~0.95 and document the
  choice) before running the pipeline. On a hit, return the cached verdict
  with a served_from_cache flag in the response.
- A TTL or timestamp check so stale verdicts don't live forever — facts
  change; a claim verified 6 months ago about a "current" officeholder may
  no longer be right. Document what TTL you chose and the reasoning.
- The threshold decision matters: too loose and "the earth is round" serves
  the cached verdict for "the earth is flat" (catastrophic for a
  fact-checker), too strict and the cache never hits. Write 3-4 test cases
  probing near-miss pairs like negations and entity swaps to validate the
  threshold — negation pairs are exactly where embedding similarity is
  misleadingly high.
- Measure and report: cache hit latency vs full-pipeline latency, and the
  cost saved per cache hit in dollars.
</requirements>
<security_and_best_practices>
- The cache must never bypass input validation — a cached claim is still
  user input on the way in.
</security_and_best_practices>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
semantic vs exact-match caching, why negations break naive embedding
similarity, and how this same pattern applies to any high-volume LLM product
— this is a strong general interview topic, flag it as such in
LEARNING_NOTES.md.
```

---

## Task 4.5 — Streaming results + launch readiness

**Concepts you'll learn:** server-sent events (SSE), streaming from
LangGraph, perceived vs actual latency, basic product analytics.

```
<task>
Stream pipeline progress to the frontend as it happens instead of one
20-second spinner, add lightweight analytics, and make the app ready for
strangers to use.
</task>
<requirements>
- Backend: an SSE (or streaming-response) variant of /verify that emits
  events as the graph progresses — sub-claims identified, evidence found per
  sub-claim (source domains), verdict forming — using LangGraph's streaming
  support.
- Frontend: replace the spinner with progressive rendering of those events,
  so the user watches the fact-check assemble. Keep the non-streaming
  endpoint working for the eval script.
- Add privacy-respecting analytics (e.g. a lightweight self-hostable or
  free-tier option like Plausible/Umami — not full user tracking): page
  views, claims submitted, cache hit rate, error rate. No PII stored beyond
  the claim text itself.
- A feedback affordance on each verdict ("was this verdict right?"
  thumbs-up/down stored to the database) — this becomes the raw material for
  Task 4.6.
- A final pre-launch pass through SECURITY-CHECKLIST.md, including the
  manual trick-input tests against the live deployment, since strangers are
  about to use this.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
perceived vs actual latency and why streaming changes the former without
touching the latter, and how SSE differs from websockets and from regular
HTTP responses.
```

---

## Task 4.6 — Launch and learn from real traffic

This task is mostly YOU, not Claude Code — it's here so it doesn't get
skipped, because it's the single most direct answer to the "no real users or
traffic" critique.

**Do manually:**
- Share the live link where relevant people actually are: r/artificial or
  similar subreddits, LinkedIn (you're actively visible there for the job
  search anyway), your Cal State network, and any AI/ML Discord communities
  you're in. A short honest post — "I built an open-source fact-checker to
  learn agentic RAG, here's what it does and what it gets wrong" — outperforms
  a salesy one.
- Let it run for 1-2 weeks. Check analytics and the feedback table every few
  days. Read the actual claims people submit.
- Keep notes on what surprises you — the gap between what you built for and
  what people actually type is the story.

**Then, with Claude Code:**

```
<task>
Analyze real usage data collected since launch and implement ONE improvement
that the data directly motivates.
</task>
<requirements>
- A short analysis script over the stored claims and feedback: claim volume,
  cache hit rate, verdict distribution, thumbs-up/down rates, and a manual
  review pass categorizing what kinds of inputs people actually submitted
  (factual claims vs opinions vs questions vs junk).
- Based on what the data shows, implement exactly one improvement. Likely
  candidate if the data matches the common pattern: a cheap claim-type
  classifier (single Haiku-class LLM call or even a heuristic) that routes
  non-checkable inputs — opinions, questions, gibberish — to an immediate
  "this isn't a checkable factual claim" response instead of burning the
  full pipeline on them. But let the data pick; if something else is the
  clear pain point, do that instead and say why.
- Write eval/usage_report.md: N claims from M unique visitors over the
  period, what the data showed, what was changed in response, and the
  measured effect (e.g. % of requests short-circuited, cost saved).
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. This
report is the "real users" proof — write it with concrete numbers.
```

---

## Task 4.7 — Resilience + the final story

**Concepts you'll learn:** graceful degradation, health checks that check
dependencies, translating engineering work into resume bullets.

```
<task>
Add graceful degradation for upstream outages, then update all project
documentation to lead with Phase 4's measured results.
</task>
<requirements>
- Graceful degradation: if Tavily is down or rate-limited, return a clear
  "search unavailable, try again shortly" response; if the Claude API is
  down, likewise — never a raw 500 or a hung request. Extend /health to
  optionally report dependency status (a shallow check, not a full pipeline
  run).
- A simple integration test simulating each upstream failure (mocked) and
  asserting the degraded response is returned within the timeout.
- Rewrite the README's results section to lead with the Phase 4 numbers:
  baseline vs final accuracy (with the reranking delta), baseline vs final
  p95 latency (with the parallelization delta), cache hit rate and cost per
  verdict, and the real-usage numbers from Task 4.6.
- Draft 3-4 resume bullet points from this project following my
  resume-rules conventions — each one anchored on a measured number from
  Phase 4, not a technology list. Also draft the 60-second interview
  walkthrough: problem, architecture, one hard decision, measured results.
- Final LEARNING_NOTES.md retrospective: the full arc from Phase 1 to Phase
  4, and an honest list of what I'd confidently defend in an interview vs
  what I'd need to review first.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. This
is the last task — the deliverable isn't just code, it's the story I'll
actually tell with this project.
```

---

## What deliberately isn't here

No auth/user accounts, no browser extension, no multi-model support, no
fine-tuning, no mobile app. Each would add weeks and make the repo bigger
without making any interview claim stronger. The goal of Phase 4 is a small
number of quantified, defensible claims — not a longer feature list. If
you're tempted to add one of these later, first ask what resume bullet it
produces that the current set doesn't.
