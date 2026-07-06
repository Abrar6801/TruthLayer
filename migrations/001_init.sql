-- TruthLayer migration 001: evidence storage with pgvector.
--
-- Embedding model locked in for this schema:
--   sentence-transformers/all-MiniLM-L6-v2  →  384 dimensions
-- The vector(384) column below and the embedding code (src/truthlayer/embedding.py)
-- must always agree; changing models means a new migration + re-embedding.
--
-- Run this in the Supabase dashboard → SQL Editor.

-- Enable the pgvector extension (ships with Supabase, just needs enabling).
create extension if not exists vector;

create table if not exists evidence_chunks (
    id          uuid primary key default gen_random_uuid(),
    source_url  text not null,
    chunk_text  text not null,
    embedding   vector(384) not null,
    -- The search query / claim this chunk was fetched for, so stale evidence
    -- can be traced back and cleaned up per claim.
    claim_query text not null,
    created_at  timestamptz not null default now()
);

-- HNSW index for approximate nearest-neighbor search with cosine distance.
-- Chosen over IVFFlat because HNSW builds incrementally and stays accurate as
-- rows are inserted, while IVFFlat's clusters are computed once at index
-- creation and degrade as the table grows/changes — a bad fit for a table
-- that starts empty and grows with every claim checked.
create index if not exists evidence_chunks_embedding_idx
    on evidence_chunks
    using hnsw (embedding vector_cosine_ops);

-- Default-deny: enable Row Level Security with NO policies. This app only
-- accesses the table through the service_role key (which bypasses RLS), so
-- this costs nothing today — it exists purely so that if an anon or
-- authenticated Supabase key ever gets pointed at this database in the
-- future, it can read/write nothing by default instead of everything.
alter table evidence_chunks enable row level security;

-- Nearest-neighbor search exposed as an RPC so application code never builds
-- SQL strings. `<=>` is pgvector's cosine *distance* operator; similarity is
-- 1 - distance, so a higher returned `similarity` means a closer match.
create or replace function match_evidence_chunks(
    query_embedding vector(384),
    match_count     int,
    min_similarity  float default 0.0
)
returns table (
    id          uuid,
    source_url  text,
    chunk_text  text,
    claim_query text,
    similarity  float
)
language sql
stable
as $$
    select
        ec.id,
        ec.source_url,
        ec.chunk_text,
        ec.claim_query,
        1 - (ec.embedding <=> query_embedding) as similarity
    from evidence_chunks ec
    where 1 - (ec.embedding <=> query_embedding) >= min_similarity
    order by ec.embedding <=> query_embedding
    limit match_count;
$$;
