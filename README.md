# TruthLayer

**An agentic RAG fact-checker.** Paste a claim; TruthLayer decomposes it into
checkable sub-claims, searches the web for evidence, retrieves the most
relevant passages with vector search, and has Claude render a verdict —
**true / false / mixed / unverifiable** — with citations, a confidence score,
and an automatic broadened-search retry when confidence is low.

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
   │                        FastAPI /verify (Render, Docker)  [API-key auth,
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
   └── every stage: Tavily search · trafilatura extraction · MiniLM local
       embeddings · Postgres+pgvector (HNSW, cosine) · Claude judge with
       injection-hardened prompts and strict JSON output
```

## Tech stack — and why each piece

| Piece | Choice | Why |
|---|---|---|
| Orchestration | LangGraph | The confidence-gated retry loop is a declared, testable graph edge instead of a hand-rolled while-loop; typed shared state; per-node tracing |
| Vector store | Postgres + pgvector | One database for everything; HNSW index stays accurate under continuous inserts (vs IVFFlat's build-time clustering) |
| Embeddings | sentence-transformers MiniLM-L6 (local) | Free, offline, no rate limits for dev; swap point is one function |
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
| Semantic cache hit | **~15ms vs 14.9s p50 (~1000×)**, saving ≈$0.0092 + 1-4 searches per hit; 0.97 threshold validated against negation pairs with the real model | [`tests/test_cache.py`](tests/test_cache.py) |
| Cost per verdict | **≈ $0.0092** (avg 2.02 LLM calls, ~3.4K in / 230 out tokens) | baseline report |
| Rationale faithfulness (LLM-as-judge, n=8) | 8/8 | baseline report |

The most interesting single result is the reranking negative: the
cross-encoder promoted text with maximal lexical overlap ("Japanese Everest
expeditions" for a claim about "Everest… Japan") over evidentially useful
chunks, flipping a correct MIXED verdict to FALSE — a concrete example of
relevance-to-text ≠ usefulness-for-judgment.

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
- **Confidence is self-reported** by the judge, not calibrated probability.
- **English-only**, and claims about very recent events depend entirely on
  what Tavily surfaces.
- **Free-tier latency:** cold starts add ~1 min on Render after idle.
- With more time: calibrated confidence, multilingual support, a claim-type
  classifier in front of the pipeline, and a larger stratified eval set.

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

Deployment (Render + Vercel + Supabase): see [DEPLOYMENT.md](DEPLOYMENT.md).

## Learning log

Every task appended a dated entry to
[LEARNING_NOTES.md](LEARNING_NOTES.md): what was built, the concepts
involved (explained from scratch), and the design tradeoffs. That file is
the honest record of the learning process this project exists for.
