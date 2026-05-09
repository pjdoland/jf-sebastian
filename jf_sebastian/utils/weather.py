"""
Weather provider abstraction. Each provider returns a normalized weather dict
with optional fields (location, description, temp_f, feels_like_f, humidity,
wind_mph, wind_dir) so the context formatter can render whatever's available.

Numeric fields (temp_f, feels_like_f, humidity, wind_mph) are always coerced
to float — providers normalize away whatever string/int oddities their upstream
API returns so downstream code only handles `float | None`.
"""

import ipaddress
import logging
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import quote, urlsplit

import requests

from jf_sebastian.config import settings

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 5
# Home Assistant emits "unknown"/"unavailable"/"none" when an entity is offline
_HA_SENTINEL_VALUES = {"unknown", "unavailable", "none", ""}

# Required env vars per provider — used in "selected but not configured" warnings
# so users know exactly what they're missing.
_REQUIRED_VARS = {
    "wttr": "ZIPCODE",
    "homeassistant": "HOME_ASSISTANT_URL, HOME_ASSISTANT_TOKEN, HOME_ASSISTANT_WEATHER_ENTITY",
    "manual": "MANUAL_WEATHER",
}


def _coerce_float(value) -> Optional[float]:
    """Best-effort float conversion; returns None for None/empty/sentinels/non-numeric."""
    if value is None:
        return None
    if isinstance(value, bool):  # bool is an int subclass — refuse it explicitly
        return None
    if isinstance(value, str):
        if value.strip().lower() in _HA_SENTINEL_VALUES:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_private_or_local_host(host: Optional[str]) -> bool:
    """True if host is loopback, RFC1918/link-local, or an mDNS `.local` name."""
    if not host:
        return False
    h = host.lower().strip()
    if h == "localhost" or h.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False  # public DNS name


