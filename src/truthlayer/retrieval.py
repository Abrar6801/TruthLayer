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

from truthlayer.config import get_settings
from truthlayer.db import RetrievedChunk, query_nearest
from truthlayer.embedding import embed_text

logger = logging.getLogger(__name__)


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
    chunks = query_nearest(embed_text(claim), top_k=k, min_similarity=min_similarity)
    logger.info(
        "Retrieved %d chunks above similarity threshold %.2f (top-k=%d)",
        len(chunks),
        min_similarity,
        k,
    )
    return chunks
