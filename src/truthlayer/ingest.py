"""Evidence ingestion: search results → clean text → chunks → embeddings → DB.

Wires together search (Task 1.3), chunking + embedding (Task 1.4), and
storage (Task 1.2). The total number of chunks stored per query is capped so
a single request can never fill the database unboundedly.

Phase 2 addition: the graph fans out over sub-claims, so `ingest_for_query`
takes an explicit search query plus a set of URLs already ingested during
this request — the same article routinely ranks for several sub-claims of
one compound claim, and re-chunking it would store duplicate evidence that
crowds out genuinely distinct sources at retrieval time.
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


def collect_chunks_for_query(
    query: str,
    skip_urls: set[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """The network phase: search → skip known URLs → extract → chunk.

    Pure I/O + text processing with no shared state, so the graph can safely
    run several of these concurrently (one per sub-claim). Embedding and
    storage happen separately in `embed_and_store` — the local model isn't
    guaranteed thread-safe, and merging first means one big efficient batch.

    Returns:
        (chunks, source_urls, used_urls) — parallel lists plus the distinct
        URLs that produced text.
    """
    settings = get_settings()
    seen = skip_urls or set()
    results = tavily_search(query)
    if not results:
        logger.warning("Search returned no usable results for query: %r", query)
        return [], [], []

    fresh = [r for r in results if r.url not in seen]
    if len(fresh) < len(results):
        logger.info("Skipping %d already-ingested URL(s)", len(results) - len(fresh))
    if not fresh:
        return [], [], []
    logger.info("Fetched %d new pages of candidate evidence for %r", len(fresh), query[:60])

    chunks: list[str] = []
    source_urls: list[str] = []
    used_urls: list[str] = []
    for result in fresh:
        text = _clean_result_text(result)
        if not text.strip():
            continue
        used_urls.append(result.url)
        for chunk in chunk_text(text):
            chunks.append(chunk)
            source_urls.append(result.url)

    # Cap per-query so one request can't fill the database unboundedly.
    if len(chunks) > settings.max_chunks_per_claim:
        logger.info(
            "Capping chunks from %d to %d (max_chunks_per_claim)",
            len(chunks),
            settings.max_chunks_per_claim,
        )
        chunks = chunks[: settings.max_chunks_per_claim]
        source_urls = source_urls[: settings.max_chunks_per_claim]
        used_urls = [url for url in used_urls if url in set(source_urls)]
    return chunks, source_urls, used_urls


def embed_and_store(chunks: list[str], source_urls: list[str], claim_query: str) -> int:
    """The compute/storage phase: embed one merged batch and insert it."""
    if not chunks:
        logger.warning("No readable text extracted for %r", claim_query[:60])
        return 0
    logger.info("Embedding %d chunks", len(chunks))
    embeddings = embed_texts(chunks)
    return insert_chunks(chunks, embeddings, source_urls, claim_query=claim_query)


def ingest_for_query(
    query: str,
    claim_query: str,
    skip_urls: set[str] | None = None,
) -> tuple[int, list[str]]:
    """Search the web for `query` and store embedded evidence chunks.

    Sequential convenience wrapper over collect + embed/store.

    Returns:
        (chunks_stored, newly_ingested_urls)
    """
    chunks, source_urls, used_urls = collect_chunks_for_query(query, skip_urls=skip_urls)
    stored = embed_and_store(chunks, source_urls, claim_query=claim_query)
    return stored, used_urls


def gather_evidence(claim: str) -> int:
    """Single-query ingestion for a claim (the Phase 1 linear-pipeline entry).

    Returns the number of chunks stored (0 if search found nothing usable).
    """
    stored, _ = ingest_for_query(claim, claim_query=claim)
    return stored
