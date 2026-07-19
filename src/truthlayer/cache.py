"""Semantic verdict cache.

Exact-match caching keys on the literal string, so "Is the earth flat?" and
"is the Earth flat" are different entries and the hit rate on natural
language is near zero. Semantic caching keys on the *embedding*: any claim
whose vector sits within a similarity threshold of a stored claim reuses its
verdict. That threshold is the whole game:

- Too loose, and "the earth is round" serves its TRUE verdict to "the earth
  is flat" — negation pairs sit misleadingly close in embedding space
  because they share almost all their tokens and topic; the one word that
  flips the meaning barely moves the vector. For a fact-checker this is the
  catastrophic failure mode.
- Too strict, and only byte-identical claims hit, which is just exact-match
  with extra steps.

We use 0.97 cosine (config), validated by near-miss probes with the real
embedding model in tests/test_cache.py. TTL: verdicts expire after 7 days
(config) because facts drift — "the current officeholder is X" can silently
become false; an expired entry just re-runs the pipeline.

The same pattern applies to any high-volume LLM product: embedding-keyed
caches convert repeat/near-repeat traffic from full-pipeline cost to one
embedding call. The threshold-vs-semantics tension (especially negation) is
identical everywhere it's used.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pgvector import Vector

from truthlayer.config import get_settings
from truthlayer.db import get_pool
from truthlayer.embedding import embed_text

logger = logging.getLogger(__name__)


def check_cache(claim: str) -> dict[str, Any] | None:
    """Return a cached verdict payload for a near-duplicate claim, or None.

    Callers must pass only *validated* claim text — the cache sits behind
    input validation, never in front of it.
    """
    settings = get_settings()
    if not settings.cache_enabled:
        return None
    embedding = embed_text(claim)
    with get_pool().connection() as conn:
        row = conn.execute(
            """
            SELECT verdict_payload,
                   claim_text,
                   1 - (embedding <=> %(q)s) AS similarity,
                   id
            FROM verified_claims
            WHERE 1 - (embedding <=> %(q)s) >= %(threshold)s
              AND created_at > now() - make_interval(hours => %(ttl)s)
            ORDER BY embedding <=> %(q)s
            LIMIT 1
            """,
            {
                "q": Vector(embedding),
                "threshold": settings.cache_similarity_threshold,
                "ttl": settings.cache_ttl_hours,
            },
        ).fetchone()
    if row is None:
        return None
    payload, cached_claim, similarity = row[0], row[1], float(row[2])
    logger.info(
        "Semantic cache HIT (similarity %.3f) — %r matched cached %r",
        similarity,
        claim[:60],
        cached_claim[:60],
    )
    result: dict[str, Any] = payload if isinstance(payload, dict) else json.loads(payload)
    # The permalink points at the ORIGINAL row, so near-duplicate claims all
    # share one canonical verdict URL.
    result["verdict_id"] = str(row[3])
    return result


def store_verdict(claim: str, payload: dict[str, Any]) -> str | None:
    """Store a completed verdict; returns the new row's id (the permalink id).

    Failures are logged and swallowed — a broken cache write must never fail
    the request that produced a perfectly good verdict — hence `None` on any
    failure: the verdict simply ships without a shareable link.
    """
    settings = get_settings()
    if not settings.cache_enabled:
        return None
    try:
        embedding = embed_text(claim)
        with get_pool().connection() as conn:
            row = conn.execute(
                """
                INSERT INTO verified_claims (claim_text, embedding, verdict_payload)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (claim, Vector(embedding), json.dumps(payload)),
            ).fetchone()
        return str(row[0]) if row else None
    except Exception as exc:
        logger.warning("Cache write failed (non-fatal): %s", exc)
        return None


def get_verdict(verdict_id: str) -> dict[str, Any] | None:
    """Fetch a stored verdict payload by permalink id, or None if unknown.

    No TTL filter: a shared link should keep working past the cache TTL —
    freshness matters when *serving new verdicts*, not when reading a
    historical one (the page shows its verdict as-of its creation).
    """
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT verdict_payload, id FROM verified_claims WHERE id = %s",
            (verdict_id,),
        ).fetchone()
    if row is None:
        return None
    payload = row[0]
    result: dict[str, Any] = payload if isinstance(payload, dict) else json.loads(payload)
    result["verdict_id"] = str(row[1])
    return result
