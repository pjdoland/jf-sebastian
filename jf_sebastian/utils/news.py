"""
News provider abstraction. Each provider returns a list of headline strings
(top N) so the context formatter can inject them into LLM context as a
"Top headlines:" bullet list.

Mirrors the weather provider pattern from `weather.py` — same shape, same
auto-selection model, same configuration ergonomics. Headlines are cached
for `NEWS_CACHE_TTL_MINUTES` (default 30) and pre-warmed at startup so the
first conversation doesn't pay for an HTTP round trip.
"""

import logging
import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import urlsplit

import feedparser
import requests

from jf_sebastian.config import settings

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 5
_HN_ITEM_TIMEOUT = 2  # per-item; we fan out in parallel so total ≈ slowest call
_HEADLINE_MAX_CHARS = 120  # truncate longer titles so context stays tight
# Polite identifying User-Agent. Some feeds (BBC, NYT, Cloudflare-fronted)
# 403 the default `python-requests/X.Y` UA, and feed publishers prefer to
# see who's polling them every 30 minutes.
_USER_AGENT = "jf-sebastian/1.0 (+https://github.com/pjdoland/jf-sebastian)"

# Strip any HTML tags that survive feedparser. Some feeds emit
# `<b>BREAKING:</b> Foo` or `<a href="…">Foo</a>` in <title>; without this
# the LLM gets the markup verbatim and TTS reads it literally.
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Required env vars per provider — used in "selected but not configured" warnings.
_REQUIRED_VARS = {
    "rss": "NEWS_RSS_URL",
    "manual": "MANUAL_NEWS",
}

# NPR Topics: News feed — used as the default if NEWS_RSS_URL is not set
# and the user has news enabled.
_DEFAULT_RSS_URL = "https://feeds.npr.org/1001/rss.xml"
_DEFAULT_RSS_LABEL = "NPR Topics: News"


