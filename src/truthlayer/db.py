"""Supabase database access for evidence chunks.

All queries go through the Supabase client library / the RPC defined in
migrations/001_init.sql — application code never interpolates values into SQL
strings, which matters here because chunk_text is arbitrary scraped web text.

This module authenticates with the service_role key, which bypasses Row Level
Security. That is acceptable ONLY because this code runs server-side. The
service_role key must never be used in any client-facing code path (frontend,
browser bundle, logs, error messages) later in the project — anything
client-reachable gets the anon key and explicit RLS policies instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from supabase import Client, create_client

from truthlayer.config import get_settings

logger = logging.getLogger(__name__)

_TABLE = "evidence_chunks"
_MATCH_RPC = "match_evidence_chunks"

_client: Client | None = None


@dataclass(frozen=True)
class RetrievedChunk:
    """An evidence chunk returned by nearest-neighbor search.

    `chunk_text` originates from the open web and is untrusted data — it must
    never be treated as instructions by downstream code.
    """

    chunk_text: str
    source_url: str
    similarity: float
    claim_query: str


def get_client() -> Client:
    """Return a cached Supabase client authenticated with the service_role key."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


def insert_chunks(
    chunks: list[str],
    embeddings: list[list[float]],
    source_urls: list[str],
    claim_query: str,
) -> int:
    """Insert evidence chunks with their embeddings.

    Args:
        chunks: The chunk texts (untrusted web content).
        embeddings: One embedding vector per chunk, same order.
        source_urls: One source URL per chunk, same order.
        claim_query: The claim/search query these chunks were gathered for.

    Returns:
        The number of rows inserted.

    Raises:
        ValueError: if the three parallel lists differ in length.
    """
    if not (len(chunks) == len(embeddings) == len(source_urls)):
        raise ValueError(
            f"chunks ({len(chunks)}), embeddings ({len(embeddings)}) and "
            f"source_urls ({len(source_urls)}) must have the same length"
        )
    if not chunks:
        return 0

    rows: list[dict[str, Any]] = [
        {
            "chunk_text": text,
            "embedding": embedding,
            "source_url": url,
            "claim_query": claim_query,
        }
        for text, embedding, url in zip(chunks, embeddings, source_urls, strict=True)
    ]
    response = get_client().table(_TABLE).insert(rows).execute()
    inserted = len(response.data or [])
    logger.info("Inserted %d evidence chunks for claim query %r", inserted, claim_query)
    return inserted


def query_nearest(
    query_embedding: list[float],
    top_k: int,
    min_similarity: float = 0.0,
) -> list[RetrievedChunk]:
    """Return the top_k stored chunks most similar to `query_embedding`.

    Uses the match_evidence_chunks RPC (cosine similarity, higher = closer).
    Results below `min_similarity` are filtered out server-side.
    """
    response = (
        get_client()
        .rpc(
            _MATCH_RPC,
            {
                "query_embedding": query_embedding,
                "match_count": top_k,
                "min_similarity": min_similarity,
            },
        )
        .execute()
    )
    raw_rows = response.data or []
    if not isinstance(raw_rows, list):
        raise TypeError(f"Unexpected RPC response shape: {type(raw_rows).__name__}")
    chunks: list[RetrievedChunk] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        similarity = row["similarity"]
        if not isinstance(similarity, int | float):
            raise TypeError(f"Non-numeric similarity in RPC response: {similarity!r}")
        chunks.append(
            RetrievedChunk(
                chunk_text=str(row["chunk_text"]),
                source_url=str(row["source_url"]),
                similarity=float(similarity),
                claim_query=str(row["claim_query"]),
            )
        )
    return chunks
