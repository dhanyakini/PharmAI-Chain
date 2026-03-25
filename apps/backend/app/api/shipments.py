"""Shipment CRUD (auth protected) including cascade-safe deletion."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_admin
from app.database.models import (
    InterventionLog,
    LifecycleEventLog,
    RouteHistory,
    Shipment,
    ShipmentStatus,
    TelemetryLog,
)
from app.services.pubsub_service import CHANNEL_LIFECYCLE, RedisPubSub, get_redis_client

router = APIRouter(prefix="/shipments", tags=["shipments"])


class ShipmentCreateRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    truck_name: str = Field(min_length=1, max_length=128)
    cargo_type: str = "insulin"
    target_temp_low_f: float = 35.0
    target_temp_high_f: float = 77.0


class ShipmentResponse(BaseModel):
    id: int
    shipment_code: str
    status: ShipmentStatus
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    truck_name: str
    current_lat: float | None
    current_lng: float | None
    target_temp_low: float
    target_temp_high: float


def _shipment_to_response(s: Shipment) -> ShipmentResponse:
    return ShipmentResponse(
        id=s.id,
        shipment_code=s.shipment_code,
        status=s.status,
        origin_lat=s.origin_lat,
        origin_lng=s.origin_lng,
        destination_lat=s.destination_lat,
        destination_lng=s.destination_lng,
        truck_name=s.truck_name,
        current_lat=s.current_lat,
        current_lng=s.current_lng,
        target_temp_low=s.target_temp_low,
        target_temp_high=s.target_temp_high,
    )


@router.get("", response_model=list[ShipmentResponse])
async def list_shipments(
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[ShipmentResponse]:
    q = await session.execute(select(Shipment).order_by(Shipment.created_at.desc()))
    shipments = q.scalars().all()
    return [_shipment_to_response(s) for s in shipments]


@router.get("/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: int,
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ShipmentResponse:
    q = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = q.scalar_one_or_none()
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    return _shipment_to_response(shipment)


@router.post("", response_model=ShipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_shipment(
    req: ShipmentCreateRequest,
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ShipmentResponse:
    shipment_code = uuid4().hex
    shipment = Shipment(
        shipment_code=shipment_code,
        cargo_type=req.cargo_type,
        origin_lat=req.origin_lat,
        origin_lng=req.origin_lng,
        destination_lat=req.destination_lat,
        destination_lng=req.destination_lng,
        truck_name=req.truck_name,
        status=ShipmentStatus.created,
        current_lat=req.origin_lat,
        current_lng=req.origin_lng,
        target_temp_low=req.target_temp_low_f,
        target_temp_high=req.target_temp_high_f,
    )
    session.add(shipment)
    await session.commit()
    await session.refresh(shipment)
    return _shipment_to_response(shipment)


async def _cancel_simulation_worker_if_running(shipment_id: int) -> None:
    """Best-effort cancellation for a simulation worker (if already implemented)."""
    try:
        from app.services.simulation_engine import simulation_task_registry

        task = simulation_task_registry.pop(shipment_id, None)
        if task is not None:
            task.cancel()
    except Exception:
        # Simulation engine may not be implemented yet, or registry key may differ.
        return


@router.delete("/{shipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shipment(
    shipment_id: int,
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    # Cancel worker first so it doesn't race with deletion.
    await _cancel_simulation_worker_if_running(shipment_id)

    redis_client = None
    try:
        redis_client = get_redis_client()
        # Best-effort: simulation state cache key convention.
        await redis_client.delete(f"simulation_state:{shipment_id}")
    except Exception:
        pass

    async with session.begin():
        q = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
        shipment = q.scalar_one_or_none()
        if shipment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

        # Explicit deletes keep behavior deterministic even if ORM relationship cascades change.
        await session.execute(delete(TelemetryLog).where(TelemetryLog.shipment_id == shipment_id))
        await session.execute(delete(InterventionLog).where(InterventionLog.shipment_id == shipment_id))
        await session.execute(delete(RouteHistory).where(RouteHistory.shipment_id == shipment_id))
        await session.execute(delete(LifecycleEventLog).where(LifecycleEventLog.shipment_id == shipment_id))
        await session.execute(delete(Shipment).where(Shipment.id == shipment_id))

    # Emit deletion lifecycle event over Redis for realtime UI updates.
    try:
        if redis_client is not None:
            pubsub = RedisPubSub(redis_client)
            msg = {
                "type": "lifecycle_event",
                "shipment_id": shipment_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {"event_name": "shipment_deleted"},
            }
            await pubsub.publish_json(CHANNEL_LIFECYCLE, msg)
    except Exception:
        pass
    finally:
        if redis_client is not None:
            try:
                await redis_client.close()
            except Exception:
                pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{shipment_id}/telemetry")
async def get_shipment_telemetry(
    shipment_id: int,
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    limit: int = 300,
) -> list[dict[str, Any]]:
    q = await session.execute(
        select(TelemetryLog)
        .where(TelemetryLog.shipment_id == shipment_id)
        .order_by(TelemetryLog.timestamp.desc())
        .limit(limit)
    )
    logs = q.scalars().all()
    return [
        {
            "id": t.id,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            "lat": t.lat,
            "lng": t.lng,
            "internal_temp": t.internal_temp,
            "external_temp": t.external_temp,
            "weather_state": t.weather_state,
            "route_segment": t.route_segment,
            "risk_score": t.risk_score,
            "raw_payload": t.raw_payload_json,
        }
        for t in logs
    ]


@router.get("/{shipment_id}/interventions")
async def get_shipment_interventions(
    shipment_id: int,
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    limit: int = 300,
) -> list[dict[str, Any]]:
    q = await session.execute(
        select(InterventionLog)
        .where(InterventionLog.shipment_id == shipment_id)
        .order_by(InterventionLog.timestamp.desc())
        .limit(limit)
    )
    logs = q.scalars().all()
    return [
        {
            "id": i.id,
            "timestamp": i.timestamp.isoformat() if i.timestamp else None,
            "agent_role": i.agent_role,
            "trigger_reason": i.trigger_reason,
            "reasoning_trace": i.reasoning_trace,
            "action_taken": i.action_taken,
            "confidence_score": i.confidence_score,
            "suggested_route": i.suggested_route_json,
            "raw_model_output": i.raw_model_output_json,
        }
        for i in logs
    ]

