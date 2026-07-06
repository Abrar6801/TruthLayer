"""Evidence ingestion: search results → clean text → chunks → embeddings → DB.

Wires together search (Task 1.3), chunking + embedding (Task 1.4), and
storage (Task 1.2). The total number of chunks stored per claim is capped so
a single query can never fill the database unboundedly.
"""

from __future__ import annotations

import logging

from truthlayer.chunking import chunk_text
from truthlayer.config import get_settings
from truthlayer.db import insert_chunks
from truthlayer.embedding import embed_texts
from truthlayer.search import SearchResult, extract_text, tavily_search

logger = logging.getLogger(__name__)


def _clean_result_text(result: SearchResult) -> str:
    """Return readable text for a search result.

    Tavily's raw_content is usually already text; if it looks like HTML,
    run it through the extractor.
    """
    content = result.raw_content
    if "<html" in content[:500].lower() or "<body" in content[:2000].lower():
        return extract_text(content)
    return content


def gather_evidence(claim: str) -> int:
    """Search the web for a claim and store embedded evidence chunks.

    Pipeline: web search → clean text per page → chunk → cap total chunks →
    embed in batches → insert into evidence_chunks.

    Returns:
        The number of chunks stored (0 if search found nothing usable).
    """
    settings = get_settings()
    results = tavily_search(claim)
    if not results:
        logger.warning("Search returned no usable results for claim: %r", claim)
        return 0
    logger.info("Fetched %d pages of candidate evidence", len(results))

    chunks: list[str] = []
    source_urls: list[str] = []
    for result in results:
        text = _clean_result_text(result)
        if not text.strip():
            continue
        for chunk in chunk_text(text):
            chunks.append(chunk)
            source_urls.append(result.url)

    if not chunks:
        logger.warning("No readable text extracted from any search result")
        return 0

    # Cap per-claim storage so one query can't fill the database unboundedly.
    if len(chunks) > settings.max_chunks_per_claim:
        logger.info(
            "Capping chunks from %d to %d (max_chunks_per_claim)",
            len(chunks),
            settings.max_chunks_per_claim,
        )
        chunks = chunks[: settings.max_chunks_per_claim]
        source_urls = source_urls[: settings.max_chunks_per_claim]

    logger.info("Embedding %d chunks", len(chunks))
    embeddings = embed_texts(chunks)
    return insert_chunks(chunks, embeddings, source_urls, claim_query=claim)
