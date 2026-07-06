"""Tests for ranking logic with fixed fake embeddings — no database needed."""

from __future__ import annotations

import pytest

from truthlayer.retrieval import cosine_similarity, rank_chunks


def test_cosine_similarity_identical_vectors() -> None:
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="dimensions differ"):
        cosine_similarity([1.0, 2.0], [1.0])


def test_cosine_similarity_zero_vector() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_rank_chunks_orders_by_similarity() -> None:
    query = [1.0, 0.0]
    candidates = [
        ("far", "https://far.example", [0.0, 1.0]),  # sim 0.0
        ("close", "https://close.example", [1.0, 0.1]),  # sim ~0.995
        ("mid", "https://mid.example", [1.0, 1.0]),  # sim ~0.707
    ]
    ranked = rank_chunks(query, candidates, top_k=3, threshold=-1.0)
    assert [chunk.chunk_text for chunk in ranked] == ["close", "mid", "far"]
    assert ranked[0].similarity > ranked[1].similarity > ranked[2].similarity


def test_rank_chunks_threshold_drops_irrelevant() -> None:
    query = [1.0, 0.0]
    candidates = [
        ("relevant", "https://a.example", [1.0, 0.0]),
        ("irrelevant", "https://b.example", [0.0, 1.0]),
    ]
    ranked = rank_chunks(query, candidates, top_k=5, threshold=0.5)
    # Below-threshold chunks are dropped, NOT padded out to k — irrelevant
    # "evidence" would read as support once it lands in the judge prompt.
    assert [chunk.chunk_text for chunk in ranked] == ["relevant"]


def test_rank_chunks_respects_top_k() -> None:
    query = [1.0, 0.0]
    candidates = [(f"c{i}", f"https://{i}.example", [1.0, float(i) / 10]) for i in range(10)]
    ranked = rank_chunks(query, candidates, top_k=3, threshold=0.0)
    assert len(ranked) == 3
