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
from typing import Optional

import requests

from jf_sebastian.config import settings

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 5
_HEADLINE_MAX_CHARS = 120  # truncate longer titles so context stays tight

# Required env vars per provider — used in "selected but not configured" warnings
# so users know exactly what they're missing.
_REQUIRED_VARS = {
    "rss": "NEWS_RSS_URL",
    "manual": "MANUAL_NEWS",
    "hackernews": "(no env vars required)",
}

# NPR Topics: News feed — used as the default if NEWS_RSS_URL is not set
# and the user has news enabled.
_DEFAULT_RSS_URL = "https://feeds.npr.org/1001/rss.xml"


def _truncate(text: str, max_chars: int = _HEADLINE_MAX_CHARS) -> str:
    text = text.strip()
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

        Up to `settings.NEWS_HEADLINE_LIMIT` headlines, ordered most-relevant
        first. Empty list and None both mean "no headlines available."
        """


class RssNewsProvider(NewsProvider):
    """Fetches headlines from any RSS or Atom feed via feedparser."""

    name = "rss"

    def is_configured(self) -> bool:
        # NPR default applies if the user enabled news but didn't set a URL.
        return bool(self._url())

    def _url(self) -> str:
        return (settings.NEWS_RSS_URL or _DEFAULT_RSS_URL).strip()

    def fetch(self) -> Optional[list[str]]:
        # Lazy import — feedparser is only needed when this provider runs.
        import feedparser

        url = self._url()
        # Use requests so we share the same timeout/headers conventions as
        # the weather providers; feedparser then parses the body.
        response = requests.get(url, timeout=_HTTP_TIMEOUT)
        response.raise_for_status()
        feed = feedparser.parse(response.content)

        if feed.bozo and not feed.entries:
            logger.warning("RSS feed %s parsed with errors: %s", url, feed.bozo_exception)
            return None

        limit = max(1, int(settings.NEWS_HEADLINE_LIMIT))
        headlines: list[str] = []
        for entry in feed.entries[:limit]:
            title = getattr(entry, "title", "")
            if not title:
                continue
            headlines.append(_truncate(title))
        return headlines or None


class HackerNewsProvider(NewsProvider):
    """Fetches top stories from the Hacker News public API."""

    name = "hackernews"
    _TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
    _ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

    def is_configured(self) -> bool:
        # No config required — the public API is free and unauthenticated.
        return True

    def fetch(self) -> Optional[list[str]]:
        limit = max(1, int(settings.NEWS_HEADLINE_LIMIT))
        ids_response = requests.get(self._TOP_STORIES_URL, timeout=_HTTP_TIMEOUT)
        ids_response.raise_for_status()
        story_ids = ids_response.json()
        if not isinstance(story_ids, list):
            return None

        headlines: list[str] = []
        for story_id in story_ids[:limit]:
            try:
                item = requests.get(
                    self._ITEM_URL.format(id=story_id), timeout=_HTTP_TIMEOUT
                ).json()
            except Exception as e:
                logger.debug("HN item %s failed: %s", story_id, e)
                continue
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
                logger.warning(
                    "NEWS_PROVIDER=%r selected but provider is not fully configured. "
                    "Set: %s. News context will be omitted.",
                    explicit, _REQUIRED_VARS.get(explicit, "(see docs)"),
                )
            return provider

    for cls in _AUTO_PRIORITY:
        provider = cls()
        if provider.is_configured():
            return provider
    return None
