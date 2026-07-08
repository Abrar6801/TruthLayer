"""Cross-encoder reranking: the second stage of two-stage retrieval.

Bi-encoder vs cross-encoder, mechanically: the bi-encoder (MiniLM in
embedding.py) encodes claim and chunk *separately* into fixed vectors, and
relevance is just their cosine — nothing about the claim can influence how
the chunk is read. That independence is what makes vector search fast (chunk
vectors are precomputed; query time is one encode + an index lookup), and
also what caps its precision: "the wall is visible from space" and "the wall
is NOT visible from space" embed nearly identically.

The cross-encoder reads claim and chunk *together* through one transformer
pass with full cross-attention, so it can see negation, entity mismatches,
and whether the chunk actually addresses the claim. That costs a full model
forward pass per (claim, chunk) pair — fine for scoring 20 candidates, absurd
for scoring a million stored chunks. Hence two stages: the cheap bi-encoder
casts a wide net (top-20), the expensive cross-encoder picks what the judge
actually reads (top-8).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from truthlayer.config import get_settings
from truthlayer.db import RetrievedChunk

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

_model: CrossEncoder | None = None


def _get_model() -> CrossEncoder:
    """Load the cross-encoder once and cache it (lazy, like the bi-encoder)."""
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder

        settings = get_settings()
        logger.info("Loading reranker model %s ...", settings.rerank_model_name)
        _model = CrossEncoder(settings.rerank_model_name)
    return _model


def rerank(claim: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
    """Re-order candidate chunks by cross-encoder relevance; keep the best top_k.

    The returned chunks keep their original bi-encoder `similarity` values so
    eval reports can show both scores side by side; ordering is by the
    cross-encoder alone.
    """
    if not chunks:
        return []
    model = _get_model()
    scores = model.predict([(claim, chunk.chunk_text) for chunk in chunks])
    ranked = sorted(zip(chunks, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    if ranked:
        logger.info(
            "Reranked %d candidates (cross-encoder scores %.2f .. %.2f), keeping %d",
            len(chunks),
            float(ranked[0][1]),
            float(ranked[-1][1]),
            min(top_k, len(ranked)),
        )
    return [chunk for chunk, _ in ranked[:top_k]]
