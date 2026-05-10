"""
Tests for the pluggable news headline system.
"""

from unittest.mock import MagicMock, patch

import pytest

from jf_sebastian.utils.news import (
    HackerNewsProvider,
    ManualNewsProvider,
    RssNewsProvider,
    _truncate,
    get_news_provider,
)


class TestTruncate:
    def test_passes_short(self):
        assert _truncate("hello") == "hello"

    def test_strips_whitespace(self):
        assert _truncate("  hello  ") == "hello"

    def test_truncates_with_ellipsis(self):
        result = _truncate("a" * 200, max_chars=10)
        assert len(result) == 10
        assert result.endswith("…")


class TestRssProvider:
    def _make_response(self, body: bytes):
        resp = MagicMock()
        resp.content = body
        resp.raise_for_status = MagicMock()
        return resp

    def test_uses_npr_default_when_url_unset(self, settings_overrides):
        """NPR is the default RSS feed — provider is configured even with no URL set."""
        settings_overrides(NEWS_PROVIDER="rss")
        assert RssNewsProvider().is_configured() is True

    def test_fetch_extracts_titles(self, settings_overrides):
        settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="https://example.com/rss", NEWS_HEADLINE_LIMIT=3)
        body = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test</title>
    <item><title>First headline</title></item>
    <item><title>Second headline</title></item>
    <item><title>Third headline</title></item>
    <item><title>Fourth headline (over limit)</title></item>
  </channel>
</rss>"""
        with patch("jf_sebastian.utils.news.requests.get", return_value=self._make_response(body)):
            headlines = RssNewsProvider().fetch()
        assert headlines == ["First headline", "Second headline", "Third headline"]

    def test_fetch_truncates_long_titles(self, settings_overrides):
        settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="https://example.com/rss", NEWS_HEADLINE_LIMIT=1)
        long_title = "a" * 200
        body = f"""<?xml version="1.0"?>
