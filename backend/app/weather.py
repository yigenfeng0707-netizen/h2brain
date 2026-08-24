"""H2Brain - Weather Tag Module

Fetches historical weather data from Open-Meteo Archive API (free, no API key).
Tags each trip with weather conditions (temperature, weather code, wind speed)
based on GPS coordinates and trip timestamps.

Used to satisfy T05 enterprise requirement: "weather labels" in working condition identification.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Any

import pandas as pd

logger = logging.getLogger("h2brain.weather")

# Open-Meteo Archive API endpoint
ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"

# WMO weather code -> Chinese label mapping
WMO_CODE_MAP = {
    0: ("晴", "clear"),
    1: ("大部晴", "mostly_clear"),
    2: ("局部多云", "partly_cloudy"),
    3: ("阴", "overcast"),
    45: ("雾", "fog"),
    48: ("冻雾", "freezing_fog"),
    51: ("小毛雨", "light_drizzle"),
    53: ("毛雨", "drizzle"),
    55: ("大毛雨", "heavy_drizzle"),
    56: ("冻毛雨", "freezing_drizzle"),
    57: ("冻雨", "freezing_rain"),
    61: ("小雨", "light_rain"),
    63: ("中雨", "rain"),
    65: ("大雨", "heavy_rain"),
    66: ("冻雨", "freezing_rain"),
    67: ("大冻雨", "heavy_freezing_rain"),
    71: ("小雪", "light_snow"),
    73: ("中雪", "snow"),
    75: ("大雪", "heavy_snow"),
    77: ("霰", "snow_grains"),
    80: ("阵雨", "rain_showers"),
    81: ("中阵雨", "heavy_rain_showers"),
    82: ("大阵雨", "violent_rain_showers"),
    85: ("阵雪", "snow_showers"),
    86: ("大阵雪", "heavy_snow_showers"),
    95: ("雷暴", "thunderstorm"),
    96: ("雷暴伴冰雹", "thunderstorm_hail"),
    99: ("大雷暴伴冰雹", "heavy_thunderstorm_hail"),
}

# Cache: (lat, lon, date_str) -> hourly weather dict
_weather_cache: dict[tuple, dict] = {}


def _wmo_to_label(code: int) -> tuple[str, str]:
    """Convert WMO weather code to (Chinese label, English key)."""
    return WMO_CODE_MAP.get(code, ("未知", "unknown"))


def _fetch_weather_batch(
    lat: float, lon: float, start_date: str, end_date: str
) -> dict | None:
    """Fetch hourly historical weather from Open-Meteo Archive API.

    Args:
        lat: Latitude
        lon: Longitude
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD

    Returns:
        Dict with 'time', 'temperature_2m', 'weathercode', 'windspeed_10m' lists,
        or None on failure.
    """
    # Round coordinates to 2 decimal places for cache efficiency (~1km resolution)
    lat_r = round(lat, 2)
    lon_r = round(lon, 2)
    cache_key = (lat_r, lon_r, start_date, end_date)

    if cache_key in _weather_cache:
        return _weather_cache[cache_key]

    params = (
        f"?latitude={lat_r}"
        f"&longitude={lon_r}"
        f"&start_date={start_date}"
        f"&end_date={end_date}"
        f"&hourly=temperature_2m,weathercode,windspeed_10m"
        f"&timezone=Asia/Shanghai"
        f"&timeformat=unixtime"
    )
    url = ARCHIVE_API_URL + params

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "H2Brain/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        hourly = data.get("hourly", {})
        if not hourly.get("time"):
            logger.warning("No hourly data returned for %s", cache_key)
            return None

        _weather_cache[cache_key] = hourly
        logger.info(
            "Fetched weather for (%.2f, %.2f) %s~%s: %d hours",
            lat_r,
            lon_r,
            start_date,
            end_date,
            len(hourly["time"]),
        )
        return hourly

    except Exception as e:
        logger.error("Weather API error for %s: %s", cache_key, e)
        return None


def _find_nearest_weather(hourly: dict, target_ts: pd.Timestamp) -> dict[str, Any]:
    """Find the nearest hourly weather entry to target timestamp.

    Args:
        hourly: Dict with 'time' (unix timestamps), 'temperature_2m', 'weathercode', 'windspeed_10m'
        target_ts: pandas Timestamp (already in Asia/Shanghai timezone)

    Returns:
        Dict with temperature, weather_code, weather_label, weather_label_en, wind_speed
    """
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    codes = hourly.get("weathercode", [])
    winds = hourly.get("windspeed_10m", [])

    if not times:
        return _default_weather()

    # Convert target to unix timestamp
    if hasattr(target_ts, "timestamp"):
        target_unix = int(target_ts.timestamp())
    else:
        target_unix = int(target_ts)

    # Find nearest hour
    best_idx = 0
    best_diff = abs(times[0] - target_unix)
    for i, t in enumerate(times):
        diff = abs(t - target_unix)
        if diff < best_diff:
            best_diff = diff
            best_idx = i

    code = (
        int(codes[best_idx])
        if best_idx < len(codes) and codes[best_idx] is not None
        else -1
    )
    label_cn, label_en = _wmo_to_label(code)

    return {
        "temperature": round(float(temps[best_idx]), 1)
        if best_idx < len(temps) and temps[best_idx] is not None
        else None,
        "weather_code": code,
        "weather_label": label_cn,
        "weather_label_en": label_en,
        "wind_speed": round(float(winds[best_idx]), 1)
        if best_idx < len(winds) and winds[best_idx] is not None
        else None,
    }


def _default_weather() -> dict[str, Any]:
    """Return default weather when API fails."""
    return {
        "temperature": None,
        "weather_code": -1,
        "weather_label": "未知",
        "weather_label_en": "unknown",
        "wind_speed": None,
    }


def tag_trip_weather(trip: pd.DataFrame) -> dict[str, Any]:
    """Fetch weather data for a trip and return weather summary.

    Samples weather at trip start, mid, and end points.

    Args:
        trip: DataFrame with 'timestamp', 'gps_lat', 'gps_lon' columns

    Returns:
        Dict with:
        - weather_start: weather at trip start
        - weather_mid: weather at trip midpoint
        - weather_end: weather at trip end
        - avg_temperature: mean temperature across samples
        - weather_summary: concise string like "晴 28-33°C"
    """
    if os.environ.get("H2BRAIN_DISABLE_WEATHER", "") == "1":
        return {
            "weather_summary": None,
            "avg_temperature": None,
            "weather_start": None,
            "weather_mid": None,
            "weather_end": None,
        }

    valid_gps = trip.dropna(subset=["gps_lat", "gps_lon"])
    valid_gps = valid_gps[(valid_gps["gps_lat"] != 0) & (valid_gps["gps_lon"] != 0)]

    if len(valid_gps) == 0:
        return {
            "weather_start": _default_weather(),
            "weather_mid": _default_weather(),
            "weather_end": _default_weather(),
            "avg_temperature": None,
            "weather_summary": "无GPS数据",
        }

    start_ts = trip["timestamp"].iloc[0]
    end_ts = trip["timestamp"].iloc[-1]
    mid_idx = len(trip) // 2
    mid_ts = trip["timestamp"].iloc[mid_idx]

    # Get GPS at start, mid, end
    start_row = valid_gps.iloc[0]
    valid_gps.iloc[-1]
    mid_row = valid_gps.iloc[len(valid_gps) // 2]

    # Date range for API (may span multiple days)
    start_date = start_ts.strftime("%Y-%m-%d")
    end_date = end_ts.strftime("%Y-%m-%d")

    # Use start GPS for entire trip (trips are typically <1 day, same region)
    lat = float(start_row["gps_lat"])
    lon = float(start_row["gps_lon"])

    hourly = _fetch_weather_batch(lat, lon, start_date, end_date)
    if hourly is None:
        # Try mid GPS
        hourly = _fetch_weather_batch(
            float(mid_row["gps_lat"]),
            float(mid_row["gps_lon"]),
            start_date,
            end_date,
        )

    if hourly is None:
        return {
            "weather_start": _default_weather(),
            "weather_mid": _default_weather(),
            "weather_end": _default_weather(),
            "avg_temperature": None,
            "weather_summary": "天气数据获取失败",
        }

    w_start = _find_nearest_weather(hourly, start_ts)
    w_mid = _find_nearest_weather(hourly, mid_ts)
    w_end = _find_nearest_weather(hourly, end_ts)

    # Compute summary
    temps = [
        w["temperature"]
        for w in [w_start, w_mid, w_end]
        if w["temperature"] is not None
    ]
    avg_temp = round(sum(temps) / len(temps), 1) if temps else None

    # Use the most common weather label
    labels = [w["weather_label"] for w in [w_start, w_mid, w_end]]
    # Pick the most frequent label, fallback to start
    from collections import Counter

    label_counts = Counter(labels)
    main_label = label_counts.most_common(1)[0][0]

    if avg_temp is not None and temps:
        temp_range = f"{min(temps):.0f}-{max(temps):.0f}C"
        weather_summary = f"{main_label} {temp_range}"
    else:
        weather_summary = main_label

    return {
        "weather_start": w_start,
        "weather_mid": w_mid,
        "weather_end": w_end,
        "avg_temperature": avg_temp,
        "weather_summary": weather_summary,
    }


def tag_trip_weather_cached(trip: pd.DataFrame) -> dict[str, Any]:
    """Wrapper with rate limiting for batch processing."""
    result = tag_trip_weather(trip)
    time.sleep(0.3)  # Rate limit: ~3 requests/sec
    return result
