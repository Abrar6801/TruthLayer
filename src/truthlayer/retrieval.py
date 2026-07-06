"""Retrieval: given a claim, find the most relevant stored evidence chunks.

Similarity metric: cosine similarity (1 - pgvector's `<=>` cosine distance).
Because our embeddings are L2-normalized (embedding.py), cosine similarity
and inner product rank identically here; cosine is used because its fixed
[-1, 1] range makes the relevance threshold meaningful and portable.

The threshold matters more for a fact-checker than for a chatbot: top-k alone
always returns *something*, and a chunk that is merely the least-irrelevant
of an irrelevant set reads like supporting evidence once it lands in the
judge's prompt. Irrelevant "evidence" is worse than no evidence at all —
below-threshold results are dropped and the pipeline reports insufficient
evidence instead.
"""

from __future__ import annotations

import logging
import math

from truthlayer.config import get_settings
from truthlayer.db import RetrievedChunk, query_nearest
from truthlayer.embedding import embed_text

logger = logging.getLogger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors, in [-1, 1].

    Mirrors what pgvector computes server-side; used by unit tests to verify
    ranking behavior without a database.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector dimensions differ: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_chunks(
    query_embedding: list[float],
    candidates: list[tuple[str, str, list[float]]],
    top_k: int,
    threshold: float,
) -> list[RetrievedChunk]:
    """Rank (chunk_text, source_url, embedding) candidates against a query.

    Pure in-memory equivalent of the pgvector query: score by cosine
    similarity, drop everything below `threshold`, return the best `top_k`
    in descending similarity order. Exists so ranking logic is unit-testable
    with fake embeddings, independent of the real database.
    """
    scored = [
        RetrievedChunk(
            chunk_text=text,
            source_url=url,
            similarity=cosine_similarity(query_embedding, embedding),
            claim_query="",
        )
        for text, url, embedding in candidates
    ]
    relevant = [chunk for chunk in scored if chunk.similarity >= threshold]
    relevant.sort(key=lambda chunk: chunk.similarity, reverse=True)
    return relevant[:top_k]


def retrieve_evidence(
    claim: str,
    top_k: int | None = None,
    threshold: float | None = None,
) -> list[RetrievedChunk]:
    """Embed the claim and return the most relevant stored evidence chunks.

    Uses the same embedding model as ingestion (a hard requirement — vectors
    from different models live in different spaces and their similarities are
    meaningless). Results below the similarity threshold are dropped rather
    than padded out to k.
    """
    settings = get_settings()
    k = top_k if top_k is not None else settings.retrieval_top_k
    min_similarity = threshold if threshold is not None else settings.similarity_threshold

    query_embedding = embed_text(claim)
    chunks = query_nearest(query_embedding, top_k=k, min_similarity=min_similarity)
    logger.info(
        "Retrieved %d chunks above similarity threshold %.2f (top-k=%d)",
        len(chunks),
        min_similarity,
        k,
    )
    return chunks
