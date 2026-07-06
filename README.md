# TruthLayer

An agentic RAG fact-checker. Given a claim, TruthLayer searches the web for
evidence, retrieves the most relevant chunks with pgvector similarity search,
and asks Claude for a structured verdict — **true / false / mixed /
unverifiable** — with citations back to sources.

Currently at **Phase 1**: a linear pipeline (search → fetch → chunk → embed →
retrieve → judge) with no orchestration framework yet.

## Setup

Requires Python 3.11+ and a Supabase project (free tier is fine).

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. Install dependencies (pinned) and the package itself
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .

# 3. Configure secrets
copy .env.example .env        # then fill in real values — .env is gitignored
# Keys needed: ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, TAVILY_API_KEY

# 4. Apply the database migration
# Open the Supabase dashboard → SQL Editor → paste and run migrations/001_init.sql

# 5. Install the git hooks (formatting, linting, secrets scanning)
pre-commit install
```

## Usage

```bash
python -m truthlayer "The Great Wall of China is visible from space with the naked eye"
```

The pipeline logs each stage (searching, fetching, embedding, retrieving,
judging) and prints the verdict, confidence, rationale, and supporting source
URLs. If no relevant evidence is found it reports *insufficient evidence*
rather than guessing.

## Development

```bash
pytest              # tests are fully mocked; no API keys or network needed
ruff check .        # lint
black .             # format
mypy                # type-check
```

## Project layout

```
src/truthlayer/
  config.py      # all env var access lives here, nowhere else
  db.py          # Supabase client wrapper (insert chunks, nearest-neighbor query)
  search.py      # Tavily web search + page fetching + HTML→text extraction
  chunking.py    # recursive text splitting
  embedding.py   # local sentence-transformers embeddings (batched)
  ingest.py      # search results → chunks → embeddings → database
  retrieval.py   # claim → top-k relevant chunks with similarity threshold
  verdict.py     # Claude judge: structured, cited, injection-resistant verdict
  cli.py         # end-to-end command-line entry point
migrations/      # SQL migrations for Supabase (run manually in SQL Editor)
tests/           # pytest suite, all external calls mocked
```

## Security notes

- `.env` is gitignored from the first commit; `pre-commit` runs
  `detect-secrets` on every commit.
- The Supabase `service_role` key is **server-side only** — it bypasses Row
  Level Security and must never reach client-facing code or logs.
- All text scraped from the web is treated as **untrusted data**: it is tagged
  `untrusted_web` at ingestion, delimited inside XML tags in the judge prompt,
  and Claude is explicitly instructed to ignore any instructions embedded in it.
