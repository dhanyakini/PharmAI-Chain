"""Nearest cold-storage warehouse lookup (shared by agents and simulation)."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WarehouseCandidate


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


async def pick_nearest_cold_storage_warehouse(
    session: AsyncSession,
    *,
    lat: float,
    lng: float,
) -> dict[str, Any] | None:
    """Return the closest `has_cold_storage` row as a JSON-serializable dict, or None."""
    wh_q = await session.execute(
        select(WarehouseCandidate).where(WarehouseCandidate.has_cold_storage == True)  # noqa: E712
    )
    candidates = wh_q.scalars().all()
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda w: haversine_km(lat, lng, float(w.lat), float(w.lng)),
    )
    best = ranked[0]
    return {
        "id": best.id,
        "name": best.name,
        "lat": float(best.lat),
        "lng": float(best.lng),
        "state": best.state,
        "has_cold_storage": best.has_cold_storage,
    }
