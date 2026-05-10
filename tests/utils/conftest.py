"""Shared fixtures for tests/utils/."""

import pytest


@pytest.fixture
def settings_overrides(monkeypatch):
    """Reset weather and news settings to safe defaults and return a setter for per-test overrides."""
    from jf_sebastian.config import settings

    defaults = {
        "WEATHER_PROVIDER": None,
        "ZIPCODE": None,
        "HOME_ASSISTANT_URL": None,
        "HOME_ASSISTANT_TOKEN": None,
        "HOME_ASSISTANT_WEATHER_ENTITY": None,
        "MANUAL_WEATHER": None,
        # News: explicitly disable for tests so an unrelated test doesn't try to
        # auto-select the NPR default and call out to the network.
        "NEWS_PROVIDER": "none",
        "NEWS_RSS_URL": None,
        "MANUAL_NEWS": None,
        "NEWS_HEADLINE_LIMIT": 5,
        "NEWS_CACHE_TTL_MINUTES": 30,
    }
    for key, value in defaults.items():
        monkeypatch.setattr(settings, key, value, raising=False)

    def apply(**overrides):
        for key, value in overrides.items():
            monkeypatch.setattr(settings, key, value, raising=False)

    return apply
