"""Tests for ranking logic with fixed fake embeddings — no database needed."""

from __future__ import annotations

import pytest

from truthlayer.db import RetrievedChunk
from truthlayer.retrieval import cosine_similarity, rank_chunks, reciprocal_rank_fusion


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


# --- hybrid retrieval: reciprocal rank fusion ---


def _rc(text: str, url: str = "https://s.example", sim: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(chunk_text=text, source_url=url, similarity=sim, claim_query="c")


def test_rrf_agreement_beats_single_list_rank_one() -> None:
    """A chunk found by both searches outranks a chunk that tops only one."""
    both = _rc("in both lists")
    vector_only = _rc("vector's favorite")
    keyword_only = _rc("keyword's favorite")
    fused = reciprocal_rank_fusion(
        [[vector_only, both], [keyword_only, both]],
        top_k=3,
    )
    assert fused[0].chunk_text == "in both lists"


def test_rrf_preserves_first_list_chunk_object_for_duplicates() -> None:
    """The vector leg's object (with its cosine similarity) survives fusion."""
    vector_version = _rc("same text", sim=0.83)
    keyword_version = _rc("same text", sim=17.2)  # ts_rank scale, incomparable
    fused = reciprocal_rank_fusion([[vector_version], [keyword_version]], top_k=1)
    assert fused[0].similarity == 0.83


def test_rrf_respects_top_k_and_orders_by_fused_score() -> None:
    a, b, c = _rc("a"), _rc("b"), _rc("c")
    fused = reciprocal_rank_fusion([[a, b, c], [b, a, c]], top_k=2)
    assert len(fused) == 2
    # a: 1/61 + 1/62 == b: 1/62 + 1/61 -> tie; c strictly lower either way.
    assert {ch.chunk_text for ch in fused} == {"a", "b"}


def test_rrf_empty_lists_return_empty() -> None:
    assert reciprocal_rank_fusion([[], []], top_k=5) == []
