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
        context_provider._get_provider()
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


def test_no_http_calls_when_unconfigured(settings_overrides):
    """A fresh install with no env vars should never call requests.get."""
    settings_overrides()
    with patch(
        "jf_sebastian.utils.weather.requests.get",
        side_effect=AssertionError("requests.get should not be called when unconfigured"),
    ):
        context_provider.warm_weather_cache()
        context = context_provider.get_realworld_context()
    assert "Current weather" not in context
