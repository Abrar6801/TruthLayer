"""Tests for web search, page fetching, and text extraction — all HTTP mocked."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from truthlayer.search import SearchResult, extract_text, fetch_page, tavily_search


class _FakeResponse:
    def __init__(self, json_data: dict[str, Any] | None = None, text: str = "") -> None:
        self._json = json_data or {}
        self.text = text

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self._json


def test_tavily_search_parses_results(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "results": [
            {"url": "https://a.example", "title": "A", "raw_content": "Alpha content."},
            {"url": "https://b.example", "title": "B", "content": "Beta snippet."},
            {"url": "https://empty.example", "title": "Empty", "raw_content": "   "},
            {"url": "", "title": "No URL", "raw_content": "orphan text"},
        ]
    }
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["timeout"] = kwargs.get("timeout")
        return _FakeResponse(json_data=payload)

    monkeypatch.setattr(httpx, "post", fake_post)

    results = tavily_search("test claim", max_results=4)

    assert [r.url for r in results] == ["https://a.example", "https://b.example"]
    assert results[0].raw_content == "Alpha content."
    assert results[1].raw_content == "Beta snippet."  # falls back to `content`
    assert captured["timeout"] is not None  # explicit timeout is always set


def test_search_results_tagged_untrusted() -> None:
    result = SearchResult(url="https://x.example", title="t", raw_content="c")
    assert result.source == "untrusted_web"


def test_fetch_page_retries_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def always_timeout(url: str, **kwargs: Any) -> _FakeResponse:
        calls["count"] += 1
        raise httpx.ConnectTimeout("simulated timeout")

    monkeypatch.setattr(httpx, "get", always_timeout)

    with pytest.raises(httpx.ConnectTimeout):
        fetch_page("https://slow.example")
    assert calls["count"] == 3  # bounded retries, then gives up


def test_fetch_page_recovers_after_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def flaky(url: str, **kwargs: Any) -> _FakeResponse:
        calls["count"] += 1
        if calls["count"] < 2:
            raise httpx.ConnectError("simulated connection reset")
        return _FakeResponse(text="<html><body>ok</body></html>")

    monkeypatch.setattr(httpx, "get", flaky)

    assert "ok" in fetch_page("https://flaky.example")
    assert calls["count"] == 2


def test_extract_text_strips_boilerplate() -> None:
    html = """
    <html><head><script>alert('ads');</script></head>
    <body>
      <nav><a href="/">Home</a><a href="/about">About</a></nav>
      <article>
        <h1>The boiling point of water</h1>
        <p>At sea level, water boils at 100 degrees Celsius. This has been
        established through repeated measurement under standard atmospheric
        pressure conditions across many laboratories worldwide.</p>
        <p>At higher altitudes the boiling point decreases because the
        atmospheric pressure is lower, which is why cooking instructions
        sometimes differ for high-altitude locations.</p>
      </article>
      <footer>© 2026 Example Corp</footer>
    </body></html>
    """
    text = extract_text(html)
    assert "100 degrees Celsius" in text
    assert "alert(" not in text


def test_extract_text_empty_input() -> None:
    assert extract_text("") == ""
    assert extract_text("   \n  ") == ""
