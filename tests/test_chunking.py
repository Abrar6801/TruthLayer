"""Tests for the chunking step."""

from __future__ import annotations

from truthlayer.chunking import chunk_text


def test_short_text_single_chunk() -> None:
    text = "A short paragraph that fits comfortably in one chunk."
    assert chunk_text(text, chunk_size=200, chunk_overlap=20) == [text]


def test_long_text_respects_chunk_size() -> None:
    text = " ".join(f"Sentence number {i} adds unique content." for i in range(100))
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=40)
    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)


def test_consecutive_chunks_overlap() -> None:
    text = " ".join(f"word{i}" for i in range(200))
    chunks = chunk_text(text, chunk_size=150, chunk_overlap=50)
    # The tail of chunk N should reappear at the head of chunk N+1 so facts
    # straddling a boundary survive in at least one chunk.
    tail_words = chunks[0].split()[-3:]
    assert all(word in chunks[1] for word in tail_words)


def test_whitespace_only_input_yields_nothing() -> None:
    assert chunk_text("   \n\n   ", chunk_size=100, chunk_overlap=10) == []


def test_prefers_paragraph_boundaries() -> None:
    para_a = "First paragraph about topic A. " * 3
    para_b = "Second paragraph about topic B. " * 3
    chunks = chunk_text(f"{para_a.strip()}\n\n{para_b.strip()}", chunk_size=120, chunk_overlap=0)
    # Each paragraph fits in a chunk on its own, so the splitter should break
    # at the blank line rather than mid-sentence.
    assert any("topic A" in chunk and "topic B" not in chunk for chunk in chunks)