class WeatherProvider(ABC):
    """Base class for weather data sources."""

    name: str = "abstract"

    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has the settings it needs to attempt a fetch."""

    @abstractmethod
    def fetch(self) -> Optional[dict]:
        """Fetch current weather. Return a normalized dict or None on failure.

        Normalized fields (all optional): location, description, temp_f,
        feels_like_f, humidity, wind_mph, wind_dir.
        """


class WttrWeatherProvider(WeatherProvider):
    """Fetches weather from wttr.in (free, no API key) using a US zipcode."""

    name = "wttr"

    def is_configured(self) -> bool:
        return bool((settings.ZIPCODE or "").strip())

    def fetch(self) -> Optional[dict]:
        zipcode = quote(str(settings.ZIPCODE).strip(), safe="")
        # Default User-Agent (python-requests/X.Y) — don't fingerprint this project to wttr.in
        response = requests.get(
            f"https://wttr.in/{zipcode}?format=j1",
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        # Defensive .get-chain — a successful 200 from wttr can still be a partial body
        condition = (data.get("current_condition") or [{}])[0]
        area = (data.get("nearest_area") or [{}])[0]
        area_name = ((area.get("areaName") or [{}])[0]).get("value")
        desc = ((condition.get("weatherDesc") or [{}])[0]).get("value")

        result = {}
        if area_name:
            result["location"] = area_name
        if desc:
            result["description"] = desc
        temp = _coerce_float(condition.get("temp_F"))
        if temp is not None:
            result["temp_f"] = temp
        feels = _coerce_float(condition.get("FeelsLikeF"))
        if feels is not None:
            result["feels_like_f"] = feels
        humidity = _coerce_float(condition.get("humidity"))
        if humidity is not None:
            result["humidity"] = humidity
        wind = _coerce_float(condition.get("windspeedMiles"))
        if wind is not None:
            result["wind_mph"] = wind
        if condition.get("winddir16Point"):
            result["wind_dir"] = condition["winddir16Point"]
        return result or None


class HomeAssistantWeatherProvider(WeatherProvider):
    """Fetches weather from a Home Assistant weather entity."""

    name = "homeassistant"

    def is_configured(self) -> bool:
        url = (settings.HOME_ASSISTANT_URL or "").strip()
        token = (settings.HOME_ASSISTANT_TOKEN or "").strip()
        entity = (settings.HOME_ASSISTANT_WEATHER_ENTITY or "").strip()
        if not (url and token and entity):
            return False
        if not entity.startswith("weather."):
            logger.warning(
                "HOME_ASSISTANT_WEATHER_ENTITY=%r doesn't look like a weather entity "
                "(expected 'weather.<name>')", entity
            )
            return False
        try:
            parsed = urlsplit(url)
        except ValueError as e:
            logger.warning("HOME_ASSISTANT_URL=%r is unparseable: %s", url, e)
            return False
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            logger.warning(
                "HOME_ASSISTANT_URL=%r is not a valid http(s) URL — refusing to fetch", url
            )
            return False
        # Refuse to send a long-lived bearer token to a non-private host over plain HTTP.
        # Common HA setups are http://homeassistant.local:8123 or http://192.168.x.x;
        # a typo to a public hostname over http would otherwise leak the token.
        if parsed.scheme == "http" and not _is_private_or_local_host(parsed.hostname):
            logger.warning(
                "HOME_ASSISTANT_URL=%r is a non-local host over plain HTTP — refusing "
                "to send bearer token. Use https:// or a private/.local hostname.", url
            )
            return False
        return True

    def fetch(self) -> Optional[dict]:
        url_base = (settings.HOME_ASSISTANT_URL or "").strip().rstrip("/")
        # If the user pasted a URL ending with /api (e.g., copied from HA's API docs),
        # we'd otherwise produce /api/api/states/... and get a confusing 404.
        if url_base.endswith("/api"):
            logger.info(
                "HOME_ASSISTANT_URL ends with '/api'; stripping to avoid '/api/api/...'. "
                "Set HOME_ASSISTANT_URL to the base URL only (e.g., http://ha.local:8123)."
            )
            url_base = url_base[: -len("/api")]
        entity = quote((settings.HOME_ASSISTANT_WEATHER_ENTITY or "").strip(), safe="")
        url = f"{url_base}/api/states/{entity}"
        response = requests.get(
            url,
            timeout=_HTTP_TIMEOUT,
            headers={
                "Authorization": f"Bearer {(settings.HOME_ASSISTANT_TOKEN or '').strip()}",
                "Content-Type": "application/json",
            },
            allow_redirects=False,
        )
        response.raise_for_status()
        state = response.json()
        attrs = state.get("attributes", {}) or {}

        result = {}
        raw_state = (state.get("state") or "").strip().lower()
        if raw_state and raw_state not in _HA_SENTINEL_VALUES:
            result["description"] = state["state"]
        if attrs.get("friendly_name"):
            result["location"] = attrs["friendly_name"]

        unit = (attrs.get("temperature_unit") or "").upper()
        is_celsius = "C" in unit and "F" not in unit  # tolerate "°C", "C", "celsius"
        temp = _coerce_float(attrs.get("temperature"))
        if temp is not None:
            result["temp_f"] = round(temp * 9 / 5 + 32, 1) if is_celsius else temp
        feels = _coerce_float(attrs.get("apparent_temperature"))
        if feels is not None:
            result["feels_like_f"] = round(feels * 9 / 5 + 32, 1) if is_celsius else feels

        humidity = _coerce_float(attrs.get("humidity"))
        if humidity is not None:
            result["humidity"] = humidity

        wind_speed = _coerce_float(attrs.get("wind_speed"))
        if wind_speed is not None:
            wind_unit = (attrs.get("wind_speed_unit") or "").lower()
            if wind_unit in ("km/h", "kph"):
                wind_speed = round(wind_speed * 0.621371, 1)
            elif wind_unit == "m/s":
                wind_speed = round(wind_speed * 2.23694, 1)
            elif wind_unit in ("kn", "knots"):
                wind_speed = round(wind_speed * 1.15078, 1)
            elif wind_unit and wind_unit != "mph":
                logger.debug("Unrecognized HA wind_speed_unit=%r; assuming mph", wind_unit)
            result["wind_mph"] = wind_speed

        bearing = attrs.get("wind_bearing")
        if bearing is not None:
            compass = _bearing_to_compass(bearing)
            if compass:
                result["wind_dir"] = compass

        return result or None


class ManualWeatherProvider(WeatherProvider):
    """Returns a fixed user-provided description (e.g., for offline/testing)."""

    name = "manual"

    def is_configured(self) -> bool:
        return bool((settings.MANUAL_WEATHER or "").strip())

    def fetch(self) -> Optional[dict]:
        text = (settings.MANUAL_WEATHER or "").strip()
        return {"description": text} if text else None


def _bearing_to_compass(bearing) -> Optional[str]:
    """Convert a numeric compass bearing to a 16-point label, or pass through if already a label."""
    if isinstance(bearing, str):
        return bearing
    try:
        deg = float(bearing) % 360
    except (TypeError, ValueError):
        return None
    points = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    return points[int((deg + 11.25) // 22.5) % 16]


_PROVIDERS = {
    cls.name: cls for cls in (WttrWeatherProvider, HomeAssistantWeatherProvider, ManualWeatherProvider)
}
VALID_PROVIDER_NAMES = frozenset(_PROVIDERS.keys())

# Auto-select priority: real-data sources first; manual is opt-in for testing/offline.
_AUTO_PRIORITY = (HomeAssistantWeatherProvider, WttrWeatherProvider, ManualWeatherProvider)


def get_weather_provider() -> Optional[WeatherProvider]:
    """Return the configured weather provider, or None if weather is disabled.

    Selection order:
    1. WEATHER_PROVIDER="none" → disabled.
    2. WEATHER_PROVIDER set to a known name → that provider (warns if not is_configured).
    3. Otherwise (unset or "auto") → first is_configured() provider in priority order:
       homeassistant > wttr > manual. This preserves backward compatibility for
       ZIPCODE-only setups while ensuring `MANUAL_WEATHER` only wins when nothing
       else is configured.
    """
    explicit = (settings.WEATHER_PROVIDER or "").lower().strip()

    if explicit == "none":
        logger.info("WEATHER_PROVIDER=none — weather context disabled")
        return None
    if explicit and explicit != "auto":
        cls = _PROVIDERS.get(explicit)
        if not cls:
            logger.warning(
                "Unknown WEATHER_PROVIDER=%r; valid values: %s. Falling back to auto-selection.",
                explicit, ", ".join(sorted(VALID_PROVIDER_NAMES) + ["none", "auto"]),
            )
        else:
            provider = cls()
            if not provider.is_configured():
                logger.warning(
                    "WEATHER_PROVIDER=%r selected but provider is not fully configured. "
                    "Set: %s. Weather context will be omitted.",
                    explicit, _REQUIRED_VARS.get(explicit, "(see docs)"),
                )
            return provider

    for cls in _AUTO_PRIORITY:
        provider = cls()
        if provider.is_configured():
            return provider
    return None
