import time
import logging
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import httpx

logger = logging.getLogger(__name__)

# 30-minute in-memory cache keyed by (round(lat, 2), round(lng, 2))
_WEATHER_CACHE: dict[tuple[float, float], tuple[float, dict]] = {}
_LOCATION_CACHE: dict[tuple[float, float], tuple[float, str]] = {}
CACHE_TTL_SECONDS = 1800  # 30 mins


def fetch_location_name(lat: float, lng: float, timeout_s: float = 1.5) -> str:
    """
    Reverse-geocodes lat/lng to a readable place name (e.g. "Noida, Uttar Pradesh")
    using Nominatim (OpenStreetMap, no key). Returns "" on failure. Cached 30 min.
    """
    key = (round(lat, 2), round(lng, 2))
    now = time.time()
    if key in _LOCATION_CACHE:
        cached_time, cached_val = _LOCATION_CACHE[key]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_val

    name = ""
    try:
        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat}&lon={lng}&format=jsonv2&zoom=12"
        )
        headers = {"User-Agent": "CareCompass/1.0 (demo health navigation app)"}
        with httpx.Client(timeout=timeout_s) as client:
            res = client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                addr = data.get("address") or {}
                raw_parts = [p for p in (addr.get("city") or addr.get("town"), addr.get("state")) if p]
                if not raw_parts:
                    raw_parts = [p for p in (data.get("name"), addr.get("state")) if p]
                parts = []
                for p in raw_parts:
                    if p not in parts:
                        parts.append(p)
                name = ", ".join(parts)
    except Exception as e:
        logger.debug(f"Nominatim reverse geocoding failed: {e}")

    _LOCATION_CACHE[key] = (now, name)
    return name


def local_time_str(dt: datetime) -> str:
    """'10:30 PM' style display of the resolved local time."""
    return dt.strftime("%I:%M %p").lstrip("0")


def parse_client_time(client_time_str: str | None) -> datetime:
    """
    Parses client ISO 8601 string with timezone offset.
    Falls back to current Asia/Kolkata (+05:30) time.
    """
    if client_time_str:
        try:
            # Handle ISO formats like 2026-07-15T14:30:00+05:30 or Z
            clean_str = client_time_str.replace("Z", "+00:00")
            return datetime.fromisoformat(clean_str)
        except Exception:
            pass

    kolkata_tz = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(kolkata_tz)


def season_display(season: str) -> str:
    """Human-readable season name (no underscores)."""
    return {
        "winter": "Winter",
        "summer": "Summer",
        "monsoon": "Monsoon",
        "post_monsoon": "Post-monsoon",
    }.get(season, str(season).replace("_", " ").capitalize())


def get_north_india_season(dt: datetime) -> str:
    """
    Determines season for North India from month & day:
    - winter: Dec-Feb (months 12, 1, 2)
    - summer: Mar to mid-Jun (months 3, 4, 5, and 1-15 of month 6)
    - monsoon: mid-Jun to Sep (16-30 of month 6, months 7, 8, 9)
    - post_monsoon: Oct-Nov (months 10, 11)
    """
    m = dt.month
    d = dt.day

    if m in (12, 1, 2):
        return "winter"
    elif m in (3, 4, 5) or (m == 6 and d <= 15):
        return "summer"
    elif (m == 6 and d > 15) or m in (7, 8, 9):
        return "monsoon"
    else:
        return "post_monsoon"


