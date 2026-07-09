"""Hosted embeddings via the OpenAI API.

Originally this called a local sentence-transformers model — free, offline,
zero rate limits, ideal for development on a full-size machine. It moved to
a hosted provider after production deployment: Render's free tier gives the
container 512MB RAM, and importing torch + loading a transformer model
inside that budget was consistently exhausting it (observed as the /verify*
endpoints hanging or 502ing while /health, which never touches the model,
stayed instant). This is exactly the swap CLAUDE.md flagged as a "one-line
change" when the project was scaffolded — that design paid off here.

`dimensions=384` on the request truncates OpenAI's native 1536-dim output
via Matryoshka representation learning, matching the vector(384) column
already defined in migrations/001_init.sql — so this swap needed zero schema
changes. Every call has an explicit timeout and bounded retries per the
project's security baseline for external API calls.
"""

from __future__ import annotations

import logging

from openai import OpenAI

from truthlayer.config import get_settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Return a cached OpenAI client, created lazily."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.http_timeout_seconds,
            max_retries=settings.http_max_retries,
        )
    return _client


def embed_texts(texts: list[str], batch_size: int = 96) -> list[list[float]]:
    """Embed a list of texts in batches via the OpenAI embeddings API.

    Batching matters for throughput and cost: one request embeds up to
    `batch_size` texts, so 60 chunks in batches of 96 is a single API call
    instead of 60. OpenAI's own per-request item limit is far higher than 96;
    this default keeps individual requests small and fast to retry on failure.

    Returns one vector (length = settings.embedding_dim) per input text, in
    the same order the API returns them (OpenAI preserves input order).
    """
    if not texts:
        return []
    settings = get_settings()
    client = _get_client()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(
            model=settings.embedding_model_name,
            input=batch,
            dimensions=settings.embedding_dim,
        )
        vectors.extend(item.embedding for item in response.data)
    return vectors


def embed_text(text: str) -> list[float]:
    """Embed a single text (e.g. the claim itself at retrieval time)."""
    return embed_texts([text])[0]
