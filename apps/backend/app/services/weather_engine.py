"""Weather engine with blizzard zone detection."""

from __future__ import annotations

from typing import Any


# Connecticut bounding polygon (approx).
# Stored as [(lat, lng), ...] for point-in-polygon checks and frontend overlay.
CONNECTICUT_BLIZZARD_ZONE: list[tuple[float, float]] = [
    (41.0, -73.7),
    (41.0, -71.8),
    (42.1, -71.8),
    (42.1, -73.7),
]


def _point_in_polygon(lat: float, lng: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray casting algorithm for point-in-polygon (lat/lng plane)."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        lat_i, lng_i = polygon[i]
        lat_j, lng_j = polygon[j]

        # Check if the edge crosses the horizontal ray from (lat, lng).
        intersects = (lng_i > lng) != (lng_j > lng) and (
            lat < (lat_j - lat_i) * (lng - lng_i) / (lng_j - lng_i + 1e-12) + lat_i
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def get_weather_at(lat: float, lng: float) -> dict[str, Any]:
    in_zone = _point_in_polygon(lat, lng, CONNECTICUT_BLIZZARD_ZONE)

    if in_zone:
        return {
            "weather_state": "blizzard",
            "external_temp_f": 25.0,
            "risk_level": 0.9,
        }

    return {
        "weather_state": "clear",
        "external_temp_f": 50.0,
        "risk_level": 0.2,
    }

