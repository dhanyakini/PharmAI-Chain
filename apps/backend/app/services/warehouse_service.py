"""Nearest cold-storage warehouse lookup (shared by agents and simulation)."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WarehouseCandidate


def nullify_warehouse_if_final_is_as_close_or_closer(
    *,
    truck_lat: float,
    truck_lng: float,
    final_lat: float,
    final_lng: float,
    warehouse: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Drop staging warehouse when the original destination is no farther (straight-line) than the warehouse.

    If distance to final <= distance to warehouse, the truck should continue toward the initial destination
    instead of diverting to staging.
    """
    if warehouse is None:
        return None
    lat_w, lng_w = warehouse.get("lat"), warehouse.get("lng")
    if lat_w is None or lng_w is None:
        return warehouse
    fd = haversine_km(truck_lat, truck_lng, float(final_lat), float(final_lng))
    wd = haversine_km(truck_lat, truck_lng, float(lat_w), float(lng_w))
    if fd <= wd:
        return None
    return warehouse


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _warehouse_to_dict(w: WarehouseCandidate, *, straight_line_km: float) -> dict[str, Any]:
    return {
        "id": w.id,
        "name": w.name,
        "lat": float(w.lat),
        "lng": float(w.lng),
        "state": w.state,
        "has_cold_storage": w.has_cold_storage,
        "capacity_units": int(w.capacity_units or 0),
        "straight_line_km": round(straight_line_km, 3),
    }


async def list_ranked_cold_storage_warehouses(
    session: AsyncSession,
    *,
    lat: float,
    lng: float,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Cold-storage rows ranked by straight-line distance from `(lat, lng)`, newest fields for staging agent."""
    wh_q = await session.execute(
        select(WarehouseCandidate).where(WarehouseCandidate.has_cold_storage == True)  # noqa: E712
    )
    candidates = wh_q.scalars().all()
    if not candidates:
        return []
    ranked = sorted(
        candidates,
        key=lambda w: haversine_km(lat, lng, float(w.lat), float(w.lng)),
    )
    out: list[dict[str, Any]] = []
    for w in ranked[: max(1, limit)]:
        d = haversine_km(lat, lng, float(w.lat), float(w.lng))
        out.append(_warehouse_to_dict(w, straight_line_km=d))
    return out


async def pick_nearest_cold_storage_warehouse(
    session: AsyncSession,
    *,
    lat: float,
    lng: float,
) -> dict[str, Any] | None:
    """Return the closest `has_cold_storage` row as a JSON-serializable dict, or None."""
    ranked = await list_ranked_cold_storage_warehouses(session, lat=lat, lng=lng, limit=1)
    if not ranked:
        return None
    wh = ranked[0]
    return {k: v for k, v in wh.items() if k != "straight_line_km"}