def _truncate(text: str, max_chars: int = _HEADLINE_MAX_CHARS) -> str:
    text = _HTML_TAG_RE.sub("", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


class NewsProvider(ABC):
    """Base class for news headline sources."""

    name: str = "abstract"

    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has the settings it needs to attempt a fetch."""

    @abstractmethod
    def fetch(self) -> Optional[list[str]]:
        """Fetch top headlines. Return a list of strings or None on failure.

        Implementations MUST NOT raise — return None on any failure so the
        caller can negative-cache uniformly. Up to `settings.NEWS_HEADLINE_LIMIT`
        headlines, ordered most-relevant first.
        """

    def describe(self) -> str:
        """Human-readable identifier for logs (e.g., 'rss (NPR Topics: News)')."""
        return self.name


class RssNewsProvider(NewsProvider):
    """Fetches headlines from any RSS or Atom feed via feedparser.

    Defaults to NPR Topics: News if NEWS_RSS_URL is unset, so headlines are on
    out-of-the-box. URL is scheme-validated (http(s) only) before the request
    fires, and redirects are disabled so a misconfigured feed doesn't silently
    chain through arbitrary hosts.
    """

    name = "rss"

    def is_configured(self) -> bool:
        url = self._url()
        if not url:
            return False
        try:
            parsed = urlsplit(url)
        except ValueError as e:
            logger.warning("NEWS_RSS_URL=%r is unparseable: %s", url, e)
            return False
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            logger.warning(
                "NEWS_RSS_URL=%r is not a valid http(s) URL — refusing to fetch", url
            )
            return False
        return True

    def _url(self) -> str:
        return (settings.NEWS_RSS_URL or _DEFAULT_RSS_URL).strip()

    def describe(self) -> str:
        url = self._url()
        if url == _DEFAULT_RSS_URL:
            return f"rss ({_DEFAULT_RSS_LABEL}, default; {url})"
        return f"rss ({url})"

    def fetch(self) -> Optional[list[str]]:
        url = self._url()
        try:
            response = requests.get(
                url,
                timeout=_HTTP_TIMEOUT,
                headers={"User-Agent": _USER_AGENT},
                allow_redirects=False,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning("RSS fetch %s failed: %s: %s", url, type(e).__name__, str(e)[:200])
            return None

        feed = feedparser.parse(response.content)
        if feed.bozo:
            if not feed.entries:
                logger.warning("RSS feed %s parsed with errors: %s", url, feed.bozo_exception)
                return None
            logger.debug("RSS feed %s parsed with warnings (entries usable): %s", url, feed.bozo_exception)

        limit = max(1, int(settings.NEWS_HEADLINE_LIMIT))
        headlines: list[str] = []
        for entry in feed.entries[:limit]:
            title = getattr(entry, "title", "")
            if title:
                headlines.append(_truncate(str(title)))
        return headlines or None


class HackerNewsProvider(NewsProvider):
    """Fetches top stories from the Hacker News public API.

    Top-stories returns a list of N item IDs; we then fetch each item in
    parallel via a shared `requests.Session` so connection setup amortizes
    across calls. Per-item timeout is tighter than the top-stories timeout
    so the worst-case cold-miss latency stays bounded.
    """

    name = "hackernews"
    _TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
    _ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

    def is_configured(self) -> bool:
        # No config required — the public API is free and unauthenticated.
        return True

    def fetch(self) -> Optional[list[str]]:
        limit = max(1, int(settings.NEWS_HEADLINE_LIMIT))
        try:
            with requests.Session() as session:
                session.headers.update({"User-Agent": _USER_AGENT})
                ids_response = session.get(self._TOP_STORIES_URL, timeout=_HTTP_TIMEOUT)
                ids_response.raise_for_status()
                story_ids = ids_response.json()
                if not isinstance(story_ids, list):
                    return None
                ids = story_ids[:limit]

                def _fetch_item(sid):
                    try:
                        resp = session.get(
                            self._ITEM_URL.format(id=sid), timeout=_HN_ITEM_TIMEOUT
                        )
                        resp.raise_for_status()
                        return resp.json()
                    except Exception as e:
                        logger.debug("HN item %s failed: %s", sid, e)
                        return None

                with ThreadPoolExecutor(max_workers=min(8, max(1, len(ids)))) as pool:
                    items = list(pool.map(_fetch_item, ids))
        except requests.RequestException as e:
            logger.warning(
                "HN fetch failed: %s: %s", type(e).__name__, str(e)[:200]
            )
            return None

        headlines: list[str] = []
        for item in items:
            title = (item or {}).get("title")
            if title:
                headlines.append(_truncate(str(title)))
        return headlines or None


class ManualNewsProvider(NewsProvider):
    """Returns user-provided newline-separated headlines (offline / testing)."""

    name = "manual"

    def is_configured(self) -> bool:
        return bool((settings.MANUAL_NEWS or "").strip())

    def fetch(self) -> Optional[list[str]]:
        # Accept literal `\n` in env-var strings as well as actual newlines —
        # python-dotenv does NOT decode escape sequences, so users typing
        # `MANUAL_NEWS=Foo\nBar` get the literal backslash-n.
        raw = (settings.MANUAL_NEWS or "").replace("\\n", "\n")
        limit = max(1, int(settings.NEWS_HEADLINE_LIMIT))
        headlines = [_truncate(line) for line in raw.splitlines() if line.strip()]
        return headlines[:limit] or None


_PROVIDERS = {
    cls.name: cls for cls in (RssNewsProvider, HackerNewsProvider, ManualNewsProvider)
}
VALID_PROVIDER_NAMES = frozenset(_PROVIDERS.keys())

# Auto-select priority: rss (real-data, user-controlled URL) > manual (opt-in
# for testing/offline). Hacker News is intentionally excluded from auto —
# it's tech-only and would be a surprise default for non-technical users.
_AUTO_PRIORITY = (RssNewsProvider, ManualNewsProvider)


def get_news_provider() -> Optional[NewsProvider]:
    """Return the configured news provider, or None if news is disabled.

    Selection order:
    1. NEWS_PROVIDER="none" → disabled.
    2. NEWS_PROVIDER set to a known name → that provider (warns if not is_configured).
    3. Otherwise (unset or "auto") → first is_configured() provider in
       priority order: rss > manual. RSS is configured by default via the
       NPR fallback URL, so the out-of-box experience is "headlines on."
    """
    explicit = (settings.NEWS_PROVIDER or "").lower().strip()

    if explicit == "none":
        logger.info("NEWS_PROVIDER=none — news context disabled")
        return None
    if explicit and explicit != "auto":
        cls = _PROVIDERS.get(explicit)
        if not cls:
            logger.warning(
                "Unknown NEWS_PROVIDER=%r; valid values: %s. Falling back to auto-selection.",
                explicit, ", ".join(sorted(VALID_PROVIDER_NAMES) + ["none", "auto"]),
            )
        else:
            provider = cls()
            if not provider.is_configured():
                # Hacker News needs no env vars, so it can never trip this path.
                hint = _REQUIRED_VARS.get(explicit, "(see docs)")
                logger.warning(
                    "NEWS_PROVIDER=%r selected but provider is not fully configured. "
                    "Set: %s. News context will be omitted.",
                    explicit, hint,
                )
            return provider

    for cls in _AUTO_PRIORITY:
        provider = cls()
        if provider.is_configured():
            return provider
    return None
