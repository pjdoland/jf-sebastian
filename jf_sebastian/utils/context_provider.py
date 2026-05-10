"""
Provides real-world context (date/time, weather, news headlines) for LLM
conversations.

Weather and news are fetched via pluggable providers (see weather.py and
news.py). Each is cached for a configurable TTL (30 min default). The first
cold-miss is fetched synchronously; subsequent stale-cache reads trigger a
single async background refresh and return the stale data immediately.
Failed refreshes set a short retry-after window so a flaky provider doesn't
pile up retry threads.

Weather and news share the same caching shape but each has its own state
(provider singleton, cache, lock, refresh-in-flight flag). Unifying the two
into a generic `CachedAsyncProvider` is a follow-up — keeping them parallel
for now minimizes the chance of regressing the v2.4.0 weather hardening.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional

from jf_sebastian.config import settings
from jf_sebastian.utils.news import NewsProvider, get_news_provider
from jf_sebastian.utils.weather import WeatherProvider, _coerce_float, get_weather_provider

logger = logging.getLogger(__name__)

_RETRY_AFTER_SECONDS = 60   # back off this long after a failed fetch (shared)

# ─── Weather state ────────────────────────────────────────────────────────────
_WEATHER_CACHE_TTL = 1800   # 30 minutes
_weather_cache: Optional[dict] = None
_weather_cache_time: float = 0
_weather_lock = threading.Lock()
_weather_refresh_in_flight: bool = False
_weather_provider: Optional[WeatherProvider] = None
_weather_provider_lock = threading.Lock()

# ─── News state ───────────────────────────────────────────────────────────────
_news_cache: Optional[list[str]] = None
_news_cache_time: float = 0
_news_lock = threading.Lock()
_news_refresh_in_flight: bool = False
_news_provider: Optional[NewsProvider] = None
_news_provider_lock = threading.Lock()


def _news_cache_ttl() -> int:
    """News TTL is configurable at runtime via NEWS_CACHE_TTL_MINUTES."""
    return max(60, int(settings.NEWS_CACHE_TTL_MINUTES) * 60)


# ─── Weather provider singleton + fetch ───────────────────────────────────────

def _get_weather_provider_cached() -> Optional[WeatherProvider]:
    """Lazy-init the weather provider singleton."""
    global _weather_provider
    with _weather_provider_lock:
        if _weather_provider is None:
            _weather_provider = get_weather_provider()
            if _weather_provider:
                logger.info("Weather provider: %s", _weather_provider.name)
            else:
                logger.info(
                    "Weather context disabled (no provider configured). "
                    "Set ZIPCODE, HOME_ASSISTANT_*, or MANUAL_WEATHER to enable."
                )
        return _weather_provider


def warm_weather_cache() -> None:
    """Pre-fetch weather in a background thread so the first conversation doesn't block."""
    provider = _get_weather_provider_cached()
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
    """Fetch fresh weather; HTTP I/O outside the lock so callers don't serialize."""
    global _weather_cache, _weather_cache_time, _weather_refresh_in_flight

    provider = _get_weather_provider_cached()
    if not provider or not provider.is_configured():
        with _weather_lock:
            _weather_refresh_in_flight = False
        return None

    with _weather_lock:
        if _weather_cache and (time.time() - _weather_cache_time) < _WEATHER_CACHE_TTL:
            _weather_refresh_in_flight = False
            return _weather_cache

    try:
        data = provider.fetch()
    except Exception as e:
        logger.warning(
            "Weather provider %s failed: %s: %s",
            provider.name, type(e).__name__, str(e)[:200],
        )
        data = None

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
            _weather_cache_time = time.time() - _WEATHER_CACHE_TTL + _RETRY_AFTER_SECONDS

        _weather_refresh_in_flight = False
        return _weather_cache


def _format_weather(weather: dict) -> str:
    """Render a weather dict into a one-line summary, omitting missing fields."""
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


# ─── News provider singleton + fetch ──────────────────────────────────────────

def _get_news_provider_cached() -> Optional[NewsProvider]:
    """Lazy-init the news provider singleton."""
    global _news_provider
    with _news_provider_lock:
        if _news_provider is None:
            _news_provider = get_news_provider()
            if _news_provider:
                # describe() includes the URL/feed name when available, so a
                # user can grep the log to see exactly where headlines come from.
                logger.info(
                    "News provider: %s. Set NEWS_PROVIDER=none in .env to disable.",
                    _news_provider.describe(),
                )
            else:
                logger.info(
                    "News context disabled (no provider configured). "
                    "Set NEWS_RSS_URL, MANUAL_NEWS, or NEWS_PROVIDER=hackernews to enable."
                )
        return _news_provider


