"""
Tests for the pluggable weather provider system.
"""

from unittest.mock import MagicMock, patch

import pytest

from jf_sebastian.utils.weather import (
    HomeAssistantWeatherProvider,
    ManualWeatherProvider,
    WttrWeatherProvider,
    _bearing_to_compass,
    _coerce_float,
    get_weather_provider,
)


class TestCoerceFloat:
    def test_passes_int(self):
        assert _coerce_float(72) == 72.0

    def test_passes_float(self):
        assert _coerce_float(72.5) == 72.5

    def test_parses_numeric_string(self):
        assert _coerce_float("72") == 72.0

    def test_strips_whitespace(self):
        assert _coerce_float("  72  ") == 72.0

    def test_none_returns_none(self):
        assert _coerce_float(None) is None

    def test_empty_string_returns_none(self):
        assert _coerce_float("") is None

    def test_ha_sentinel_returns_none(self):
        assert _coerce_float("unknown") is None
        assert _coerce_float("UNAVAILABLE") is None
        assert _coerce_float("none") is None

    def test_garbage_string_returns_none(self):
        assert _coerce_float("not-a-number") is None

    def test_bool_returns_none(self):
        assert _coerce_float(True) is None
        assert _coerce_float(False) is None


class TestWttrProvider:
    def test_not_configured_without_zipcode(self, settings_overrides):
        settings_overrides()
        assert WttrWeatherProvider().is_configured() is False

    def test_configured_with_zipcode(self, settings_overrides):
        settings_overrides(ZIPCODE="90210")
        assert WttrWeatherProvider().is_configured() is True

    def test_fetch_normalizes_response(self, settings_overrides):
        settings_overrides(ZIPCODE="90210")
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "current_condition": [
                {
                    "temp_F": "72",
                    "FeelsLikeF": "70",
                    "weatherDesc": [{"value": "Sunny"}],
                    "humidity": "45",
                    "windspeedMiles": "8",
                    "winddir16Point": "WSW",
                }
            ],
            "nearest_area": [{"areaName": [{"value": "Beverly Hills"}]}],
        }
        fake_response.raise_for_status = MagicMock()
        with patch("jf_sebastian.utils.weather.requests.get", return_value=fake_response):
            data = WttrWeatherProvider().fetch()

        assert data["location"] == "Beverly Hills"
        assert data["temp_f"] == 72.0  # coerced to float
        assert data["feels_like_f"] == 70.0
        assert data["humidity"] == 45.0
        assert data["wind_mph"] == 8.0
        assert data["description"] == "Sunny"
        assert data["wind_dir"] == "WSW"

    def test_fetch_handles_partial_response(self, settings_overrides):
        """A successful 200 with missing/empty arrays should yield a partial dict, not crash."""
        settings_overrides(ZIPCODE="90210")
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "current_condition": [{"weatherDesc": [{"value": "Cloudy"}]}],
            "nearest_area": [],
        }
        fake_response.raise_for_status = MagicMock()
        with patch("jf_sebastian.utils.weather.requests.get", return_value=fake_response):
            data = WttrWeatherProvider().fetch()
        assert data == {"description": "Cloudy"}

    def test_fetch_returns_none_on_empty_response(self, settings_overrides):
        settings_overrides(ZIPCODE="90210")
        fake_response = MagicMock()
        fake_response.json.return_value = {}
        fake_response.raise_for_status = MagicMock()
        with patch("jf_sebastian.utils.weather.requests.get", return_value=fake_response):
            assert WttrWeatherProvider().fetch() is None


