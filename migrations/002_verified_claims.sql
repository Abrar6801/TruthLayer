-- TruthLayer migration 002: semantic verdict cache.
--
-- Stores completed verdicts keyed by the claim's embedding, so a repeat (or
-- near-duplicate) claim can be answered from cache instead of re-running the
-- full search/judge pipeline.
--
-- Run in the Supabase SQL Editor for production; the docker-compose Postgres
-- applies it automatically on a fresh volume (docker compose down -v && up).

create table if not exists verified_claims (
    id              uuid primary key default gen_random_uuid(),
    claim_text      text not null,
    embedding       vector(384) not null,
    -- The full VerifyResponse payload as returned to the client.
    verdict_payload jsonb not null,
    created_at      timestamptz not null default now()
);

create index if not exists verified_claims_embedding_idx
    on verified_claims
    using hnsw (embedding vector_cosine_ops);

-- TTL pruning runs on created_at; index keeps it cheap.
create index if not exists verified_claims_created_at_idx
    on verified_claims (created_at);

-- Default-deny, same reasoning as evidence_chunks: this table is only ever
-- touched server-side; RLS with no policies closes it to any future
-- anon/authenticated key by default.
alter table verified_claims enable row level security;
