"""Evidence gathering: web search via Tavily and page fetching/extraction.

Everything this module returns came from the open internet. Every result is
tagged `source="untrusted_web"` so downstream code (and downstream *prompts*)
can never confuse scraped text with trusted instructions. This matters for
this project specifically: a fact-checker deliberately ingests arbitrary web
pages, which is exactly the delivery mechanism for prompt injection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import httpx
import trafilatura
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from truthlayer.config import get_settings

logger = logging.getLogger(__name__)

_TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# One slow or broken site must not hang the pipeline: every network call has
# an explicit timeout and a small, bounded number of retries with backoff.
_retry_on_network_errors = retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


@dataclass(frozen=True)
class SearchResult:
    """A candidate evidence page returned by web search.

    `raw_content` is arbitrary internet text — untrusted data, never
    instructions. The `source` tag makes that explicit in the data structure.
    """

    url: str
    title: str
    raw_content: str
    source: Literal["untrusted_web"] = field(default="untrusted_web")


@_retry_on_network_errors
def _post_tavily(payload: dict[str, object], timeout: float) -> dict[str, object]:
    """POST to the Tavily search API, raising on HTTP errors so tenacity retries."""
    settings = get_settings()
    response = httpx.post(
        _TAVILY_SEARCH_URL,
        json=payload,
        headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
        timeout=timeout,
    )
    response.raise_for_status()
    data: dict[str, object] = response.json()
    return data


def tavily_search(query: str, max_results: int | None = None) -> list[SearchResult]:
    """Search the web for evidence pages relevant to `query`.

    Asks Tavily to include the raw page content so most results don't need a
    separate fetch. Results with no content are dropped — a URL with nothing
    readable behind it is not evidence.
    """
    settings = get_settings()
    limit = max_results if max_results is not None else settings.search_max_results
    logger.info("Searching web for: %r (max %d results)", query, limit)

    data = _post_tavily(
        {
            "query": query,
            "max_results": limit,
            "include_raw_content": True,
        },
        timeout=settings.http_timeout_seconds,
    )

    results: list[SearchResult] = []
    raw_results = data.get("results", [])
    if isinstance(raw_results, list):
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            content = str(item.get("raw_content") or item.get("content") or "")
            if url and content.strip():
                results.append(
                    SearchResult(url=url, title=str(item.get("title") or ""), raw_content=content)
                )
    logger.info("Search returned %d usable results", len(results))
    return results


@_retry_on_network_errors
def fetch_page(url: str) -> str:
    """Fetch a page's raw HTML with a hard timeout and bounded retries.

    Used as a fallback when a search result comes back without raw content.
    """
    settings = get_settings()
    response = httpx.get(
        url,
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "TruthLayer/0.1 (fact-checking research tool)"},
    )
    response.raise_for_status()
    return response.text


def extract_text(raw_html: str) -> str:
    """Extract clean, readable text from raw HTML.

    Strips navigation, ads, scripts, and boilerplate via trafilatura. Returns
    an empty string when nothing readable can be extracted, so callers can
    simply skip the page.
    """
    if not raw_html.strip():
        return ""
    extracted = trafilatura.extract(raw_html, include_comments=False, include_tables=False)
    return extracted or ""
