"""
Provides real-world context (date/time, weather) for LLM conversations.

Weather is fetched via a pluggable provider (see weather.py) and cached for
30 minutes. The first cold-miss is fetched synchronously; subsequent stale-cache
reads trigger a single async background refresh and return the stale data
immediately. Failed refreshes set a short retry-after window so a flaky provider
doesn't pile up retry threads.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional

from jf_sebastian.utils.weather import WeatherProvider, _coerce_float, get_weather_provider

logger = logging.getLogger(__name__)

_WEATHER_CACHE_TTL = 1800  # 30 minutes
_RETRY_AFTER_SECONDS = 60   # back off this long after a failed fetch
_weather_cache: Optional[dict] = None
_weather_cache_time: float = 0
_weather_lock = threading.Lock()
_refresh_in_flight: bool = False
_provider: Optional[WeatherProvider] = None
_provider_lock = threading.Lock()


def _get_provider() -> Optional[WeatherProvider]:
    """Lazy-init the weather provider singleton."""
    global _provider
    with _provider_lock:
        if _provider is None:
            _provider = get_weather_provider()
            if _provider:
                logger.info("Weather provider: %s", _provider.name)
            else:
                # No provider configured — give the user feedback they can
                # grep for, since this is the most common silent-misconfig
                # path (typo'd env var name, etc.).
                logger.info(
                    "Weather context disabled (no provider configured). "
                    "Set ZIPCODE, HOME_ASSISTANT_*, or MANUAL_WEATHER to enable."
                )
        return _provider


def _reset_provider_for_tests() -> None:
    """Test-internal: reset cached provider/cache so tests can swap settings between cases."""
    global _provider, _weather_cache, _weather_cache_time, _refresh_in_flight
    with _provider_lock:
        _provider = None
    with _weather_lock:
        _weather_cache = None
        _weather_cache_time = 0
        _refresh_in_flight = False


def warm_weather_cache() -> None:
    """Pre-fetch weather in a background thread so the first conversation doesn't block."""
    provider = _get_provider()
    if not provider or not provider.is_configured():
        return

    def _warm_with_retry():
        for _ in range(3):
            if _fetch_weather():
                return
            time.sleep(2)
        logger.warning(
            "Weather pre-warm via %s failed after 3 attempts; will retry on first conversation",
            provider.name,
        )

    threading.Thread(target=_warm_with_retry, daemon=True).start()


def _fetch_weather() -> Optional[dict]:
    """Fetch fresh weather via the provider, updating the cache.

    The HTTP request runs OUTSIDE `_weather_lock` so a slow network doesn't
    serialize foreground readers behind a background refresh. The lock only
    guards the cache-snapshot reads and writes.

    On success, updates `_weather_cache` and `_weather_cache_time`.
    On failure, bumps `_weather_cache_time` enough to back off `_RETRY_AFTER_SECONDS`
    before the next attempt, preventing tight retry loops against a failing provider.
    Returns the (possibly stale) cache, or None if no cache exists.
    """
    global _weather_cache, _weather_cache_time, _refresh_in_flight

    provider = _get_provider()
    if not provider or not provider.is_configured():
        # Even on this no-op path, make sure no caller leaves the flag set —
        # otherwise a future stale read would never spawn another refresh.
        with _weather_lock:
            _refresh_in_flight = False
        return None

    # Quick freshness check: another caller may have refreshed while we were
    # spawning. Don't waste an HTTP round-trip if so.
    with _weather_lock:
        if _weather_cache and (time.time() - _weather_cache_time) < _WEATHER_CACHE_TTL:
            _refresh_in_flight = False
            return _weather_cache

    # HTTP I/O happens outside the lock so concurrent readers don't block.
    try:
        data = provider.fetch()
    except Exception as e:
        logger.warning(
            "Weather provider %s failed: %s: %s",
            provider.name, type(e).__name__, str(e)[:200],
        )
        data = None

    # Re-acquire the lock only to mutate cache state.
    with _weather_lock:
        if data:
            _weather_cache = data
            _weather_cache_time = time.time()
            logger.info(
                "Weather updated via %s: %s in %s",
                provider.name,
                data.get("description", "?"),
                data.get("location", "unknown"),
            )
        else:
            # Back off so we don't tight-loop against a failing provider.
            _weather_cache_time = time.time() - _WEATHER_CACHE_TTL + _RETRY_AFTER_SECONDS

        _refresh_in_flight = False
        return _weather_cache


def _format_weather(weather: dict) -> str:
    """Render a weather dict into a one-line summary, omitting missing fields.

    Defensive against non-numeric values from third-party providers — coerces
    everything through `_coerce_float` and silently drops fields that can't
    be normalized.
    """
    parts = []
    if weather.get("description"):
        parts.append(str(weather["description"]))

    temp = _coerce_float(weather.get("temp_f"))
    if temp is not None:
        feels = _coerce_float(weather.get("feels_like_f"))
        temp_str = f"{temp}F"
        if feels is not None and feels != temp:
            temp_str += f" (feels like {feels}F)"
        parts.append(temp_str)

    humidity = _coerce_float(weather.get("humidity"))
    if humidity is not None:
        parts.append(f"humidity {humidity}%")

    wind = _coerce_float(weather.get("wind_mph"))
    if wind is not None:
        wind_str = f"wind {wind} mph"
        if weather.get("wind_dir"):
            wind_str += f" {weather['wind_dir']}"
        parts.append(wind_str)

    summary = ", ".join(parts) if parts else "unknown"
    location = weather.get("location")
    return f"Current weather in {location}: {summary}" if location else f"Current weather: {summary}"


def get_realworld_context() -> str:
    """Build a context string with current date/time and weather.

    Uses cached weather data when available; on cold miss does a synchronous
    fetch so the LLM has data on the first call. On stale cache, returns the
    stale value immediately and triggers a single background refresh
    (subsequent stale reads while the refresh is in flight don't spawn more
    threads).
    """
    global _refresh_in_flight

    now = datetime.now()
    parts = [f"Current date and time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}"]

    provider = _get_provider()
    if provider:
        # Single lock acquire snapshots cache state and reserves the refresh
        # slot if a background fetch is needed.
        spawn_refresh = False
        with _weather_lock:
            weather = _weather_cache
            cache_stale = (time.time() - _weather_cache_time) >= _WEATHER_CACHE_TTL
            if cache_stale and weather and not _refresh_in_flight:
                _refresh_in_flight = True
                spawn_refresh = True

        if spawn_refresh:
            threading.Thread(target=_fetch_weather, daemon=True).start()
        elif cache_stale and not weather:
            # Cold miss: blocking fetch so the LLM has data on the first call.
            weather = _fetch_weather()

        if weather:
            parts.append(_format_weather(weather))

    return (
        "The following is real-world context. Use this information to answer "
        "questions about the current time, date, or weather. Keep these answers "
        "short and direct — stay in character.\n"
        + "\n".join(parts)
    )