class TestHomeAssistantProvider:
    def test_not_configured_when_partial(self, settings_overrides):
        settings_overrides(HOME_ASSISTANT_URL="http://ha.local:8123")
        assert HomeAssistantWeatherProvider().is_configured() is False

    def test_configured_with_all_three(self, settings_overrides):
        settings_overrides(
            HOME_ASSISTANT_URL="http://ha.local:8123",
            HOME_ASSISTANT_TOKEN="abc",
            HOME_ASSISTANT_WEATHER_ENTITY="weather.home",
        )
        assert HomeAssistantWeatherProvider().is_configured() is True

    def test_not_configured_with_invalid_url(self, settings_overrides):
        settings_overrides(
            HOME_ASSISTANT_URL="not-a-url",
            HOME_ASSISTANT_TOKEN="abc",
            HOME_ASSISTANT_WEATHER_ENTITY="weather.home",
        )
        assert HomeAssistantWeatherProvider().is_configured() is False

    def test_not_configured_with_non_weather_entity(self, settings_overrides):
        settings_overrides(
            HOME_ASSISTANT_URL="http://ha.local:8123",
            HOME_ASSISTANT_TOKEN="abc",
            HOME_ASSISTANT_WEATHER_ENTITY="sensor.temperature",
        )
        assert HomeAssistantWeatherProvider().is_configured() is False

    def test_not_configured_with_file_scheme(self, settings_overrides):
        settings_overrides(
            HOME_ASSISTANT_URL="file:///etc/passwd",
            HOME_ASSISTANT_TOKEN="abc",
            HOME_ASSISTANT_WEATHER_ENTITY="weather.home",
        )
        assert HomeAssistantWeatherProvider().is_configured() is False

    def test_fetch_fahrenheit_passthrough(self, settings_overrides):
        settings_overrides(
            HOME_ASSISTANT_URL="http://ha.local:8123/",
            HOME_ASSISTANT_TOKEN="abc",
            HOME_ASSISTANT_WEATHER_ENTITY="weather.home",
        )
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "state": "sunny",
            "attributes": {
                "friendly_name": "Home",
                "temperature": 72,
                "apparent_temperature": 70,
                "temperature_unit": "°F",
                "humidity": 45,
                "wind_speed": 8,
                "wind_speed_unit": "mph",
                "wind_bearing": 247.5,
            },
        }
        fake_response.raise_for_status = MagicMock()
        with patch("jf_sebastian.utils.weather.requests.get", return_value=fake_response) as mock_get:
            data = HomeAssistantWeatherProvider().fetch()

        # URL should not double-slash even if user includes trailing slash
        called_url = mock_get.call_args[0][0]
        assert "//api/states" not in called_url
        assert called_url.endswith("/api/states/weather.home")
        # Auth header should carry the bearer token, not be in the URL
        assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer abc"
        # Redirects must be off to avoid leaking the token cross-host
        assert mock_get.call_args.kwargs["allow_redirects"] is False

        assert data["description"] == "sunny"
        assert data["location"] == "Home"
        assert data["temp_f"] == 72.0
        assert data["feels_like_f"] == 70.0
        assert data["humidity"] == 45.0
        assert data["wind_mph"] == 8.0
        assert data["wind_dir"] == "WSW"

    def test_fetch_celsius_converts_to_fahrenheit(self, settings_overrides):
        settings_overrides(
            HOME_ASSISTANT_URL="http://ha.local:8123",
            HOME_ASSISTANT_TOKEN="abc",
            HOME_ASSISTANT_WEATHER_ENTITY="weather.home",
        )
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "state": "cloudy",
            "attributes": {
                "temperature": 20,
                "temperature_unit": "°C",
                "wind_speed": 10,
                "wind_speed_unit": "km/h",
            },
        }
        fake_response.raise_for_status = MagicMock()
        with patch("jf_sebastian.utils.weather.requests.get", return_value=fake_response):
            data = HomeAssistantWeatherProvider().fetch()

        assert data["temp_f"] == 68.0  # 20°C → 68°F
        assert data["wind_mph"] == 6.2  # 10 km/h → 6.2 mph

    def test_fetch_handles_unavailable_entity(self, settings_overrides):
        """HA reports 'unknown'/'unavailable' when the integration is offline; we should skip those."""
        settings_overrides(
            HOME_ASSISTANT_URL="http://ha.local:8123",
            HOME_ASSISTANT_TOKEN="abc",
            HOME_ASSISTANT_WEATHER_ENTITY="weather.home",
        )
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "state": "unavailable",
            "attributes": {
                "temperature": "unknown",
                "humidity": None,
            },
        }
        fake_response.raise_for_status = MagicMock()
        with patch("jf_sebastian.utils.weather.requests.get", return_value=fake_response):
            data = HomeAssistantWeatherProvider().fetch()

        # No description (state was a sentinel), no temp, no humidity — nothing to render.
        assert data is None

    def test_fetch_celsius_unit_variants(self, settings_overrides):
        """Tolerate 'C', 'celsius', 'Celsius' as well as the canonical '°C'."""
        settings_overrides(
            HOME_ASSISTANT_URL="http://ha.local:8123",
            HOME_ASSISTANT_TOKEN="abc",
            HOME_ASSISTANT_WEATHER_ENTITY="weather.home",
        )
        for unit in ["°C", "C", "celsius", "Celsius"]:
            fake_response = MagicMock()
            fake_response.json.return_value = {
                "state": "sunny",
                "attributes": {"temperature": 0, "temperature_unit": unit},
            }
            fake_response.raise_for_status = MagicMock()
            with patch("jf_sebastian.utils.weather.requests.get", return_value=fake_response):
                data = HomeAssistantWeatherProvider().fetch()
            assert data["temp_f"] == 32.0, f"unit={unit!r} should be treated as Celsius"