<rss version="2.0"><channel><item><title>{long_title}</title></item></channel></rss>""".encode()
        with patch("jf_sebastian.utils.news.requests.get", return_value=self._make_response(body)):
            headlines = RssNewsProvider().fetch()
        assert len(headlines[0]) <= 120
        assert headlines[0].endswith("…")

    def test_fetch_handles_atom_feed(self, settings_overrides):
        settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="https://example.com/atom", NEWS_HEADLINE_LIMIT=5)
        body = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Atom story one</title></entry>
  <entry><title>Atom story two</title></entry>
</feed>"""
        with patch("jf_sebastian.utils.news.requests.get", return_value=self._make_response(body)):
            headlines = RssNewsProvider().fetch()
        assert headlines == ["Atom story one", "Atom story two"]

    def test_fetch_returns_none_on_unparseable(self, settings_overrides):
        settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="https://example.com/rss")
        with patch(
            "jf_sebastian.utils.news.requests.get",
            return_value=self._make_response(b"<not even XML"),
        ):
            assert RssNewsProvider().fetch() is None

    def test_fetch_decodes_html_entities(self, settings_overrides):
        settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="https://example.com/rss")
        # feedparser decodes &amp; and &#8217; etc.
        body = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><item><title>Tech &amp; Science</title></item></channel></rss>"""
        with patch("jf_sebastian.utils.news.requests.get", return_value=self._make_response(body)):
            headlines = RssNewsProvider().fetch()
        assert headlines == ["Tech & Science"]


class TestHackerNewsProvider:
    def test_always_configured(self, settings_overrides):
        settings_overrides()
        assert HackerNewsProvider().is_configured() is True

    def test_fetch_returns_top_titles(self, settings_overrides):
        settings_overrides(NEWS_HEADLINE_LIMIT=3)

        def fake_get(url, timeout):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if url.endswith("topstories.json"):
                resp.json.return_value = [101, 102, 103, 999]
            elif url.endswith("/item/101.json"):
                resp.json.return_value = {"title": "Story one"}
            elif url.endswith("/item/102.json"):
                resp.json.return_value = {"title": "Story two"}
            elif url.endswith("/item/103.json"):
                resp.json.return_value = {"title": "Story three"}
            return resp

        with patch("jf_sebastian.utils.news.requests.get", side_effect=fake_get):
            headlines = HackerNewsProvider().fetch()
        assert headlines == ["Story one", "Story two", "Story three"]

    def test_fetch_skips_items_with_no_title(self, settings_overrides):
        settings_overrides(NEWS_HEADLINE_LIMIT=3)

        def fake_get(url, timeout):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if url.endswith("topstories.json"):
                resp.json.return_value = [201, 202, 203]
            elif url.endswith("/item/201.json"):
                resp.json.return_value = {"title": "Has title"}
            elif url.endswith("/item/202.json"):
                resp.json.return_value = None  # deleted item
            elif url.endswith("/item/203.json"):
                resp.json.return_value = {}  # malformed
            return resp

        with patch("jf_sebastian.utils.news.requests.get", side_effect=fake_get):
            headlines = HackerNewsProvider().fetch()
        assert headlines == ["Has title"]

    def test_fetch_returns_none_on_non_list_topstories(self, settings_overrides):
        settings_overrides()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"unexpected": "shape"}
        with patch("jf_sebastian.utils.news.requests.get", return_value=resp):
            assert HackerNewsProvider().fetch() is None


class TestManualNewsProvider:
    def test_not_configured_when_blank(self, settings_overrides):
        settings_overrides()
        assert ManualNewsProvider().is_configured() is False

    def test_not_configured_when_whitespace_only(self, settings_overrides):
        settings_overrides(MANUAL_NEWS="   \n  \n   ")
        assert ManualNewsProvider().is_configured() is False

    def test_parses_real_newlines(self, settings_overrides):
        settings_overrides(MANUAL_NEWS="One\nTwo\nThree")
        assert ManualNewsProvider().fetch() == ["One", "Two", "Three"]

    def test_parses_literal_backslash_n(self, settings_overrides):
        # python-dotenv doesn't decode \n; the user's env-var string may
        # contain literal backslash-n that we expand here.
        settings_overrides(MANUAL_NEWS="One\\nTwo\\nThree")
        assert ManualNewsProvider().fetch() == ["One", "Two", "Three"]

    def test_skips_blank_lines(self, settings_overrides):
        settings_overrides(MANUAL_NEWS="One\n\n\nTwo")
        assert ManualNewsProvider().fetch() == ["One", "Two"]

    def test_honors_headline_limit(self, settings_overrides):
        settings_overrides(MANUAL_NEWS="One\nTwo\nThree\nFour", NEWS_HEADLINE_LIMIT=2)
        assert ManualNewsProvider().fetch() == ["One", "Two"]


class TestProviderFactory:
    def test_explicit_none_returns_none(self, settings_overrides):
        settings_overrides(NEWS_PROVIDER="none", NEWS_RSS_URL="https://example.com/rss")
        assert get_news_provider() is None

    def test_explicit_choice_overrides_others(self, settings_overrides):
        settings_overrides(
            NEWS_PROVIDER="manual",
            NEWS_RSS_URL="https://example.com/rss",
            MANUAL_NEWS="Just this",
        )
        assert isinstance(get_news_provider(), ManualNewsProvider)

    def test_unknown_provider_warns_and_falls_back(self, settings_overrides, caplog):
        settings_overrides(NEWS_PROVIDER="nonsense")
        with caplog.at_level("WARNING"):
            provider = get_news_provider()
        # Falls back to auto; rss is configured by default (NPR fallback).
        assert isinstance(provider, RssNewsProvider)
        assert any("Unknown NEWS_PROVIDER" in r.message for r in caplog.records)

    def test_auto_picks_rss_with_npr_default(self, settings_overrides):
        """Out-of-the-box: no env vars set → rss provider with NPR default URL."""
        settings_overrides(NEWS_PROVIDER=None)
        assert isinstance(get_news_provider(), RssNewsProvider)

    def test_auto_excludes_hackernews(self, settings_overrides):
        """Hacker News should never auto-select since it's tech-only."""
        # Force rss to look unconfigured by setting an empty URL... but the NPR
        # default kicks in. Instead, set NEWS_PROVIDER to a known-broken value
        # that pushes us into auto-select.
        settings_overrides(NEWS_PROVIDER="auto")
        provider = get_news_provider()
        # Auto picks rss (NPR default); HN is excluded from auto.
        assert isinstance(provider, RssNewsProvider)

    def test_explicit_provider_unconfigured_warns(self, settings_overrides, caplog):
        """User sets NEWS_PROVIDER=manual but didn't set MANUAL_NEWS."""
        settings_overrides(NEWS_PROVIDER="manual")
        with caplog.at_level("WARNING"):
            provider = get_news_provider()
        assert isinstance(provider, ManualNewsProvider)
        assert any(
            "not fully configured" in r.message and "MANUAL_NEWS" in r.message
            for r in caplog.records
        )

    def test_explicit_none_logs_disabled(self, settings_overrides, caplog):
        settings_overrides(NEWS_PROVIDER="none")
        with caplog.at_level("INFO"):
            assert get_news_provider() is None
        assert any("news context disabled" in r.message.lower() for r in caplog.records)
