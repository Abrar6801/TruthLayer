"""Local embeddings via sentence-transformers.

The model here MUST stay in sync with the vector(384) column created in
migrations/001_init.sql — the model name and dimension are locked in together
via config.py. Local embeddings are free and offline, which is ideal for
development; swapping to a hosted provider later only requires replacing the
body of `embed_texts` (the rest of the pipeline sees plain lists of floats).

Embeddings are L2-normalized so that cosine similarity comparisons (both in
pgvector and in local ranking code) are consistent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from truthlayer.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Load the sentence-transformers model once and cache it.

    The import happens lazily so that unit tests (which mock embedding) and
    tooling never pay the multi-second torch import / model load cost.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        logger.info("Loading embedding model %s ...", settings.embedding_model_name)
        _model = SentenceTransformer(settings.embedding_model_name)
    return _model


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embed a list of texts in batches.

    Batching matters for throughput: the model processes a batch in one
    forward pass, so embedding 60 chunks in batches of 32 takes ~2 model
    calls instead of 60.

    Returns one L2-normalized vector (length = settings.embedding_dim) per
    input text, in the same order.
    """
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in vectors]


def embed_text(text: str) -> list[float]:
    """Embed a single text (e.g. the claim itself at retrieval time)."""
    return embed_texts([text])[0]
