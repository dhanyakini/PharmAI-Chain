"""Dashboard HTTP endpoints for live operational status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_admin
from app.api.websocket import get_active_websocket_connection_count
from app.core.state import app_state
from app.database.models import Shipment
from app.services.simulation_engine import simulation_task_registry

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def dashboard_summary(
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    q = await session.execute(select(func.count(Shipment.id)))
    shipment_count = int(q.scalar_one() or 0)

    running_shipments = len(simulation_task_registry)
    return {
        "shipment_count": shipment_count,
        "simulation_running_shipments": running_shipments,
        "redis_connected": app_state.redis_connected,
    }


@router.get("/live-state")
async def dashboard_live_state(
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    q = await session.execute(select(func.count(Shipment.id)))
    shipment_count = int(q.scalar_one() or 0)

    return {
        "api_connected": True,
        "websocket_connected": get_active_websocket_connection_count(),
        "redis_connected": app_state.redis_connected,
        "simulation_running": len(simulation_task_registry) > 0,
        "simulation_running_shipments": len(simulation_task_registry),
        "shipment_count": shipment_count,
    }

