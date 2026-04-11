"""Routing service using OSRM demo server to generate road polylines."""

from __future__ import annotations

from typing import Any

import httpx


OSRM_BASE_URL = "https://routing.openstreetmap.de/routed-car/route/v1/driving"


async def generate_route_polyline(
    *,
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
) -> dict[str, Any]:
    """Generate a driving route polyline between two points.

    Returns coordinates in `[lat, lng]` order for frontend friendliness.
    """
    coord_pair = f"{origin_lng},{origin_lat};{destination_lng},{destination_lat}"
    url = f"{OSRM_BASE_URL}/{coord_pair}"

    params = {
        "overview": "full",
        "geometries": "geojson",
    }

    # OSRM is external. In this environment IPv6 can time out, so force IPv4
    # to make routing reliable (no geometry fallback).
    last_exc: Exception | None = None
    for _attempt in range(2):
        try:
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
            async with httpx.AsyncClient(timeout=30, transport=transport) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            routes = data.get("routes") or []
            if not routes:
                raise RuntimeError("No OSRM routes returned")

            route0 = routes[0]
            geometry = route0.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []

            # OSRM geojson coordinates: [lng, lat]
            polyline_lat_lng: list[list[float]] = [[lat, lng] for lng, lat in coordinates]

            distance_km = (route0.get("distance") or 0.0) / 1000.0
            eta_minutes = (route0.get("duration") or 0.0) / 60.0

            return {
                "polyline": polyline_lat_lng,
                "distance_km": float(distance_km),
                "eta_minutes": float(eta_minutes),
            }
        except Exception as e:
            last_exc = e

    raise RuntimeError(f"OSRM routing failed: {last_exc!r}") from last_exc


async def route_truck_to_reroute_target(
    *,
    truck_lat: float,
    truck_lng: float,
    final_destination_lat: float,
    final_destination_lng: float,
    warehouse_candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    """Drive OSRM from truck to staging warehouse when provided, else to final destination."""
    if (
        isinstance(warehouse_candidate, dict)
        and warehouse_candidate.get("lat") is not None
        and warehouse_candidate.get("lng") is not None
    ):
        dest_lat = float(warehouse_candidate["lat"])
        dest_lng = float(warehouse_candidate["lng"])
    else:
        dest_lat = float(final_destination_lat)
        dest_lng = float(final_destination_lng)
    return await generate_route_polyline(
        origin_lat=truck_lat,
        origin_lng=truck_lng,
        destination_lat=dest_lat,
        destination_lng=dest_lng,
    )

