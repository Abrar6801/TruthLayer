"""Tests for domain credibility tiering."""

from __future__ import annotations

import pytest

from truthlayer.source_credibility import domain_tier


@pytest.mark.parametrize(
    "url",
    [
        "https://www.reuters.com/world/some-article",
        "https://en.wikipedia.org/wiki/Boiling_point",
        "https://pwg.gsfc.nasa.gov/stargaze/Scolumb.htm",  # nasa.gov subdomain
        "https://www.cdc.gov/flu/index.html",
        "https://ocw.mit.edu/courses/",  # .edu suffix
    ],
)
def test_high_tier(url: str) -> None:
    assert domain_tier(url) == "high"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.facebook.com/FortuneMagazine/posts/12345",
        "https://www.quora.com/Is-there-any-evidence",
        "https://www.youtube.com/watch?v=abc",
        "https://old.reddit.com/r/askscience/",  # subdomain of a low-tier domain
    ],
)
def test_low_tier(url: str) -> None:
    assert domain_tier(url) == "low"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.some-random-blog.io/post",
        "https://checkthat.example/article",
        "",  # unparseable → medium, never a crash
    ],
)
def test_unknown_domains_default_to_medium(url: str) -> None:
    assert domain_tier(url) == "medium"


def test_lookalike_domains_do_not_inherit_tier() -> None:
    """evil-reuters.com must not match reuters.com (dot-boundary check)."""
    assert domain_tier("https://evilreuters.com/fake") == "medium"
    assert domain_tier("https://notreuters.com/fake") == "medium"


def test_low_tier_platform_cannot_be_promoted_by_path() -> None:
    """A path mentioning a trusted outlet doesn't change the domain's tier."""
    assert domain_tier("https://facebook.com/reuters.com/official") == "low"