class TestManualProvider:
    def test_not_configured_when_blank(self, settings_overrides):
        settings_overrides()
        assert ManualWeatherProvider().is_configured() is False

    def test_returns_description_only(self, settings_overrides):
        settings_overrides(MANUAL_WEATHER="Sunny and 72F")
        data = ManualWeatherProvider().fetch()
        assert data == {"description": "Sunny and 72F"}


class TestProviderFactory:
    def test_explicit_none_returns_none(self, settings_overrides):
        settings_overrides(WEATHER_PROVIDER="none", ZIPCODE="90210")
        assert get_weather_provider() is None

    def test_explicit_choice_overrides_others(self, settings_overrides):
        settings_overrides(
            WEATHER_PROVIDER="manual",
            ZIPCODE="90210",
            MANUAL_WEATHER="Foggy",
        )
        provider = get_weather_provider()
        assert isinstance(provider, ManualWeatherProvider)

    def test_unknown_provider_warns_and_falls_back(self, settings_overrides, caplog):
        settings_overrides(WEATHER_PROVIDER="nonsense", ZIPCODE="90210")
        with caplog.at_level("WARNING"):
            provider = get_weather_provider()
        assert isinstance(provider, WttrWeatherProvider)
        assert any("Unknown WEATHER_PROVIDER" in r.message for r in caplog.records)

    def test_explicit_provider_unconfigured_warns(self, settings_overrides, caplog):
        """User sets WEATHER_PROVIDER=homeassistant but forgets the token."""
        settings_overrides(WEATHER_PROVIDER="homeassistant")
        with caplog.at_level("WARNING"):
            provider = get_weather_provider()
        assert isinstance(provider, HomeAssistantWeatherProvider)
        assert any("not fully configured" in r.message for r in caplog.records)

    def test_auto_picks_homeassistant_first(self, settings_overrides):
        settings_overrides(
            HOME_ASSISTANT_URL="http://ha.local:8123",
            HOME_ASSISTANT_TOKEN="x",
            HOME_ASSISTANT_WEATHER_ENTITY="weather.home",
            ZIPCODE="90210",
            MANUAL_WEATHER="Foggy",
        )
        provider = get_weather_provider()
        assert isinstance(provider, HomeAssistantWeatherProvider)

    def test_auto_falls_to_wttr_when_only_zipcode_set(self, settings_overrides):
        """Backward compatibility: existing ZIPCODE-only setups still get wttr."""
        settings_overrides(ZIPCODE="90210")
        provider = get_weather_provider()
        assert isinstance(provider, WttrWeatherProvider)

    def test_auto_prefers_wttr_over_manual(self, settings_overrides):
        """Manual is opt-in for testing; real-data sources should win in auto mode."""
        settings_overrides(ZIPCODE="90210", MANUAL_WEATHER="Foggy")
        provider = get_weather_provider()
        assert isinstance(provider, WttrWeatherProvider)

    def test_auto_uses_manual_when_only_manual_set(self, settings_overrides):
        settings_overrides(MANUAL_WEATHER="Foggy")
        provider = get_weather_provider()
        assert isinstance(provider, ManualWeatherProvider)

    def test_auto_returns_none_when_nothing_configured(self, settings_overrides):
        settings_overrides()
        assert get_weather_provider() is None


class TestBearingToCompass:
    def test_north(self):
        assert _bearing_to_compass(0) == "N"

    def test_east(self):
        assert _bearing_to_compass(90) == "E"

    def test_south(self):
        assert _bearing_to_compass(180) == "S"

    def test_west(self):
        assert _bearing_to_compass(270) == "W"

    def test_string_passthrough(self):
        assert _bearing_to_compass("WSW") == "WSW"

    def test_none_input_returns_none(self):
        assert _bearing_to_compass(None) is None

    def test_wraps_past_360(self):
        assert _bearing_to_compass(360) == "N"
        assert _bearing_to_compass(720) == "N"
