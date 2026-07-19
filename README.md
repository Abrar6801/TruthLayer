# TruthLayer

**An agentic RAG fact-checker.** Paste a claim; TruthLayer decomposes it into
checkable sub-claims, searches the web for evidence, retrieves the most
relevant passages with vector search, and has Claude render a verdict —
**true / false / mixed / unverifiable** — with citations, a per-source
stance (supports / disputes / context), a confidence score, and an automatic
broadened-search retry when confidence is low.

**Live demo:** <https://truthlayer-azure.vercel.app> — the example chips
answer from the semantic cache in under a second; a fresh claim takes
10–30s (plus a cold start if the backend has been idle).

Built solo as a learning project for the agentic-RAG stack (LangGraph,
pgvector, FastAPI, Next.js, LangSmith), with the explicit goal of being able
to defend every design decision in an interview — see
[LEARNING_NOTES.md](LEARNING_NOTES.md) for the running per-task log of
concepts, decisions, and tradeoffs.

## Architecture

```
Browser ── Next.js (Vercel) ── /api/verify route handler   [visitor rate limit,
   │                                │                        holds service key]
   │                                ▼
   │                        FastAPI /verify (Cloud Run, Docker) [API-key auth,
   │                                │                          rate limit, CORS]
   │                                ▼
   │                        LangGraph state machine
   │        ┌──────────────────────────────────────────────┐
   │        │ decompose ─▶ search_and_embed ─▶ retrieve ─▶ judge
   │        │     ▲            (per sub-claim,      │        │
   │        │     │             URL-deduped)        │   low confidence?
   │        │     └──────────── broaden ◀───────────┼────────┘
   │        │                   (max 2 retries,     │
   │        │                    LLM call budget)   ▼
   │        └──────────────────────────────── verdict + citations
   │
   └── every stage: Tavily search · trafilatura extraction · OpenAI hosted
       embeddings · Postgres+pgvector (HNSW, cosine) · Claude judge with
       injection-hardened prompts and strict JSON output
```

## Tech stack — and why each piece

