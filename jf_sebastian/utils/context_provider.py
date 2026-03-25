"""
Provides real-world context (date/time, weather) for LLM conversations.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional

import requests

from jf_sebastian.config import settings

logger = logging.getLogger(__name__)

_WEATHER_CACHE_TTL = 1800  # 30 minutes
_weather_cache: Optional[dict] = None
_weather_cache_time: float = 0
_weather_lock = threading.Lock()


def warm_weather_cache() -> None:
    """Pre-fetch weather in a background thread so the first conversation doesn't block."""
    if not settings.ZIPCODE:
        return

    def _warm_with_retry():
        for attempt in range(3):
            result = _fetch_weather()
            if result:
                return
            time.sleep(2)
        logger.warning("Weather pre-warm failed after 3 attempts; will retry on first conversation")

    thread = threading.Thread(target=_warm_with_retry, daemon=True)
    thread.start()


def _fetch_weather() -> Optional[dict]:
    """Fetch current weather from wttr.in for the configured zipcode."""
    global _weather_cache, _weather_cache_time

    if not settings.ZIPCODE:
        return None

    with _weather_lock:
        # Re-check inside lock (another thread may have refreshed)
        if _weather_cache and (time.time() - _weather_cache_time) < _WEATHER_CACHE_TTL:
            return _weather_cache

        try:
            response = requests.get(
                f"https://wttr.in/{settings.ZIPCODE}?format=j1",
                timeout=5,
                headers={"User-Agent": "jf-sebastian"}
            )
            response.raise_for_status()
            data = response.json()

            condition = data["current_condition"][0]
            area = data["nearest_area"][0]

            _weather_cache = {
                "location": area["areaName"][0]["value"],
                "temp_f": condition["temp_F"],
                "feels_like_f": condition["FeelsLikeF"],
                "description": condition["weatherDesc"][0]["value"],
                "humidity": condition["humidity"],
                "wind_mph": condition["windspeedMiles"],
                "wind_dir": condition["winddir16Point"],
            }
            _weather_cache_time = time.time()
            logger.info(f"Weather updated: {_weather_cache['temp_f']}F, "
                        f"{_weather_cache['description']} in {_weather_cache['location']}")
            return _weather_cache

        except Exception as e:
            logger.warning(f"Failed to fetch weather: {e}")
            return _weather_cache  # stale cache or None


def get_realworld_context() -> str:
    """Build a context string with current date/time and weather.

    Uses cached weather data only — never blocks on HTTP.
    If the cache is expired, triggers a background refresh for next time.
    """
    now = datetime.now()
    parts = [
        f"Current date and time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}"
    ]

    # Get weather: sync fetch on cold miss (no data at all), async refresh on stale
    weather = _weather_cache
    if settings.ZIPCODE and (not weather or (time.time() - _weather_cache_time) >= _WEATHER_CACHE_TTL):
        if weather:
            # Have stale data — refresh in background, use stale for now
            threading.Thread(target=_fetch_weather, daemon=True).start()
        else:
            # No data at all — sync fetch so LLM has something to work with
            weather = _fetch_weather()

    if weather:
        parts.append(
            f"Current weather in {weather['location']}: "
            f"{weather['description']}, {weather['temp_f']}F "
            f"(feels like {weather['feels_like_f']}F), "
            f"humidity {weather['humidity']}%, "
            f"wind {weather['wind_mph']} mph {weather['wind_dir']}"
        )

    context = "\n".join(parts)
    return (
        f"The following is real-world context. Use this information to answer "
        f"questions about the current time, date, or weather. Keep these answers "
        f"short and direct — stay in character.\n"
        f"{context}"
    )
