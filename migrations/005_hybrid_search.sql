-- TruthLayer migration 005: full-text search column for hybrid retrieval.
--
-- Pure vector search is weakest exactly where fact-checking is hardest:
-- names, numbers, dates, and exact phrases ("1921 Nobel Prize") embed into
-- fuzzy neighborhoods, while lexical search matches them exactly. This adds
-- Postgres full-text search (BM25-adjacent ts_rank) alongside pgvector so
-- retrieval.py can fuse both rankings (Reciprocal Rank Fusion) behind the
-- HYBRID_ENABLED flag — no new infrastructure, same database.
--
-- STORED generated column: computed once per insert (chunks are
-- write-once), so reads pay nothing. The GIN index makes @@ queries
-- sublinear.
--
-- Run in the Supabase SQL Editor (or via psycopg) for production; the
-- docker-compose Postgres applies it automatically on a fresh volume.

alter table evidence_chunks
    add column if not exists chunk_tsv tsvector
    generated always as (to_tsvector('english', chunk_text)) stored;

create index if not exists evidence_chunks_tsv_idx
    on evidence_chunks using gin (chunk_tsv);
