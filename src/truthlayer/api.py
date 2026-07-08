"""FastAPI service wrapping the TruthLayer verification graph.

Auth model: this is **service-to-service** authentication, not user auth.
There are no user accounts or sessions — the only legitimate caller is our
own Next.js server, which proves itself with a single shared secret in the
X-API-Key header. User-facing auth (who is this person?) happens, if ever,
at the frontend layer; this key answers a different question: "is this
request coming from our frontend at all, or from a stranger who found the
URL?" Without it, anyone who discovers the endpoint can run up our
Anthropic/Tavily bill.

Why async matters here specifically: a /verify request spends 10-20+ seconds
almost entirely *waiting* — on Tavily, on page downloads, on Claude. A sync
handler would pin a worker for that whole wait, so a handful of concurrent
users would exhaust the pool while every worker sits idle on I/O. The graph
itself is synchronous code, so we push it onto a worker thread with
asyncio.to_thread and the event loop stays free to accept other requests.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from truthlayer.config import ConfigError, get_settings

logger = logging.getLogger(__name__)

#: Same bound the CLI enforces; validated by Pydantic before any logic runs.
MAX_CLAIM_LENGTH = 1000


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Fail fast at startup: bad config should kill the process, not requests."""
    try:
        settings = get_settings()
    except ConfigError as exc:
        logger.error("%s", exc)
        raise
    if not settings.truthlayer_api_key:
        raise ConfigError(
            "TRUTHLAYER_API_KEY is not set. The API refuses to start without "
            "its own auth key — an open /verify endpoint is an open wallet."
        )
    logger.info("TruthLayer API starting (CORS origins: %s)", settings.allowed_origins)
    yield


class VerifyRequest(BaseModel):
    """Request body for /verify — validated before touching any business logic."""

    claim: str = Field(
        min_length=3,
        max_length=MAX_CLAIM_LENGTH,
        description="The factual claim to verify.",
        examples=["The Great Wall of China is visible from space with the naked eye."],
    )


class VerifyResponse(BaseModel):
    """Structured verdict returned by /verify."""

    claim: str
    verdict: str = Field(description="true | false | mixed | unverifiable")
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    sources: list[str]
    sub_claims: list[str]
    low_confidence: bool = Field(
        description="True when the verdict shipped below the confidence threshold "
        "after exhausting retries — evidence may be incomplete."
    )
    retries: int
    served_from_cache: bool = Field(
        default=False,
        description="True when a semantically near-identical claim was verified "
        "recently and this verdict was served from the cache.",
    )


class HealthResponse(BaseModel):
    """Liveness signal."""

    status: str = "ok"


async def _require_api_key(request: Request) -> None:
    """Service-to-service auth: constant-time comparison of X-API-Key."""
    provided = request.headers.get("X-API-Key", "")
    expected = get_settings().truthlayer_api_key
    # compare_digest resists timing attacks; never log either value.
    if not (provided and expected and secrets.compare_digest(provided, expected)):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def create_app() -> FastAPI:
    """Build the FastAPI app (factory so tests can construct it fresh).

    The rate limiter is created per-app (not module-level) so every app
    instance gets isolated limit state — a module-level limiter would
    accumulate a duplicate limit registration on every factory call.
    """
    settings = get_settings()
    limiter = Limiter(key_func=get_remote_address)
    app = FastAPI(
        title="TruthLayer",
        description="Agentic RAG fact-checker: claim in, cited verdict out.",
        version="0.2.0",
        lifespan=_lifespan,
    )
    app.state.limiter = limiter
    # slowapi's handler signature is (Request, RateLimitExceeded); Starlette
    # types the registry against plain Exception, hence the cast.
    app.add_exception_handler(
        RateLimitExceeded,
        cast(Callable[[Request, Exception], Response], _rate_limit_exceeded_handler),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback server-side with a correlation id; the client
        # gets the id and nothing else — no stack traces, paths, or exception
        # text ever cross the API boundary.
        error_id = uuid.uuid4().hex[:12]
        logger.exception("Unhandled error [%s] on %s", error_id, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error (ref {error_id})"},
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/verify", response_model=VerifyResponse, dependencies=[Depends(_require_api_key)])
    @limiter.limit(settings.verify_rate_limit)
    async def verify(request: Request, body: VerifyRequest) -> VerifyResponse:
        # Import here so the app can boot (and /health respond) without the
        # heavyweight graph/model imports.
        import truthlayer.cache
        import truthlayer.graph

        claim = body.claim.strip()
        if not claim:
            raise HTTPException(status_code=422, detail="Claim must not be blank")

        # Semantic cache sits BEHIND validation (a cached claim is still user
        # input on the way in) and in front of the expensive pipeline.
        cached = await asyncio.to_thread(truthlayer.cache.check_cache, claim)
        if cached is not None:
            return VerifyResponse(**{**cached, "served_from_cache": True})

        # The graph is sync (httpx sync + local embedding model); run it on a
        # worker thread so this endpoint doesn't block the event loop.
        state = await asyncio.to_thread(truthlayer.graph.verify_claim, claim)
        verdict = state.get("verdict")
        if verdict is None:
            logger.error("Graph produced no verdict; errors: %s", state.get("errors"))
            raise HTTPException(status_code=502, detail="Verification pipeline failed")

        response = VerifyResponse(
            claim=claim,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            rationale=verdict.rationale,
            sources=verdict.supporting_sources,
            sub_claims=state.get("sub_claims", [claim]),
            low_confidence=state.get("low_confidence", False),
            retries=state.get("retry_count", 0),
        )
        await asyncio.to_thread(
            truthlayer.cache.store_verdict,
            claim,
            response.model_dump(exclude={"served_from_cache"}),
        )
        return response

    return app
