"""
Tests for the real-world context builder.
"""

from unittest.mock import patch

import pytest

from jf_sebastian.utils import context_provider


@pytest.fixture(autouse=True)
def reset_provider():
    """Ensure each test starts with a fresh provider singleton and empty cache."""
    context_provider._reset_provider_for_tests()
    yield
    context_provider._reset_provider_for_tests()


def test_context_includes_date_and_time(settings_overrides):
    settings_overrides()
    context = context_provider.get_realworld_context()
    assert "Current date and time:" in context


def test_context_no_weather_when_disabled(settings_overrides):
    settings_overrides(WEATHER_PROVIDER="none", ZIPCODE="90210")
    context = context_provider.get_realworld_context()
    assert "Current weather" not in context


def test_context_uses_manual_provider(settings_overrides):
    settings_overrides(MANUAL_WEATHER="Sunny and 72F")
    context = context_provider.get_realworld_context()
    assert "Current weather: Sunny and 72F" in context


def test_format_weather_full_payload():
    text = context_provider._format_weather({
        "location": "Home",
        "description": "Sunny",
        "temp_f": 72.0,
        "feels_like_f": 70.0,
        "humidity": 45.0,
        "wind_mph": 8.0,
        "wind_dir": "WSW",
    })
    assert text == "Current weather in Home: Sunny, 72.0F (feels like 70.0F), humidity 45.0%, wind 8.0 mph WSW"


def test_format_weather_omits_missing_fields():
    text = context_provider._format_weather({"description": "Foggy"})
    assert text == "Current weather: Foggy"


def test_format_weather_skips_redundant_feels_like():
    text = context_provider._format_weather({
        "description": "Sunny",
        "temp_f": 72,
        "feels_like_f": 72.0,  # int vs float — should still match numerically
    })
    assert "feels like" not in text


def test_format_weather_handles_no_data():
    assert context_provider._format_weather({}) == "Current weather: unknown"


def test_format_weather_drops_unnormalized_garbage():
    """A third-party provider that forgets to normalize must not crash the formatter."""
    text = context_provider._format_weather({
        "description": "Sunny",
        "temp_f": "not-a-number",
        "humidity": "unavailable",
        "wind_mph": None,
    })
    assert text == "Current weather: Sunny"


def test_no_provider_logs_disabled_message(settings_overrides, caplog):
    """A user who's not configured anything should get an INFO line they can grep for."""
    settings_overrides()
    with caplog.at_level("INFO"):
        context_provider._get_weather_provider_cached()
    assert any("Weather context disabled" in r.message for r in caplog.records)


def test_cold_miss_triggers_sync_fetch(settings_overrides):
    settings_overrides(MANUAL_WEATHER="Cold and snowy")
    context = context_provider.get_realworld_context()
    assert "Cold and snowy" in context
    assert context_provider._weather_cache == {"description": "Cold and snowy"}


def test_provider_fetch_failure_negative_caches(settings_overrides):
    """When the provider raises, we should not pile up retry threads."""
    settings_overrides(ZIPCODE="90210")
    with patch(
        "jf_sebastian.utils.weather.requests.get",
        side_effect=Exception("network down"),
    ):
        # First call: cold miss, sync fetch fails, no weather rendered.
        context_provider.get_realworld_context()
        # Second call: should not retry yet (negative-cached for ~_RETRY_AFTER_SECONDS).
        # Verify by checking the cache time is recent enough that cache_stale is False.
        import time as _time
        age = _time.time() - context_provider._weather_cache_time
        assert age < context_provider._WEATHER_CACHE_TTL, "negative cache should suppress immediate retry"


def test_warm_cache_no_op_without_provider(settings_overrides):
    settings_overrides()
    # Should not raise, should not start any threads doing real work
    context_provider.warm_weather_cache()


def test_no_http_calls_when_explicitly_disabled(settings_overrides):
    """When weather is unconfigured AND news is explicitly NEWS_PROVIDER=none,
    neither subsystem should make any HTTP calls. (Out-of-the-box, news is
    on by default — see test_default_news_uses_npr_rss for that path.)"""
    settings_overrides()  # NEWS_PROVIDER defaults to "none" in conftest
    with patch(
        "jf_sebastian.utils.weather.requests.get",
        side_effect=AssertionError("weather.requests.get should not be called when unconfigured"),
    ), patch(
        "jf_sebastian.utils.news.requests.get",
        side_effect=AssertionError("news.requests.get should not be called when news disabled"),
    ):
        context_provider.warm_weather_cache()
        context_provider.warm_news_cache()
        context = context_provider.get_realworld_context()
    assert "Current weather" not in context
    assert "Top headlines" not in context


# ─── News integration ─────────────────────────────────────────────────────────


def test_format_news_renders_bullets():
    text = context_provider._format_news(["First", "Second", "Third"])
    assert text == "Top headlines:\n- First\n- Second\n- Third"


def test_format_news_handles_empty_list():
    assert context_provider._format_news([]) == ""


def test_context_uses_manual_news(settings_overrides):
    settings_overrides(
        NEWS_PROVIDER="manual",
        MANUAL_NEWS="Headline A\nHeadline B",
    )
    context = context_provider.get_realworld_context()
    assert "Top headlines:" in context
    assert "- Headline A" in context
    assert "- Headline B" in context


def test_context_no_news_when_disabled(settings_overrides):
    settings_overrides(NEWS_PROVIDER="none", MANUAL_NEWS="Should not appear")
    context = context_provider.get_realworld_context()
    assert "Top headlines" not in context


def test_news_negative_caches_on_failure(settings_overrides):
    """When the news provider raises, we shouldn't tight-loop retries."""
    settings_overrides(NEWS_PROVIDER="rss", NEWS_RSS_URL="https://example.com/rss")
    with patch(
        "jf_sebastian.utils.news.requests.get",
        side_effect=Exception("network down"),
    ):
        context_provider.get_realworld_context()
        import time as _time
        ttl = context_provider._news_cache_ttl()
        age = _time.time() - context_provider._news_cache_time
        assert age < ttl, "negative cache should suppress immediate retry"


def test_warm_news_cache_no_op_without_provider(settings_overrides):
    settings_overrides()  # NEWS_PROVIDER=none from conftest
    context_provider.warm_news_cache()  # should not raise


def test_default_news_uses_npr_rss(settings_overrides):
    """Pin behavior: out-of-box default (no NEWS_* env vars) auto-selects RSS
    with the NPR fallback URL. This is the 'always-on' default the user chose."""
    settings_overrides(NEWS_PROVIDER=None)  # explicit unset, not "none"
    provider = context_provider._get_news_provider_cached()
    # Provider is RssNewsProvider with the NPR default URL
    assert provider is not None
    assert provider.name == "rss"
    description = provider.describe()
    assert "NPR" in description
    assert "default" in description


def test_context_includes_both_weather_and_news(settings_overrides):
    """When both subsystems are configured, both sections appear."""
    settings_overrides(
        MANUAL_WEATHER="Foggy",
        NEWS_PROVIDER="manual",
        MANUAL_NEWS="Headline one\nHeadline two",
    )
    context = context_provider.get_realworld_context()
    assert "Current weather: Foggy" in context
    assert "Top headlines:" in context
    assert "- Headline one" in context
    # Order: weather before news
    assert context.index("Current weather") < context.index("Top headlines")
