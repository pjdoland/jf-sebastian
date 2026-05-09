"""Shared fixtures for tests/utils/."""

import pytest


@pytest.fixture
def settings_overrides(monkeypatch):
    """Reset weather-related settings to None and return a setter for per-test overrides."""
    from jf_sebastian.config import settings

    defaults = {
        "WEATHER_PROVIDER": None,
        "ZIPCODE": None,
        "HOME_ASSISTANT_URL": None,
        "HOME_ASSISTANT_TOKEN": None,
        "HOME_ASSISTANT_WEATHER_ENTITY": None,
        "MANUAL_WEATHER": None,
    }
    for key, value in defaults.items():
        monkeypatch.setattr(settings, key, value, raising=False)

    def apply(**overrides):
        for key, value in overrides.items():
            monkeypatch.setattr(settings, key, value, raising=False)

    return apply