| Piece | Choice | Why |
|---|---|---|
| Orchestration | LangGraph | The confidence-gated retry loop is a declared, testable graph edge instead of a hand-rolled while-loop; typed shared state; per-node tracing |
| Vector store | Postgres + pgvector | One database for everything; HNSW index stays accurate under continuous inserts (vs IVFFlat's build-time clustering) |
| Embeddings | OpenAI text-embedding-3-small, truncated to 384 dims | Started local (sentence-transformers) for free/offline dev; swapped to hosted after Render's 512MB free tier couldn't hold torch + a loaded model without hanging `/verify` |
| Judge LLM | Claude (Sonnet) | Strong grounded-judgment behavior; strict JSON + Pydantic validation gives a hard parse-or-fail boundary |
| API | FastAPI | Async endpoint keeps the event loop free during 10-30s I/O waits; typed request/response models; free OpenAPI docs |
| Frontend | Next.js 14 App Router | Server-side route handler keeps the service key out of the browser bundle; Vercel free tier |
| Evals/tracing | LangSmith + custom harness | Per-node traces for debugging the retry loop; the eval harness measures accuracy, latency, and cost per verdict |

## Results (measured, not vibes)

On a 40-claim hand-labeled eval set (13 true / 13 false / 7 mixed / 7
unverifiable, mixed difficulty — small enough to be honest about: treat every
number as ±):

| Metric | Value | Report |
|---|---|---|
| Verdict accuracy | **77.5%** (26/26 on true/false; mixed & unverifiable bleed into "false") | [`eval/baseline_report.md`](eval/baseline_report.md) |
| Latency after parallelizing sub-claim search | **p50 10.5s (−30%), p95 15.3s (−39%)**; the search stage itself −57% | [`eval/latency_report.md`](eval/latency_report.md) |
| Cross-encoder reranking | **Honest negative: 77.5% → 75.0%, +1.15s** — chunk-level analysis of why; shipped off by default | [`eval/reranking_report.md`](eval/reranking_report.md) |
| Semantic cache hit | **~15ms vs 14.9s p50 (~1000×)**, saving ≈$0.0092 + 1-4 searches per hit; threshold re-measured to 0.94 after the embedding-model swap (a tuned similarity threshold is a per-model constant) | [`tests/test_cache.py`](tests/test_cache.py) |
| Cost per verdict | **≈ $0.0092** (avg 2.02 LLM calls, ~3.4K in / 230 out tokens) | baseline report |
| Rationale faithfulness (LLM-as-judge, n=8) | 8/8 | baseline report |
| Confidence calibration | **Overconfident by ~16 points** (Brier 0.195, ECE 0.165): 34/40 verdicts state ≥0.9 confidence but only 79% of those are right | [`eval/calibration_report.md`](eval/calibration_report.md) |
| Failure taxonomy | **All 9 baseline misses are judge labeling errors, zero retrieval failures** — compound claims mislabeled FALSE instead of MIXED, unfalsifiable claims FALSE instead of UNVERIFIABLE; drove a targeted judge-prompt fix | [`eval/error_analysis.md`](eval/error_analysis.md) |
| Taxonomy fix (directional, n=12) | **3/12 → 7/12 on the targeted subset**: 4/5 MIXED failures recovered, 0/4 UNVERIFIABLE — a real half-win that redirects the next iteration to the label-policy question | [`eval/taxonomy_fix_directional.md`](eval/taxonomy_fix_directional.md) |
| Calibrated confidence | Displayed confidence is now **remapped through the measured reliability curve** (stated 0.95 → shown ~0.79); raw value preserved in `raw_confidence` for refitting | [`src/truthlayer/confidence.py`](src/truthlayer/confidence.py) |

The most interesting single result is the reranking negative: the
cross-encoder promoted text with maximal lexical overlap ("Japanese Everest
expeditions" for a claim about "Everest… Japan") over evidentially useful
chunks, flipping a correct MIXED verdict to FALSE — a concrete example of
relevance-to-text ≠ usefulness-for-judgment.

## Post-launch engineering

Everything below was added after the production launch, driven by the
measurements above rather than intuition:

- **Error analysis → targeted fix:** reading all 9 failures showed accuracy
  is judge-bound, not retrieval-bound, so the fix was ordered
  verdict-boundary decision rules + contrast few-shots in the judge prompt —
  not a retrieval rebuild (gain unmeasured until the next eval run).
- **Source credibility + recency:** every evidence chunk now carries a
  system-assigned domain tier (high / medium / low — scraped content can't
  influence it) and its publish date; the judge weighs both when sources
  conflict and discounts verdicts resting only on social/forum evidence.
- **Per-source stance:** the judge labels each citation supports / disputes /
  context, and the UI says "3 support, 1 disputes" instead of hiding the
  losing side of a disagreement.
- **Hybrid retrieval (shipped disabled):** pgvector + Postgres full-text
  fused with Reciprocal Rank Fusion, behind `HYBRID_ENABLED=false` until an
  eval run proves it — the reranking negative earned that policy.
- **Shareable verdicts:** every verdict gets a permalink
  (`/verdict/<id>`) served from the semantic-cache table; near-duplicate
  claims share one canonical URL.
- **CI/CD:** every push runs lint/type/test for backend + frontend; merges
  to main build the image in GitHub Actions and deploy to Cloud Run via
  keyless OIDC (Workload Identity Federation — no service-account key
  exists anywhere).

## Security posture

- Prompt injection is the core threat for a system that ingests arbitrary web
  text: scraped content is tagged untrusted at the type level, XML-delimited
  in every prompt, the judge is instructed to treat it as data, output must
  validate against a strict schema, and cited URLs are filtered against the
  actual evidence set. An adversarial-chunk test exercises this end to end.
- Secrets: env-vars only, single config module, `.env` gitignored from the
  first commit, detect-secrets pre-commit hook, no secrets in Docker layers
  (verified via `docker history`).
- The API refuses to boot without its own auth key; rate limiting exists at
  both the visitor layer (Next.js, per-IP) and the service layer (FastAPI).
- All SQL is parameterized; the DB is addressed by a server-side connection
  string; RLS is enabled default-deny on every table.
- Containers run as a non-root user; `.dockerignore` keeps `.env`, `.git`,
  and tests out of the build context.

## Known limitations (honest list)

- **Evidence quality ceiling:** verdicts are only as good as the top search
  results; SEO spam or thin coverage produces "unverifiable" (by design) but
  sometimes confidently-wrong evidence slips through.
- **The eval set is 40 claims** — big enough to catch regressions, far too
  small for statistically tight accuracy claims. Treat every number as ±.
- **Confidence calibration is coarse**: the displayed confidence is remapped
  through a curve fitted on only 40 claims and on the *previous* judge
  prompt — directionally right (overconfidence is measured, the cap at 0.79
  is evidence-based), but the anchors need refitting after the next full
  eval run.
- **English-only**, and claims about very recent events depend entirely on
  what Tavily surfaces.
- **Free-tier latency:** Cloud Run scale-to-zero adds a ~10–30s cold start
  after idle (masked by the frontend's warmup retry).
- With more time: post-hoc confidence remapping, multilingual support, a
  claim-type classifier in front of the pipeline, and a larger stratified
  eval set.

## Run it locally

```bash
# Backend (needs Docker Desktop)
cp .env.example .env             # fill in ANTHROPIC_API_KEY, TAVILY_API_KEY;
                                 # keep the compose DATABASE_URL as-is
docker compose up --build        # API on :8000 + local pgvector Postgres
curl http://localhost:8000/health

# Frontend
cd frontend
cp .env.local.example .env.local # point at http://localhost:8000 + same service key
npm install && npm run dev       # UI on :3000

# Tests / eval (Python 3.11+, venv)
pip install -r requirements.txt -r requirements-dev.txt && pip install -e .
pytest                           # fully mocked, no keys needed
python eval/run_eval.py --tag mytest --limit 5   # real run (spends API credits)
python eval/score_eval.py eval/results/<file>.json
```

Deployment (Google Cloud Run + Vercel + Supabase): see
[DEPLOYMENT.md](DEPLOYMENT.md).

## Learning log

Every task appended a dated entry to
[LEARNING_NOTES.md](LEARNING_NOTES.md): what was built, the concepts
involved (explained from scratch), and the design tradeoffs. That file is
the honest record of the learning process this project exists for.
