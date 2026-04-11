"""Live weather (OpenWeather) + DB-backed blizzard simulation scenarios."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models import BlizzardScenario

log = logging.getLogger(__name__)

# (rounded_lat, rounded_lng) -> (expires_monotonic, payload)
_weather_cache: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}


def _round_coord(x: float, places: int = 3) -> float:
    return round(x, places)


def static_fallback_weather(lat: float, lng: float) -> dict[str, Any]:
    """Deterministic mild ambient when no API key or provider failure."""
    # Very rough latitude-based outdoor feel (not meteorology — dev fallback only).
    base = 45.0 + min(25.0, max(-15.0, (35.0 - abs(lat)) * 0.8))
    return {
        "weather_state": "clear",
        "external_temp_f": float(base),
        "risk_level": 0.2,
        "source": "fallback",
        "wind_speed_mph": 5.0,
        "visibility_miles": 10.0,
        "provider_detail": {"lat": lat, "lng": lng},
    }


def _owm_risk_and_state(main_lower: str, temp_f: float, wind_mph: float) -> tuple[str, float]:
    risk = 0.2
    state = "clear"
    if main_lower in ("snow",):
        state = "snow"
        risk = max(risk, 0.65)
    if main_lower in ("rain", "drizzle", "thunderstorm"):
        state = "precipitation"
        risk = max(risk, 0.45)
    if main_lower in ("mist", "fog", "haze", "smoke"):
        state = "reduced_visibility"
        risk = max(risk, 0.4)
    if main_lower in ("clouds",):
        state = "clouds"
    if temp_f <= 32.0:
        risk = min(1.0, risk + 0.25)
    if wind_mph >= 35.0:
        risk = min(1.0, risk + 0.2)
        if main_lower == "snow" and wind_mph >= 35.0:
            state = "blizzard"
            risk = min(1.0, max(risk, 0.85))
    return state, float(risk)


async def fetch_live_weather_openweather(lat: float, lng: float) -> dict[str, Any]:
    settings = get_settings()
    key = (settings.openweather_api_key or "").strip()
    if not key:
        return static_fallback_weather(lat, lng)

    rk = (_round_coord(lat), _round_coord(lng))
    now = time.monotonic()
    cached = _weather_cache.get(rk)
    if cached and cached[0] > now:
        out = dict(cached[1])
        out["source"] = "openweather_cache"
        return out

    params = {
        "lat": lat,
        "lon": lng,
        "appid": key,
        "units": "imperial",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(settings.openweather_base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("OpenWeather request failed: %s", e)
        return static_fallback_weather(lat, lng)

    main_block = (data.get("weather") or [{}])[0]
    main = str(main_block.get("main", "")).lower()
    wind = data.get("wind") or {}
    wind_mph = float(wind.get("speed") or 0.0)
    temp_f = float((data.get("main") or {}).get("temp") or 50.0)
    visibility_m = data.get("visibility")
    visibility_miles = float(visibility_m) / 1609.34 if visibility_m is not None else None

    state, risk = _owm_risk_and_state(main, temp_f, wind_mph)
    out = {
        "weather_state": state,
        "external_temp_f": temp_f,
        "risk_level": risk,
        "source": "openweather",
        "wind_speed_mph": wind_mph,
        "visibility_miles": visibility_miles,
        "provider_detail": {
            "id": main_block.get("id"),
            "main": main_block.get("main"),
            "description": main_block.get("description"),
        },
    }
    ttl = max(30.0, float(settings.weather_cache_ttl_seconds))
    _weather_cache[rk] = (now + ttl, dict(out))
    return out


async def load_blizzard_scenario(session: AsyncSession, scenario_id: int) -> dict[str, Any] | None:
    q = await session.execute(select(BlizzardScenario).where(BlizzardScenario.id == scenario_id))
    row = q.scalar_one_or_none()
    if row is None:
        return None
    extra = row.extra_json if isinstance(row.extra_json, dict) else {}
    return {
        "weather_state": row.weather_state,
        "external_temp_f": float(row.external_temp_f),
        "risk_level": float(row.risk_level),
        "source": "blizzard_scenario",
        "blizzard_scenario_id": row.id,
        "blizzard_scenario_slug": row.slug,
        "wind_speed_mph": float(row.wind_speed_mph) if row.wind_speed_mph is not None else None,
        "visibility_miles": float(row.visibility_miles) if row.visibility_miles is not None else None,
        "precip_type": row.precip_type,
        "synopsis": row.synopsis,
        "provider_detail": {"name": row.name, **extra},
    }


async def resolve_weather_for_simulation(
    session: AsyncSession,
    lat: float,
    lng: float,
    *,
    blizzard_scenario_id: int | None,
) -> dict[str, Any]:
    """If a DB scenario is active, use it; otherwise use live OpenWeather (or fallback)."""
    if blizzard_scenario_id is not None:
        scenario = await load_blizzard_scenario(session, blizzard_scenario_id)
        if scenario is not None:
            return scenario
        log.warning("blizzard_scenario_id=%s not found; using live weather", blizzard_scenario_id)
    return await fetch_live_weather_openweather(lat, lng)
