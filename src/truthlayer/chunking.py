"""Text chunking for evidence pages.

Chunk size / overlap tradeoff, in short: chunks must be small enough that a
retrieved chunk is *about one thing* (a 5,000-character chunk matches a query
weakly on average even when one paragraph inside it matches strongly), but
large enough to carry the context the judge needs to interpret a sentence.
Overlap exists so a fact straddling a chunk boundary still appears intact in
at least one chunk.

Defaults (config.py): 800 characters per chunk with 150 overlap — roughly a
few paragraphs, a reasonable fit for the ~256-token effective input window of
the all-MiniLM-L6-v2 embedding model.
"""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from truthlayer.config import get_settings


def chunk_text(
    text: str, chunk_size: int | None = None, chunk_overlap: int | None = None
) -> list[str]:
    """Split page text into overlapping chunks for embedding.

    Uses a recursive splitter that prefers to break on paragraph boundaries,
    then sentences, then words — only falling back to a hard character cut
    when nothing better fits. Whitespace-only chunks are dropped.

    Args:
        text: Clean page text (already stripped of HTML).
        chunk_size: Max characters per chunk; defaults to settings.chunk_size.
        chunk_overlap: Characters shared between consecutive chunks; defaults
            to settings.chunk_overlap.
    """
    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size if chunk_size is not None else settings.chunk_size,
        chunk_overlap=chunk_overlap if chunk_overlap is not None else settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]