def warm_news_cache() -> None:
    """Pre-fetch news in a background thread so the first conversation doesn't block."""
    provider = _get_news_provider_cached()
    if not provider or not provider.is_configured():
        return

    def _warm_with_retry():
        for _ in range(3):
            if _fetch_news():
                return
            time.sleep(2)
        logger.warning(
            "News pre-warm via %s failed after 3 attempts; headlines will be skipped "
            "until the next successful fetch (toy operation otherwise unaffected).",
            provider.name,
        )

    threading.Thread(target=_warm_with_retry, daemon=True).start()


def _fetch_news() -> Optional[list[str]]:
    """Fetch fresh headlines; HTTP I/O outside the lock so callers don't serialize."""
    global _news_cache, _news_cache_time, _news_refresh_in_flight

    provider = _get_news_provider_cached()
    if not provider or not provider.is_configured():
        with _news_lock:
            _news_refresh_in_flight = False
        return None

    ttl = _news_cache_ttl()
    with _news_lock:
        if _news_cache and (time.time() - _news_cache_time) < ttl:
            _news_refresh_in_flight = False
            return _news_cache

    try:
        data = provider.fetch()
    except Exception as e:
        logger.warning(
            "News provider %s failed: %s: %s",
            provider.name, type(e).__name__, str(e)[:200],
        )
        data = None

    with _news_lock:
        if data:
            _news_cache = data
            _news_cache_time = time.time()
            logger.info(
                "News updated via %s: %d headline(s)", provider.name, len(data),
            )
        else:
            _news_cache_time = time.time() - ttl + _RETRY_AFTER_SECONDS

        _news_refresh_in_flight = False
        return _news_cache


def _format_news(headlines: list[str]) -> str:
    """Render headlines as a bulleted block under a 'Top headlines:' header."""
    bullets = "\n".join(f"- {h}" for h in headlines if h)
    return f"Top headlines:\n{bullets}" if bullets else ""


# ─── Test seam ────────────────────────────────────────────────────────────────

def _reset_provider_for_tests() -> None:
    """Test-internal: reset cached providers/caches so tests can swap settings between cases."""
    global _weather_provider, _weather_cache, _weather_cache_time, _weather_refresh_in_flight
    global _news_provider, _news_cache, _news_cache_time, _news_refresh_in_flight
    with _weather_provider_lock:
        _weather_provider = None
    with _weather_lock:
        _weather_cache = None
        _weather_cache_time = 0
        _weather_refresh_in_flight = False
    with _news_provider_lock:
        _news_provider = None
    with _news_lock:
        _news_cache = None
        _news_cache_time = 0
        _news_refresh_in_flight = False


# ─── Public entry point ───────────────────────────────────────────────────────

def get_realworld_context() -> str:
    """Build a context string with current date/time, weather, and news.

    Uses cached data when available; on cold miss does a synchronous fetch
    so the LLM has data on the first call. On stale cache, returns the stale
    value immediately and triggers a single background refresh per subsystem.
    """
    global _weather_refresh_in_flight, _news_refresh_in_flight

    now = datetime.now()
    parts = [f"Current date and time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}"]

    # Weather
    weather_provider = _get_weather_provider_cached()
    if weather_provider:
        spawn_refresh = False
        with _weather_lock:
            weather = _weather_cache
            cache_stale = (time.time() - _weather_cache_time) >= _WEATHER_CACHE_TTL
            if cache_stale and weather and not _weather_refresh_in_flight:
                _weather_refresh_in_flight = True
                spawn_refresh = True

        if spawn_refresh:
            threading.Thread(target=_fetch_weather, daemon=True).start()
        elif cache_stale and not weather:
            weather = _fetch_weather()

        if weather:
            parts.append(_format_weather(weather))

    # News
    news_provider = _get_news_provider_cached()
    if news_provider:
        ttl = _news_cache_ttl()
        spawn_refresh = False
        with _news_lock:
            news = _news_cache
            cache_stale = (time.time() - _news_cache_time) >= ttl
            if cache_stale and news and not _news_refresh_in_flight:
                _news_refresh_in_flight = True
                spawn_refresh = True

        if spawn_refresh:
            threading.Thread(target=_fetch_news, daemon=True).start()
        elif cache_stale and not news:
            news = _fetch_news()

        if news:
            parts.append(_format_news(news))

    return (
        "The following is real-world context. Use this information to answer "
        "questions about the current time, date, weather, or what's in the news. "
        "Keep these answers short and direct — stay in character.\n"
        + "\n".join(parts)
    )
