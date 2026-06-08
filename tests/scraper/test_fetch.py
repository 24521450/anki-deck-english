"""Tests for src.scraper.fetch.

Covers:
- HttpFetcher: 200 → ok; 404 → error; network exception → error
- CachingFetcher: cache hit skips network; cache miss writes + reads back
- ThrottledFetcher: sleeps on miss; doesn't sleep on hit
- InMemoryFetcher: deterministic, used to verify call order
- oxford_cached / cambridge_cached: convenience constructors wire up
  the standard pipeline; cache_name contract
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from src.scraper.fetch import (
    CAMBRIDGE_URL,
    FetchResult,
    Fetcher,
    OXFORD_URL,
    CachingFetcher,
    HttpFetcher,
    ThrottledFetcher,
    cambridge_cached,
    oxford_cached,
)


# ── Test adapters ──────────────────────────────────────────────────

class InMemoryFetcher:
    """Deterministic Fetcher for tests. `responses[word]` = FetchResult."""
    def __init__(self, responses: dict[str, FetchResult] | None = None,
                 default: FetchResult | None = None,
                 cache_name_fn: Callable[[str], str] = lambda w: f"{w}.html"):
        self.responses = responses or {}
        self.default = default or FetchResult(text="<html>default</html>")
        self.calls: list[str] = []
        self.cache_name_fn = cache_name_fn

    def fetch(self, word: str) -> FetchResult:
        self.calls.append(word)
        return self.responses.get(word, self.default)

    def cache_name(self, word: str) -> str:
        return self.cache_name_fn(word)


# ── HttpFetcher (network-mocked) ───────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def test_http_fetcher_returns_text_on_200(monkeypatch):
    import requests
    def fake_get(url, headers, timeout, verify):
        return _FakeResponse(200, "<html>oxford</html>")
    monkeypatch.setattr(requests, "get", fake_get)
    f = HttpFetcher(url_template=OXFORD_URL)
    r = f.fetch("run")
    assert r.ok
    assert r.text == "<html>oxford</html>"
    assert r.http_status == 200
    assert r.cache_hit is False


def test_http_fetcher_returns_error_on_404(monkeypatch):
    import requests
    def fake_get(url, headers, timeout, verify):
        return _FakeResponse(404, "")
    monkeypatch.setattr(requests, "get", fake_get)
    f = HttpFetcher(url_template=OXFORD_URL)
    r = f.fetch("missing")
    assert not r.ok
    assert r.http_status == 404
    assert "404" in r.error


def test_http_fetcher_returns_error_on_network_exception(monkeypatch):
    import requests
    def fake_get(url, headers, timeout, verify):
        raise requests.ConnectionError("dns fail")
    monkeypatch.setattr(requests, "get", fake_get)
    f = HttpFetcher(url_template=OXFORD_URL)
    r = f.fetch("any")
    assert not r.ok
    assert "network" in r.error
    assert "dns fail" in r.error


# ── CachingFetcher ─────────────────────────────────────────────────

def test_caching_fetcher_returns_cache_hit(tmp_path: Path):
    inner = InMemoryFetcher(
        responses={"run": FetchResult(text="<html>network</html>")},
    )
    f = CachingFetcher(inner=inner, cache_dir=tmp_path)
    r = f.fetch("run")
    assert r.cache_hit is False  # first call: network
    assert r.text == "<html>network</html>"

    # Second call should be cache hit
    r2 = f.fetch("run")
    assert r2.cache_hit is True
    assert r2.text == "<html>network</html>"
    # Inner was only called once
    assert inner.calls == ["run"]


def test_caching_fetcher_writes_to_disk(tmp_path: Path):
    inner = InMemoryFetcher(
        responses={"run": FetchResult(text="<html>persisted</html>")},
        cache_name_fn=lambda w: f"oxford_{w}.html",
    )
    f = CachingFetcher(inner=inner, cache_dir=tmp_path)
    f.fetch("run")
    cached = tmp_path / "oxford_run.html"
    assert cached.exists()
    assert cached.read_text(encoding="utf-8") == "<html>persisted</html>"


def test_caching_fetcher_does_not_write_on_error(tmp_path: Path):
    """If the inner fetcher errors, the cache must not be written."""
    inner = InMemoryFetcher(
        responses={"run": FetchResult(error="HTTP 500")},
    )
    f = CachingFetcher(inner=inner, cache_dir=tmp_path)
    f.fetch("run")
    # Cache file should NOT exist
    assert not (tmp_path / "run.html").exists()


# ── ThrottledFetcher ───────────────────────────────────────────────

def test_throttled_fetcher_sleeps_on_miss(monkeypatch):
    inner = InMemoryFetcher(responses={"run": FetchResult(text="x")})
    f = ThrottledFetcher(inner=inner, throttle=0.05)
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    f.fetch("run")
    assert sleeps == [0.05]


def test_throttled_fetcher_does_not_sleep_on_cache_hit(monkeypatch):
    """CachingFetcher at the OUTER level reports cache_hit; ThrottledFetcher
    should not sleep when the inner (cache) returns a hit."""
    inner = InMemoryFetcher(responses={"run": FetchResult(text="x", cache_hit=True)})
    f = ThrottledFetcher(inner=inner, throttle=0.05)
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    f.fetch("run")
    assert sleeps == []


# ── Convenience constructors ──────────────────────────────────────

def test_oxford_cached_uses_oxford_url_and_default_cache_name(tmp_path: Path):
    f = oxford_cached(cache_dir=tmp_path)
    assert f.cache_name("run") == "run.html"
    # The inner is a ThrottledFetcher wrapping an HttpFetcher with OXFORD_URL.
    inner = f.inner.inner
    assert inner.url_template == OXFORD_URL
    assert inner.verify_ssl is True  # Oxford has valid certs


def test_cambridge_cached_uses_cambridge_url_and_ssl_false(tmp_path: Path):
    f = cambridge_cached(cache_dir=tmp_path)
    assert f.cache_name("run") == "run.html"
    inner = f.inner.inner
    assert inner.url_template == CAMBRIDGE_URL
    assert inner.verify_ssl is False  # Cambridge on some Windows envs


# ── FetchResult contract ──────────────────────────────────────────

def test_fetch_result_ok_when_text_and_no_error():
    assert FetchResult(text="x").ok is True
    assert FetchResult(text="x", error=None).ok is True
    assert FetchResult(text=None).ok is False
    assert FetchResult(text="x", error="oops").ok is False
    assert FetchResult(text=None, error="e").ok is False
