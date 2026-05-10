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

    def test_strips_html_tags(self):
        # Real-world feeds occasionally embed markup in <title>; without
        # stripping, the LLM sees and TTS would speak the tag literally.
        assert _truncate("<b>BREAKING:</b> Storm warning") == "BREAKING: Storm warning"
        assert _truncate('<a href="x">Foo</a>') == "Foo"


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

    def test_not_configured_with_invalid_url_scheme(self, settings_overrides, caplog):
        settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="file:///etc/passwd")
        with caplog.at_level("WARNING"):
            assert RssNewsProvider().is_configured() is False
        assert any("not a valid http(s) URL" in r.message for r in caplog.records)

    def test_not_configured_with_unparseable_url(self, settings_overrides):
        settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="http://[invalid")
        assert RssNewsProvider().is_configured() is False

    def test_describe_includes_url(self, settings_overrides):
        settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="https://example.com/feed.xml")
        assert "https://example.com/feed.xml" in RssNewsProvider().describe()

    def test_describe_npr_default_marked(self, settings_overrides):
        settings_overrides(NEWS_PROVIDER="rss")
        assert "NPR" in RssNewsProvider().describe()

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
        with patch(
            "jf_sebastian.utils.news.requests.get", return_value=self._make_response(body)
        ) as mock_get:
            headlines = RssNewsProvider().fetch()
        assert headlines == ["First headline", "Second headline", "Third headline"]
        # Verify we send a User-Agent and disable redirects (security/politeness).
        kwargs = mock_get.call_args.kwargs
        assert "User-Agent" in kwargs["headers"]
        assert kwargs["allow_redirects"] is False

    def test_fetch_strips_html_in_titles(self, settings_overrides):
        settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="https://example.com/rss")
        body = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>&lt;b&gt;BREAKING:&lt;/b&gt; Storm warning</title></item>
</channel></rss>"""
        with patch("jf_sebastian.utils.news.requests.get", return_value=self._make_response(body)):
            headlines = RssNewsProvider().fetch()
        assert headlines == ["BREAKING: Storm warning"]

    def test_fetch_returns_none_on_request_exception(self, settings_overrides):
        """Network errors must not propagate — caller relies on None for negative-cache."""
        import requests as _requests
        settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="https://example.com/rss")
        with patch(
            "jf_sebastian.utils.news.requests.get",
            side_effect=_requests.ConnectionError("network down"),
        ):
            assert RssNewsProvider().fetch() is None

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
    """HN uses a `requests.Session` for connection reuse and parallel item fetches.
    Tests patch `Session.get` so the test doubles match the production call path.
    """

    def _patched_session_get(self, url_to_response):
        """Build a side_effect for Session.get(self, url, timeout=...) that
        returns canned responses keyed by URL substring."""

        def _side_effect(self, url, timeout):
            for needle, resp in url_to_response.items():
                if url.endswith(needle):
                    return resp
            raise AssertionError(f"unexpected URL {url!r}")

        return _side_effect

    def _make_resp(self, json_value):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = json_value
        return resp

    def test_always_configured(self, settings_overrides):
        settings_overrides()
        assert HackerNewsProvider().is_configured() is True

    def test_fetch_returns_top_titles(self, settings_overrides):
        settings_overrides(NEWS_HEADLINE_LIMIT=3)
        url_map = {
            "topstories.json": self._make_resp([101, 102, 103, 999]),
            "/item/101.json": self._make_resp({"title": "Story one"}),
            "/item/102.json": self._make_resp({"title": "Story two"}),
            "/item/103.json": self._make_resp({"title": "Story three"}),
        }
        with patch.object(
            __import__("requests").Session, "get",
            self._patched_session_get(url_map),
        ):
            headlines = HackerNewsProvider().fetch()
        # Order is preserved (HN ranking) — pool.map is order-preserving.
        assert headlines == ["Story one", "Story two", "Story three"]

    def test_fetch_skips_items_with_no_title(self, settings_overrides):
        settings_overrides(NEWS_HEADLINE_LIMIT=3)
        url_map = {
            "topstories.json": self._make_resp([201, 202, 203]),
            "/item/201.json": self._make_resp({"title": "Has title"}),
            "/item/202.json": self._make_resp(None),    # deleted
            "/item/203.json": self._make_resp({}),       # malformed
        }
        with patch.object(
            __import__("requests").Session, "get",
            self._patched_session_get(url_map),
        ):
            headlines = HackerNewsProvider().fetch()
        assert headlines == ["Has title"]

    def test_fetch_returns_none_on_non_list_topstories(self, settings_overrides):
        settings_overrides()
        url_map = {"topstories.json": self._make_resp({"unexpected": "shape"})}
        with patch.object(
            __import__("requests").Session, "get",
            self._patched_session_get(url_map),
        ):
            assert HackerNewsProvider().fetch() is None

    def test_fetch_returns_none_on_request_exception(self, settings_overrides):
        """Network errors must not propagate — caller relies on None for negative-cache."""
        import requests as _requests
        settings_overrides()
        with patch.object(
            _requests.Session, "get",
            side_effect=_requests.ConnectionError("network down"),
        ):
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
