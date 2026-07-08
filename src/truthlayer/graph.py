"""The TruthLayer agentic graph (LangGraph).

Phase 1 was a straight chain of function calls: any step's output went to
exactly one next step, and a weak verdict was simply the final answer. A
state machine buys two things that a chain can't express cleanly:

1. **Branching on results** — after the judge runs, a conditional edge
   inspects the verdict's confidence and either ends, or loops back through
   a broadened search. In a chain that's an ad-hoc while-loop with tangled
   bookkeeping; in a graph it's a declared edge you can see, test, and trace.
2. **Shared typed state** — every node reads and writes one TruthLayerState,
   so the data flowing through the pipeline is inspectable at every step
   (and LangSmith can trace it per node in Phase 3).

The retry edge is protecting against a specific failure mode: the first
search happened to fetch weak or off-topic pages, so the judge, correctly,
has low confidence. Retrying with the *same* query would fetch the same
pages; the broaden node rewrites the query first. The hard retry cap
(settings.max_verdict_retries) and the request-wide LLM call budget
(settings.max_llm_calls_per_claim) are what stand between "agentic loop"
and "infinite loop with a credit card attached".

Graph shape:

    START -> decompose -> search_and_embed -> retrieve -> judge
                ^                                           |
                |            (confidence low, retries left) |
                +--------------- broaden <------------------+
                                                            |
                                       (confident, or caps hit) -> END
"""

from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from truthlayer.config import get_settings
from truthlayer.db import RetrievedChunk
from truthlayer.decompose import broaden_query, decompose_claim
from truthlayer.ingest import ingest_for_query
from truthlayer.retrieval import retrieve_evidence
from truthlayer.verdict import DEFAULT_JUDGE_ATTEMPTS, Verdict, VerdictParseError, generate_verdict

logger = logging.getLogger(__name__)


class TruthLayerState(TypedDict, total=False):
    """Everything that flows through the graph for one /verify request."""

    claim: str  # original, validated user claim
    sub_claims: list[str]
    search_queries: list[str]  # queries for the next search pass
    ingested_urls: list[str]  # dedup across sub-claims and retries
    chunks_stored: int
    evidence: list[RetrievedChunk]
    verdict: Verdict | None
    confidence: float
    low_confidence: bool  # final verdict shipped below the threshold
    retry_count: int
    llm_calls_used: int  # counted against settings.max_llm_calls_per_claim
    errors: list[str]


def _budget_left(state: TruthLayerState) -> int:
    return get_settings().max_llm_calls_per_claim - state.get("llm_calls_used", 0)


def _node_decompose(state: TruthLayerState) -> dict[str, Any]:
    """Split the claim into sub-claims; they become the first search queries."""
    claim = state["claim"]
    if _budget_left(state) < 1:
        return {"sub_claims": [claim], "search_queries": [claim]}
    try:
        sub_claims = decompose_claim(claim)
    except Exception as exc:  # a failed decomposition must not sink the request
        logger.warning("Decompose failed (%s); treating claim as atomic", exc)
        return {
            "sub_claims": [claim],
            "search_queries": [claim],
            "llm_calls_used": state.get("llm_calls_used", 0) + 1,
            "errors": state.get("errors", []) + [f"decompose: {exc}"],
        }
    return {
        "sub_claims": sub_claims,
        "search_queries": sub_claims,
        "llm_calls_used": state.get("llm_calls_used", 0) + 1,
    }


def _node_search_and_embed(state: TruthLayerState) -> dict[str, Any]:
    """Run search → chunk → embed → store for each pending query, deduped by URL."""
    seen = set(state.get("ingested_urls", []))
    stored_total = state.get("chunks_stored", 0)
    errors = list(state.get("errors", []))
    new_urls: list[str] = []
    for query in state.get("search_queries", []):
        try:
            stored, urls = ingest_for_query(query, claim_query=state["claim"], skip_urls=seen)
        except Exception as exc:  # one dead query must not sink the others
            logger.warning("Search/ingest failed for %r: %s", query, exc)
            errors.append(f"search {query!r}: {exc}")
            continue
        stored_total += stored
        new_urls.extend(urls)
        seen.update(urls)
    return {
        "chunks_stored": stored_total,
        "ingested_urls": state.get("ingested_urls", []) + new_urls,
        "errors": errors,
    }


def _node_retrieve(state: TruthLayerState) -> dict[str, Any]:
    """Retrieve evidence for the ORIGINAL claim across everything stored.

    Retrieval deliberately runs against the original claim rather than
    per-sub-claim: the judge needs the combined picture (a compound claim can
    be half-true), and chunks fetched for one sub-claim often bear on another.
    """
    evidence = retrieve_evidence(state["claim"])
    return {"evidence": evidence}


