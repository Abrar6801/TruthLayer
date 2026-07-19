-- TruthLayer migration 004: evidence publish dates.
--
-- Stores the publish date Tavily reports for a page (when it reports one),
-- so the judge can weigh recency: for claims about current facts
-- (officeholders, records, prices), a 2019 article and a 2026 article are
-- not equal evidence. Nullable because most non-news pages have no reliable
-- date — absence of a date is itself information the judge sees.
--
-- Run in the Supabase SQL Editor (or via psycopg) for production; the
-- docker-compose Postgres applies it automatically on a fresh volume.

alter table evidence_chunks
    add column if not exists published_date date;
