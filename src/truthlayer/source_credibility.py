"""Domain-level source credibility tiers.

Why this exists: at judge time every evidence chunk used to look identical —
a Facebook post and a Reuters article carried equal weight, and the error
analysis (eval/error_analysis.md) shows the judge citing facebook.com and
quora.com in real verdicts. This module gives the judge an explicit,
inspectable signal about how much editorial control typically stands behind
a domain.

Deliberately a *tier*, not a truth score: a high-tier source can be wrong
and a forum post can be right. The judge is told to weigh tiers when sources
conflict, never to auto-believe tier-high content — that would just be a
different prompt-injection surface ("trust me, I'm Reuters" says the
attacker's page). Tiering is by registrable domain only, which scraped
content cannot influence.

The lists are a starting point, curated by hand and easy to extend; they are
intentionally in code (reviewable, versioned, testable) rather than config.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

SourceTier = Literal["high", "medium", "low"]

#: Outlets and institutions with strong editorial/scientific review norms.
_HIGH_TRUST_DOMAINS = frozenset(
    {
        "apnews.com",
        "bbc.co.uk",
        "bbc.com",
        "britannica.com",
        "cdc.gov",
        "economist.com",
        "espn.com",
        "ft.com",
        "nasa.gov",
        "nature.com",
        "nejm.org",
        "nih.gov",
        "noaa.gov",
        "nobelprize.org",
        "npr.org",
        "nytimes.com",
        "ourworldindata.org",
        "pewresearch.org",
        "reuters.com",
        "science.org",
        "sciencedirect.com",
        "smithsonianmag.com",
        "theguardian.com",
        "washingtonpost.com",
        "who.int",
        "wsj.com",
        "wikipedia.org",
    }
)

#: User-generated / unmoderated platforms: anyone can post anything.
_LOW_TRUST_DOMAINS = frozenset(
    {
        "blogspot.com",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "medium.com",
        "pinterest.com",
        "quora.com",
        "reddit.com",
        "tiktok.com",
        "tumblr.com",
        "twitter.com",
        "wordpress.com",
        "x.com",
        "youtube.com",
    }
)

#: Top-level domains whose registration itself implies institutional standing.
_HIGH_TRUST_SUFFIXES = (".gov", ".edu", ".mil")


def _registrable_match(host: str, domain: str) -> bool:
    """True if `host` is `domain` or a subdomain of it (dot-boundary safe)."""
    return host == domain or host.endswith("." + domain)


def domain_tier(url: str) -> SourceTier:
    """Classify a source URL's domain into a credibility tier.

    Unknown domains are "medium" — most of the web is neither a wire service
    nor a social feed, and defaulting unknowns to either extreme would make
    the signal noise.
    """
    host = urlparse(url).netloc.lower().split(":")[0]
    if not host:
        return "medium"
    if host.endswith(_HIGH_TRUST_SUFFIXES) or any(
        _registrable_match(host, d) for d in _HIGH_TRUST_DOMAINS
    ):
        return "high"
    if any(_registrable_match(host, d) for d in _LOW_TRUST_DOMAINS):
        return "low"
    return "medium"