def _node_judge(state: TruthLayerState) -> dict[str, Any]:
    """Judge the claim against the evidence; record confidence for routing."""
    evidence = state.get("evidence", [])
    if not evidence:
        # No relevant evidence — don't burn an LLM call asking Claude to say
        # so. Low confidence routes this into a broadened retry if any remain.
        verdict = Verdict(
            verdict="unverifiable",
            confidence=0.1,
            rationale="No relevant evidence was retrieved for this claim.",
            supporting_sources=[],
        )
        return {"verdict": verdict, "confidence": verdict.confidence}

    attempts = min(DEFAULT_JUDGE_ATTEMPTS, _budget_left(state))
    if attempts < 1:
        logger.warning("LLM call budget exhausted before judging; returning unverifiable")
        verdict = Verdict(
            verdict="unverifiable",
            confidence=0.1,
            rationale="The request's LLM call budget was exhausted before a verdict.",
            supporting_sources=[],
        )
        return {"verdict": verdict, "confidence": verdict.confidence}

    try:
        verdict = generate_verdict(state["claim"], evidence, max_attempts=attempts)
    except VerdictParseError as exc:
        logger.error("Judge produced unparseable output: %s", exc)
        verdict = Verdict(
            verdict="unverifiable",
            confidence=0.1,
            rationale="The judge model returned unparseable output.",
            supporting_sources=[],
        )
        return {
            "verdict": verdict,
            "confidence": verdict.confidence,
            "llm_calls_used": state.get("llm_calls_used", 0) + attempts,
            "errors": state.get("errors", []) + [f"judge: {exc}"],
        }
    return {
        "verdict": verdict,
        "confidence": verdict.confidence,
        # Conservative accounting: a parse retry may or may not have happened;
        # counting the full allowance keeps the budget a true upper bound.
        "llm_calls_used": state.get("llm_calls_used", 0) + attempts,
    }


def _node_broaden(state: TruthLayerState) -> dict[str, Any]:
    """Rewrite the search query for the retry pass (never repeat a search)."""
    retry_no = state.get("retry_count", 0) + 1
    logger.info(
        "Retry %d triggered: confidence %.2f below threshold %.2f",
        retry_no,
        state.get("confidence", 0.0),
        get_settings().confidence_threshold,
    )
    previous = list(state.get("sub_claims", [])) + list(state.get("search_queries", []))
    if _budget_left(state) < 1:
        # Budget gone — fall back to the raw claim (still deduped by URL).
        return {"search_queries": [state["claim"]], "retry_count": retry_no}
    try:
        query = broaden_query(state["claim"], previous)
    except Exception as exc:
        logger.warning("Broaden failed (%s); reusing raw claim as query", exc)
        return {
            "search_queries": [state["claim"]],
            "retry_count": retry_no,
            "llm_calls_used": state.get("llm_calls_used", 0) + 1,
            "errors": state.get("errors", []) + [f"broaden: {exc}"],
        }
    return {
        "search_queries": [query],
        "retry_count": retry_no,
        "llm_calls_used": state.get("llm_calls_used", 0) + 1,
    }


def _route_after_judge(state: TruthLayerState) -> Literal["broaden", "finalize"]:
    """Confidence-gated retry edge with hard caps (the anti-infinite-loop gate)."""
    settings = get_settings()
    confident = state.get("confidence", 0.0) >= settings.confidence_threshold
    retries_left = state.get("retry_count", 0) < settings.max_verdict_retries
    if not confident and retries_left and _budget_left(state) >= 1:
        return "broaden"
    return "finalize"


def _node_finalize(state: TruthLayerState) -> dict[str, Any]:
    """Flag verdicts that ship below the confidence threshold."""
    low = state.get("confidence", 0.0) < get_settings().confidence_threshold
    if low:
        logger.warning(
            "Final verdict is low confidence (%.2f) after %d retries — evidence may be incomplete",
            state.get("confidence", 0.0),
            state.get("retry_count", 0),
        )
    return {"low_confidence": low}


def build_graph() -> CompiledStateGraph[TruthLayerState, None, TruthLayerState, TruthLayerState]:
    """Compile the TruthLayer verification graph."""
    graph = StateGraph(TruthLayerState)
    graph.add_node("decompose", _node_decompose)
    graph.add_node("search_and_embed", _node_search_and_embed)
    graph.add_node("retrieve", _node_retrieve)
    graph.add_node("judge", _node_judge)
    graph.add_node("broaden", _node_broaden)
    graph.add_node("finalize", _node_finalize)

    graph.add_edge(START, "decompose")
    graph.add_edge("decompose", "search_and_embed")
    graph.add_edge("search_and_embed", "retrieve")
    graph.add_edge("retrieve", "judge")
    graph.add_conditional_edges(
        "judge", _route_after_judge, {"broaden": "broaden", "finalize": "finalize"}
    )
    graph.add_edge("broaden", "search_and_embed")
    graph.add_edge("finalize", END)
    return graph.compile()


_compiled: CompiledStateGraph[TruthLayerState, None, TruthLayerState, TruthLayerState] | None = None


def get_graph() -> CompiledStateGraph[TruthLayerState, None, TruthLayerState, TruthLayerState]:
    """Return the compiled graph, building it once."""
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def verify_claim(claim: str) -> TruthLayerState:
    """Run the full agentic pipeline for one claim and return the final state."""
    initial: TruthLayerState = {
        "claim": claim,
        "retry_count": 0,
        "llm_calls_used": 0,
        "errors": [],
        "ingested_urls": [],
        "chunks_stored": 0,
    }
    final = cast(TruthLayerState, get_graph().invoke(initial))
    return final
