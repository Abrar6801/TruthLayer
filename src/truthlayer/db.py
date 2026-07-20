"""Postgres/pgvector access for evidence chunks (psycopg3 + connection pool).

All queries are parameterized — values travel separately from SQL text, which
matters here because chunk_text is arbitrary scraped web text. Nothing in this
module ever interpolates content into a SQL string.

The database is addressed by a single DATABASE_URL:
- local dev / docker-compose: the pgvector Postgres container
- production: Supabase's Postgres connection string (Settings → Database).
  That string is a server-side secret with the same standing as the old
  service_role key — it must never reach client-facing code, logs, or the
  frontend bundle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg import Connection
from psycopg_pool import ConnectionPool

from truthlayer.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


@dataclass(frozen=True)
class RetrievedChunk:
    """An evidence chunk returned by nearest-neighbor search.

    `chunk_text` originates from the open web and is untrusted data — it must
    never be treated as instructions by downstream code. `published_date` is
    ISO `YYYY-MM-DD` when the source page carried one, else None.
    """

    chunk_text: str
    source_url: str
    similarity: float
    claim_query: str
    published_date: str | None = None


def _configure(conn: Connection) -> None:
    """Register the pgvector type adapter on every pooled connection."""
    register_vector(conn)


def get_pool() -> ConnectionPool:
    """Return the shared connection pool, creating it lazily."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=5,
            configure=_configure,
            # Fail fast if the DB is unreachable instead of hanging a request.
            timeout=settings.http_timeout_seconds,
        )
    return _pool


def insert_chunks(
    chunks: list[str],
    embeddings: list[list[float]],
    source_urls: list[str],
    claim_query: str,
    published_dates: list[str | None] | None = None,
) -> int:
    """Insert evidence chunks with their embeddings.

    Args:
        chunks: The chunk texts (untrusted web content).
        embeddings: One embedding vector per chunk, same order.
        source_urls: One source URL per chunk, same order.
        claim_query: The claim/search query these chunks were gathered for.
        published_dates: Optional ISO dates per chunk (None entries allowed);
            omitting the list stores NULL for every chunk.

    Returns:
        The number of rows inserted.

    Raises:
        ValueError: if the parallel lists differ in length.
    """
    if published_dates is None:
        published_dates = [None] * len(chunks)
    if not (len(chunks) == len(embeddings) == len(source_urls) == len(published_dates)):
        raise ValueError(
            f"chunks ({len(chunks)}), embeddings ({len(embeddings)}), "
            f"source_urls ({len(source_urls)}) and published_dates "
            f"({len(published_dates)}) must have the same length"
        )
    if not chunks:
        return 0

    rows = [
        (text, Vector(embedding), url, claim_query, published)
        for text, embedding, url, published in zip(
            chunks, embeddings, source_urls, published_dates, strict=True
        )
    ]
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO evidence_chunks
                (chunk_text, embedding, source_url, claim_query, published_date)
            VALUES (%s, %s, %s, %s, %s)
            """,
            rows,
        )
        inserted = cur.rowcount if cur.rowcount is not None and cur.rowcount > 0 else len(rows)
    logger.info("Inserted %d evidence chunks for claim query %r", inserted, claim_query)
    return inserted


def query_nearest(
    query_embedding: list[float],
    top_k: int,
    min_similarity: float = 0.0,
) -> list[RetrievedChunk]:
    """Return the top_k stored chunks most similar to `query_embedding`.

    Cosine similarity = 1 - (`<=>` cosine distance); higher means closer.
    Results below `min_similarity` are filtered out in SQL.
    """
    with get_pool().connection() as conn:
        result = conn.execute(
            """
            SELECT chunk_text,
                   source_url,
                   1 - (embedding <=> %(q)s) AS similarity,
                   claim_query,
                   published_date
            FROM evidence_chunks
            WHERE 1 - (embedding <=> %(q)s) >= %(min_sim)s
            ORDER BY embedding <=> %(q)s
            LIMIT %(k)s
            """,
            {"q": Vector(query_embedding), "min_sim": min_similarity, "k": top_k},
        ).fetchall()
    return [
        RetrievedChunk(
            chunk_text=row[0],
            source_url=row[1],
            similarity=float(row[2]),
            claim_query=row[3],
            published_date=row[4].isoformat() if row[4] is not None else None,
        )
        for row in result
    ]
