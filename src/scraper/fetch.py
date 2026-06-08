"""Fetcher seam for ielts-deck.

Resolves raw HTML for a word from Oxford Learner's Dictionary,
Cambridge Dictionary, or any future source. The interface is:
fetch one word's HTML, transparently using a local cache. The seam
hides:
  - HTTP library (requests / aiohttp)
  - Throttle
  - User-Agent
  - Cache path convention
  - Source URL template
  - SSL verification toggle

Adapters:
  - OxfordFetcher: OXFORD_URL = definition/english/{word}
  - CambridgeFetcher: CAMBRIDGE_URL = dictionary.cambridge.org/.../{word}
  - CachingFetcher: wraps any fetcher with disk cache (uses
    adapter's `cache_name()` for the path)

The interface is sync-first. Async adapters (e.g. AsyncFetcher for
aiohttp) can be added later by changing the return type — the
_caller_ pattern stays the same.

B in architecture review (proof of concept: scrape_with_fallback
migrated, other 5 call sites deferred).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# ── URL templates (single source of truth) ────────────────────────

OXFORD_URL = "https://www.oxfordlearnersdictionaries.com/definition/english/{word}"
CAMBRIDGE_URL = "https://dictionary.cambridge.org/dictionary/english/{word}"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 30.0  # seconds
DEFAULT_THROTTLE = 0.25  # seconds between network requests


# ── Result ─────────────────────────────────────────────────────────

@dataclass
class FetchResult:
    """Outcome of a single fetch call.

    `text` is the raw HTML on success (cache hit OR network OK).
    `cache_hit` is True if the cache supplied the bytes (no network).
    `error` is set on network/parse failure; `text` may be partial.
    """
    text: str | None = None
    cache_hit: bool = False
    http_status: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.text is not None and not self.error


# ── Fetcher protocol ───────────────────────────────────────────────

class Fetcher(Protocol):
    """Adapter that satisfies the HTML fetch seam.

    Implementations: HttpFetcher, CambridgeHttpFetcher (ssl=False),
    InMemoryFetcher (tests), CachingFetcher (decorator).
    """

    def fetch(self, word: str) -> FetchResult: ...
    def cache_name(self, word: str) -> str:
        """Filename (basename, not full path) used for this word's cache."""
        ...


# ── Cache decorator ────────────────────────────────────────────────

@dataclass
class CachingFetcher:
    """Wraps another Fetcher with disk cache. Reads first, writes on miss.

    `cache_dir` is the directory where cache files live (will be created
    on first write). `cache_hit` reports True when the file existed and
    was returned without calling the inner fetcher.
    """
    inner: Fetcher
    cache_dir: Path

    def cache_name(self, word: str) -> str:
        return self.inner.cache_name(word)

    def fetch(self, word: str) -> FetchResult:
        path = self.cache_dir / self.cache_name(word)
        if path.exists():
            return FetchResult(
                text=path.read_text(encoding="utf-8", errors="replace"),
                cache_hit=True,
            )
        result = self.inner.fetch(word)
        if result.ok and result.text is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(result.text, encoding="utf-8", errors="replace")
        return result


# ── HTTP adapters ──────────────────────────────────────────────────

@dataclass
class HttpFetcher:
    """Synchronous HTTP fetcher using requests.

    `url_template` is the URL with `{word}` placeholder.
    `verify_ssl` set False for sources that have cert issues
    (Cambridge on some Windows envs).
    """
    url_template: str
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = DEFAULT_TIMEOUT
    verify_ssl: bool = True

    def cache_name(self, word: str) -> str:
        return f"{word}.html"

    def fetch(self, word: str) -> FetchResult:
        import requests
        url = self.url_template.format(word=word)
        try:
            r = requests.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except Exception as e:
            return FetchResult(error=f"network: {e}")
        if r.status_code != 200:
            return FetchResult(http_status=r.status_code, error=f"HTTP {r.status_code}")
        return FetchResult(text=r.text, http_status=r.status_code)


@dataclass
class ThrottledFetcher:
    """Wraps any Fetcher, sleeps `throttle` seconds after each network call.

    Cache hits don't sleep (no network was made). Use this as the
    innermost wrapper around HttpFetcher, then wrap with CachingFetcher.
    """
    inner: Fetcher
    throttle: float = DEFAULT_THROTTLE

    def cache_name(self, word: str) -> str:
        return self.inner.cache_name(word)

    def fetch(self, word: str) -> FetchResult:
        result = self.inner.fetch(word)
        if not result.cache_hit and result.ok:
            import time
            time.sleep(self.throttle)
        return result


# ── Convenience constructors ──────────────────────────────────────

def oxford_cached(cache_dir: Path, throttle: float = DEFAULT_THROTTLE) -> CachingFetcher:
    """Build the standard Oxford fetcher: CachingFetcher(ThrottledFetcher(HttpFetcher))."""
    return CachingFetcher(
        inner=ThrottledFetcher(
            inner=HttpFetcher(url_template=OXFORD_URL),
            throttle=throttle,
        ),
        cache_dir=cache_dir,
    )


def cambridge_cached(cache_dir: Path, throttle: float = DEFAULT_THROTTLE) -> CachingFetcher:
    """Cambridge fetcher (ssl=False per scrape_with_fallback convention)."""
    return CachingFetcher(
        inner=ThrottledFetcher(
            inner=HttpFetcher(url_template=CAMBRIDGE_URL, verify_ssl=False),
            throttle=throttle,
        ),
        cache_dir=cache_dir,
    )
