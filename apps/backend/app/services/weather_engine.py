"""Weather helpers.

Simulation uses `weather_service.resolve_weather_for_simulation` (OpenWeather + DB scenarios).
This module keeps a small sync fallback for any legacy callers.
"""

from __future__ import annotations

from typing import Any


def get_weather_at(lat: float, lng: float) -> dict[str, Any]:
    """Sync fallback only — no HTTP. Prefer async `weather_service` in the simulation loop."""
    from app.services.weather_service import static_fallback_weather

    return static_fallback_weather(lat, lng)
