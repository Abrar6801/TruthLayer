"""Central configuration for TruthLayer.

This module is the ONLY place in the codebase that reads environment
variables. Everything else imports `get_settings()` and reads typed fields,
so a missing or misspelled variable fails fast at startup with a clear
message instead of surfacing as a confusing error deep inside the pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, get_args

from dotenv import load_dotenv

#: Valid output_config.effort values accepted by the Claude API.
LLMEffort = Literal["low", "medium", "high", "xhigh", "max"]
_VALID_LLM_EFFORTS = get_args(LLMEffort)

#: Environment variables that must be present and non-empty.
REQUIRED_VARS = (
    "ANTHROPIC_API_KEY",
    "TAVILY_API_KEY",
    "DATABASE_URL",
)


class ConfigError(RuntimeError):
    """Raised at startup when required environment variables are missing."""


@dataclass(frozen=True)
class Settings:
    """Typed, validated application settings.

    Secrets come from the environment (via .env in development). Tunables
    have sensible defaults and can be overridden with env vars of the same
    (upper-cased) name.
    """

    # --- secrets (required) ---
    anthropic_api_key: str
    tavily_api_key: str
    # Postgres connection string. Local dev: the docker-compose pgvector
    # container. Production: Supabase's connection string — a server-side
    # secret that must never reach client code, logs, or the frontend bundle.
    database_url: str

    # --- embedding model, locked in with the DB schema (Task 1.2) ---
    # Changing the model means changing the vector(384) column and re-embedding
    # everything, so these two values must move together.
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # --- LLM ---
    anthropic_model: str = "claude-sonnet-5"
    # Claude Sonnet 5 (and the rest of the 4.7+/Fable-5 generation) removed
    # sampling parameters (temperature/top_p/top_k) entirely — sending one is a
    # 400, not a no-op. Repeatable judge output now comes from the strict JSON
    # schema (verdict.py) plus low effort, not from a temperature knob.
    llm_effort: LLMEffort = "low"
    # Hard ceiling on Claude calls a single /verify request can trigger across
    # decomposition, judging, broadening, and parse retries combined. The graph
    # tracks llm_calls_used in state and every node checks this before calling.
    max_llm_calls_per_claim: int = 8

    # --- agentic graph (Phase 2) ---
    # Verdicts below this confidence trigger a broadened-search retry.
    confidence_threshold: float = 0.6
    # Hard cap on broaden-and-retry loops; after this the verdict ships with a
    # low_confidence flag instead of looping forever.
    max_verdict_retries: int = 2

    # --- pipeline tunables ---
    search_max_results: int = 5
    chunk_size: int = 800
    chunk_overlap: int = 150
    max_chunks_per_claim: int = 60
    retrieval_top_k: int = 8
    # Cosine similarity below this is treated as "no relevant evidence".
    similarity_threshold: float = 0.35

    # --- reranking (Phase 4.2) ---
    # Two-stage retrieval: pgvector fetches `retrieval_candidates` (wide),
    # a cross-encoder reranks (claim, chunk) pairs, and only the top
    # `retrieval_top_k` reach the judge. Toggleable for A/B eval runs.
    rerank_enabled: bool = False
    rerank_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    retrieval_candidates: int = 20

    # --- concurrency (Phase 4.3) ---
    # Max simultaneous sub-claim search/fetch cycles. Bounded so a 4-sub-claim
    # decomposition can't fire unbounded Tavily calls into free-tier limits.
    search_concurrency: int = 3

    # --- network hygiene ---
    http_timeout_seconds: float = 15.0
    http_max_retries: int = 3

    # --- API service (Phase 2) ---
    # Our own service-to-service key: the Next.js server (not the browser)
    # presents this to FastAPI. Distinct from the Anthropic key. Empty means
    # "not configured" — the API refuses to serve /verify without it.
    truthlayer_api_key: str = ""
    # Comma-separated CORS allowlist; only the frontend's origin belongs here.
    allowed_origins: str = "http://localhost:3000"
    # slowapi rate limit for /verify (per client IP).
    verify_rate_limit: str = "10/minute"


def _read_optional_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _read_optional_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load, validate, and cache settings from the environment.

    Raises:
        ConfigError: if any required variable is missing or empty, listing
            every missing variable at once (not just the first one).
    """
    load_dotenv()  # no-op if .env doesn't exist (e.g. in CI)

    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        raise ConfigError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in real values."
        )

    llm_effort = os.environ.get("LLM_EFFORT", "low")
    if llm_effort not in _VALID_LLM_EFFORTS:
        raise ConfigError(
            f"LLM_EFFORT={llm_effort!r} is not valid; must be one of {_VALID_LLM_EFFORTS}"
        )

    defaults = Settings(anthropic_api_key="", tavily_api_key="", database_url="")
    return Settings(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        tavily_api_key=os.environ["TAVILY_API_KEY"],
        database_url=os.environ["DATABASE_URL"],
        embedding_model_name=os.environ.get("EMBEDDING_MODEL_NAME", defaults.embedding_model_name),
        embedding_dim=_read_optional_int("EMBEDDING_DIM", defaults.embedding_dim),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", defaults.anthropic_model),
        llm_effort=llm_effort,  # type: ignore[arg-type]  # validated against _VALID_LLM_EFFORTS above
        max_llm_calls_per_claim=_read_optional_int(
            "MAX_LLM_CALLS_PER_CLAIM", defaults.max_llm_calls_per_claim
        ),
        confidence_threshold=_read_optional_float(
            "CONFIDENCE_THRESHOLD", defaults.confidence_threshold
        ),
        max_verdict_retries=_read_optional_int("MAX_VERDICT_RETRIES", defaults.max_verdict_retries),
        search_max_results=_read_optional_int("SEARCH_MAX_RESULTS", defaults.search_max_results),
        chunk_size=_read_optional_int("CHUNK_SIZE", defaults.chunk_size),
        chunk_overlap=_read_optional_int("CHUNK_OVERLAP", defaults.chunk_overlap),
        max_chunks_per_claim=_read_optional_int(
            "MAX_CHUNKS_PER_CLAIM", defaults.max_chunks_per_claim
        ),
        retrieval_top_k=_read_optional_int("RETRIEVAL_TOP_K", defaults.retrieval_top_k),
        similarity_threshold=_read_optional_float(
            "SIMILARITY_THRESHOLD", defaults.similarity_threshold
        ),
        rerank_enabled=os.environ.get("RERANK_ENABLED", "").lower() in ("1", "true", "yes"),
        rerank_model_name=os.environ.get("RERANK_MODEL_NAME", defaults.rerank_model_name),
        retrieval_candidates=_read_optional_int(
            "RETRIEVAL_CANDIDATES", defaults.retrieval_candidates
        ),
        search_concurrency=_read_optional_int("SEARCH_CONCURRENCY", defaults.search_concurrency),
        http_timeout_seconds=_read_optional_float(
            "HTTP_TIMEOUT_SECONDS", defaults.http_timeout_seconds
        ),
        http_max_retries=_read_optional_int("HTTP_MAX_RETRIES", defaults.http_max_retries),
        truthlayer_api_key=os.environ.get("TRUTHLAYER_API_KEY", defaults.truthlayer_api_key),
        allowed_origins=os.environ.get("ALLOWED_ORIGINS", defaults.allowed_origins),
        verify_rate_limit=os.environ.get("VERIFY_RATE_LIMIT", defaults.verify_rate_limit),
    )