def fetch_open_meteo_data(lat: float, lng: float, timeout_s: float = 1.5) -> dict:
    """
    Fetches Open-Meteo weather forecast and air quality concurrently using httpx.
    Caches for 30 minutes keyed by (round(lat, 2), round(lng, 2)).
    Returns empty dict on timeout or failure.
    """
    cache_key = (round(lat, 2), round(lng, 2))
    now = time.time()
    if cache_key in _WEATHER_CACHE:
        cached_time, cached_val = _WEATHER_CACHE[cache_key]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_val

    forecast_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}"
        "&current=temperature_2m,relative_humidity_2m,precipitation,weather_code"
    )
    aqi_url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lng}"
        "&current=us_aqi,pm2_5"
    )

    data = {
        "temperature_c": None,
        "humidity": None,
        "precipitation_mm": None,
        "weather_code": None,
        "aqi": None,
        "pm2_5": None,
    }

    def fetch_url(url: str):
        try:
            with httpx.Client(timeout=timeout_s) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return res.json().get("current", {})
        except Exception as e:
            logger.debug(f"Open-Meteo call to {url} failed: {e}")
        return {}

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_f = executor.submit(fetch_url, forecast_url)
            future_a = executor.submit(fetch_url, aqi_url)

            fc = future_f.result()
            aq = future_a.result()

            if fc:
                data["temperature_c"] = fc.get("temperature_2m")
                data["humidity"] = fc.get("relative_humidity_2m")
                data["precipitation_mm"] = fc.get("precipitation")
                data["weather_code"] = fc.get("weather_code")

            if aq:
                data["aqi"] = aq.get("us_aqi")
                data["pm2_5"] = aq.get("pm2_5")

        if any(v is not None for v in data.values()):
            _WEATHER_CACHE[cache_key] = (now, data)
    except Exception as e:
        logger.warning(f"Error fetching Open-Meteo data: {e}")

    return data


def get_context(
    lat: float | None = None,
    lng: float | None = None,
    client_time_str: str | None = None,
) -> dict:
    """
    Builds context: {season, local_hour, is_night, temperature_c, humidity,
    precipitation_mm, weather_code, aqi, tags[], summary}.
    On weather failure or missing location, returns date/time/season fields safely.
    """
    dt = parse_client_time(client_time_str)
    season = get_north_india_season(dt)
    local_hour = dt.hour
    is_night = local_hour >= 22 or local_hour < 6

    context = {
        "season": season,
        "local_hour": local_hour,
        "is_night": is_night,
        "local_time_str": local_time_str(dt),
        "location_name": "",
        "temperature_c": None,
        "humidity": None,
        "precipitation_mm": None,
        "weather_code": None,
        "aqi": None,
        "tags": [],
        "summary": "",
    }

    tags = []
    if season == "monsoon":
        tags.append("monsoon_season")
    if is_night:
        tags.append("night_time")

    # Fetch weather + place name if lat/lng available
    if lat is not None and lng is not None:
        context["location_name"] = fetch_location_name(lat, lng)
        weather_data = fetch_open_meteo_data(lat, lng)
        context.update(weather_data)

        temp = weather_data.get("temperature_c")
        humidity = weather_data.get("humidity")
        precip = weather_data.get("precipitation_mm")
        w_code = weather_data.get("weather_code")
        aqi = weather_data.get("aqi")

        # Tags definition
        if temp is not None:
            if temp >= 40.0:
                tags.append("heat_wave")
            elif temp <= 6.0:
                tags.append("cold_wave")

        if temp is not None and humidity is not None:
            if temp >= 32.0 and humidity >= 70:
                tags.append("hot_humid")

        if precip is not None and precip >= 1.0:
            tags.append("rainy")
        elif w_code in [51, 53, 55, 61, 63, 65, 80, 81, 82, 95]:
            tags.append("rainy")

        if aqi is not None and aqi >= 200:
            tags.append("poor_air")

    # Deduplicate tags
    context["tags"] = sorted(list(set(tags)))

    # Human-readable summary
    summary_parts = []
    if context["location_name"]:
        summary_parts.append(context["location_name"])
    summary_parts.append(season_display(season))
    if context["temperature_c"] is not None:
        summary_parts.append(f"{round(context['temperature_c'])}°C")
    if "hot_humid" in tags:
        summary_parts.append("Humid")
    elif "rainy" in tags:
        summary_parts.append("Rainy")
    if context["aqi"] is not None:
        summary_parts.append(f"AQI {round(context['aqi'])}")

    context["summary"] = " · ".join(summary_parts)
    return context
