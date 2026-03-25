"""Simulation controller endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_admin
from app.database.models import (
    InterventionLog,
    LifecycleEventLog,
    RouteHistory,
    Shipment,
    ShipmentStatus,
    WarehouseCandidate,
    TelemetryLog,
    utcnow,
)
from app.services.lifecycle_service import emit_lifecycle_event
from app.services.pubsub_service import get_redis_client
from app.services.routing_service import generate_route_polyline
from app.services.simulation_engine import (
    apply_reroute_to_running_shipment,
    simulation_task_registry,
    simulation_runtime_registry,
    stop_simulation_worker,
    start_simulation_worker,
)

router = APIRouter(prefix="/simulation", tags=["simulation"])


class SimulationActionResponse(BaseModel):
    shipment_id: int
    status: str


def _timeline_entry_from_event(row: LifecycleEventLog) -> dict[str, Any]:
    agent_role = None
    event_name = row.event
    if event_name.endswith("_agent_called"):
        agent_role = event_name.replace("_agent_called", "")
    elif event_name.endswith("_decision_selected"):
        agent_role = event_name.replace("_decision_selected", "")

    payload = row.payload_json or {}
    description = None
    if "reasoning_trace" in payload:
        description = payload.get("reasoning_trace")
    elif "internal_temp_f" in payload:
        description = f"Internal temperature: {payload.get('internal_temp_f')}F"
    elif "weather_state" in payload:
        description = f"Weather state: {payload.get('weather_state')}"
    elif "event_name" in payload:
        description = payload.get("event_name")

    return {
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "event_name": event_name,
        "agent_role": agent_role,
        "description": description,
        "payload": payload,
    }


@router.post("/start/{shipment_id}", response_model=SimulationActionResponse)
async def start_simulation(
    shipment_id: int,
    _: Any = Depends(require_admin),
) -> SimulationActionResponse:
    try:
        await start_simulation_worker(shipment_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return SimulationActionResponse(shipment_id=shipment_id, status="started")


@router.post("/stop/{shipment_id}", response_model=SimulationActionResponse)
async def stop_simulation(
    shipment_id: int,
    _: Any = Depends(require_admin),
) -> SimulationActionResponse:
    await stop_simulation_worker(shipment_id)
    return SimulationActionResponse(shipment_id=shipment_id, status="stopping")


@router.post("/confirm-reroute/{shipment_id}", response_model=SimulationActionResponse)
async def confirm_reroute(
    shipment_id: int,
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> SimulationActionResponse:
    runtime = simulation_runtime_registry.get(shipment_id)
    if runtime is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Simulation not running")
    if runtime.pending_reroute is None or not runtime.pending_reroute.get("reroute_suggested"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No reroute suggestion pending")

    # Identify current truck coordinate from the running simulation.
    current_lat = float(runtime.truck_lat)
    current_lng = float(runtime.truck_lng)

    # Current destination comes from shipment.
    shipment_q = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = shipment_q.scalar_one_or_none()
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    await emit_lifecycle_event(
        shipment_id=shipment_id,
        event_name="reroute_confirmed",
        payload={"warehouse_candidate": runtime.pending_reroute.get("warehouse_candidate")},
    )

    try:
        preview_polyline = runtime.pending_reroute.get("proposed_remaining_polyline")
        if isinstance(preview_polyline, list) and preview_polyline:
            remaining_polyline = [[float(p[0]), float(p[1])] for p in preview_polyline]
            alt = {
                "distance_km": runtime.pending_reroute.get("proposed_distance_km"),
                "eta_minutes": runtime.pending_reroute.get("proposed_eta_minutes"),
            }
        else:
            # Alternate route only for remaining path: current -> final destination.
            alt = await generate_route_polyline(
                origin_lat=current_lat,
                origin_lng=current_lng,
                destination_lat=float(shipment.destination_lat),
                destination_lng=float(shipment.destination_lng),
            )
            remaining_polyline = alt["polyline"]
        if not remaining_polyline:
            raise RuntimeError("Alternate route empty")
        remaining_polyline[0] = [current_lat, current_lng]

        # Prefix for DB/visualization (keep what already traveled).
        polyline = runtime.route_polyline
        if not polyline:
            raise RuntimeError("Current route polyline missing")
        seg_idx = int(runtime.segment_idx)
        prefix = polyline[: seg_idx + 1]
        if prefix:
            prefix[-1] = [current_lat, current_lng]
        full_polyline = prefix + remaining_polyline[1:]

        # Persist new route + update shipment status atomically.
        async with session.begin():
            shipment.status = ShipmentStatus.rerouted
            shipment.current_lat = current_lat
            shipment.current_lng = current_lng
            session.add(shipment)

            rh = RouteHistory(
                shipment_id=shipment_id,
                timestamp=utcnow(),
                route_name="reroute_applied",
                reason="user_confirmed",
                polyline_json=full_polyline,
                distance_km=alt["distance_km"],
                eta_minutes=alt["eta_minutes"],
            )
            session.add(rh)

        # Update running worker to continue from the current position (no teleporting).
        await apply_reroute_to_running_shipment(shipment_id, remaining_polyline)
        async with runtime.lock:
            runtime.shipment_status = ShipmentStatus.rerouted
            runtime.pending_reroute = None
            runtime.paused_for_reroute_confirmation = False

        await emit_lifecycle_event(
            shipment_id=shipment_id,
            event_name="reroute_applied",
            payload={
                "remaining_polyline": remaining_polyline,
                "distance_km": alt["distance_km"],
                "eta_minutes": alt["eta_minutes"],
            },
        )
        await emit_lifecycle_event(
            shipment_id=shipment_id,
            event_name="simulation_resumed",
            payload={"reason": "reroute_confirmed"},
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return SimulationActionResponse(shipment_id=shipment_id, status="rerouted")


@router.post("/reject-reroute/{shipment_id}", response_model=SimulationActionResponse)
async def reject_reroute(
    shipment_id: int,
    _: Any = Depends(require_admin),
) -> SimulationActionResponse:
    runtime = simulation_runtime_registry.get(shipment_id)
    if runtime is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Simulation not running")

    async with runtime.lock:
        if runtime.pending_reroute is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No reroute suggestion pending")
        runtime.pending_reroute = None
        runtime.paused_for_reroute_confirmation = False

    await emit_lifecycle_event(
        shipment_id=shipment_id,
        event_name="reroute_rejected",
        payload={},
    )
    await emit_lifecycle_event(
        shipment_id=shipment_id,
        event_name="simulation_resumed",
        payload={"reason": "reroute_rejected"},
    )
    return SimulationActionResponse(shipment_id=shipment_id, status="reroute_rejected")


@router.get("/export/{shipment_id}")
async def export_simulation_run(
    shipment_id: int,
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    shipment_q = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = shipment_q.scalar_one_or_none()
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    routes_q = await session.execute(
        select(RouteHistory).where(RouteHistory.shipment_id == shipment_id).order_by(RouteHistory.timestamp.asc())
    )
    routes = routes_q.scalars().all()

    telemetry_q = await session.execute(
        select(TelemetryLog).where(TelemetryLog.shipment_id == shipment_id).order_by(TelemetryLog.timestamp.asc())
    )
    telemetry = telemetry_q.scalars().all()

    interventions_q = await session.execute(
        select(InterventionLog).where(InterventionLog.shipment_id == shipment_id).order_by(InterventionLog.timestamp.asc())
    )
    interventions = interventions_q.scalars().all()

    lifecycle_q = await session.execute(
        select(LifecycleEventLog).where(LifecycleEventLog.shipment_id == shipment_id).order_by(LifecycleEventLog.timestamp.asc())
    )
    lifecycle = lifecycle_q.scalars().all()

    return {
        "shipment": {
            "id": shipment.id,
            "shipment_code": shipment.shipment_code,
            "truck_name": shipment.truck_name,
            "status": shipment.status.value if hasattr(shipment.status, "value") else str(shipment.status),
            "origin": {"lat": float(shipment.origin_lat), "lng": float(shipment.origin_lng)},
            "destination": {"lat": float(shipment.destination_lat), "lng": float(shipment.destination_lng)},
            "current_location": {
                "lat": float(shipment.current_lat) if shipment.current_lat is not None else None,
                "lng": float(shipment.current_lng) if shipment.current_lng is not None else None,
            },
            "target_temp_low": float(shipment.target_temp_low),
            "target_temp_high": float(shipment.target_temp_high),
            "created_at": shipment.created_at.isoformat() if shipment.created_at else None,
            "updated_at": shipment.updated_at.isoformat() if shipment.updated_at else None,
        },
        "routes": [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "route_name": r.route_name,
                "reason": r.reason,
                "distance_km": r.distance_km,
                "eta_minutes": r.eta_minutes,
                "polyline": r.polyline_json,
            }
            for r in routes
        ],
        "telemetry_logs": [
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
            for t in telemetry
        ],
        "intervention_logs": [
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
            for i in interventions
        ],
        "lifecycle_events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "event": e.event,
                "payload": e.payload_json,
            }
            for e in lifecycle
        ],
    }


@router.get("/state/{shipment_id}")
async def simulation_state(
    shipment_id: int,
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    redis_client = get_redis_client()
    try:
        key = f"simulation_state:{shipment_id}"
        raw = await redis_client.get(key)
        running_state = json.loads(raw) if raw else None

        shipment_q = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
        shipment = shipment_q.scalar_one_or_none()
        if shipment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

        warehouses_q = await session.execute(
            select(WarehouseCandidate).where(WarehouseCandidate.has_cold_storage == True)  # noqa: E712
        )
        warehouses = [
            {
                "id": w.id,
                "name": w.name,
                "lat": float(w.lat),
                "lng": float(w.lng),
                "state": w.state,
                "has_cold_storage": w.has_cold_storage,
            }
            for w in warehouses_q.scalars().all()
        ]

        first_route_q = await session.execute(
            select(RouteHistory)
            .where(RouteHistory.shipment_id == shipment_id)
            .order_by(RouteHistory.timestamp.asc())
        )
        first_route = first_route_q.scalars().first()

        latest_route_q = await session.execute(
            select(RouteHistory)
            .where(RouteHistory.shipment_id == shipment_id)
            .order_by(RouteHistory.timestamp.desc())
        )
        latest_route = latest_route_q.scalars().first()

        def _parse_polyline(polyline_json: Any) -> list[list[float]] | None:
            if not polyline_json:
                return None
            if not isinstance(polyline_json, list):
                return None
            return [[float(p[0]), float(p[1])] for p in polyline_json]

        default_route_polyline = _parse_polyline(first_route.polyline_json) if first_route else None
        current_route_polyline = _parse_polyline(latest_route.polyline_json) if latest_route else None

        is_running = running_state is not None

        prefix_polyline = None
        remaining_polyline = None

        # Prefer in-memory runtime (it reflects reroute-updated remaining path).
        runtime = simulation_runtime_registry.get(shipment_id)
        if is_running and runtime is not None and runtime.segment_idx < len(runtime.route_polyline):
            remaining_polyline = runtime.route_polyline[runtime.segment_idx:]
            if remaining_polyline:
                remaining_polyline = [p for p in remaining_polyline]
                remaining_polyline[0] = [float(runtime.truck_lat), float(runtime.truck_lng)]
        elif current_route_polyline:
            # Not running: still show the latest known route.
            remaining_polyline = current_route_polyline

        return {
            "shipment_id": shipment_id,
            "running": is_running,
            "state": running_state if is_running else None,
            "paused_for_reroute_confirmation": bool(
                runtime.paused_for_reroute_confirmation
            )
            if runtime is not None
            else bool((running_state or {}).get("controls", {}).get("paused_for_reroute_confirmation")),
            "pending_reroute": (
                runtime.pending_reroute
                if runtime is not None
                else (running_state or {}).get("controls", {}).get("pending_reroute")
            ),
            "origin": {"lat": float(shipment.origin_lat), "lng": float(shipment.origin_lng)},
            "destination": {"lat": float(shipment.destination_lat), "lng": float(shipment.destination_lng)},
            "warehouses": warehouses,
            "default_route_polyline": default_route_polyline,
            "current_route_polyline": current_route_polyline,
            "prefix_polyline": prefix_polyline,
            "remaining_polyline": remaining_polyline,
        }
    finally:
        try:
            await redis_client.close()
        except Exception:
            pass


@router.get("/lifecycle/{shipment_id}")
async def simulation_lifecycle(
    shipment_id: int,
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    q = await session.execute(
        select(LifecycleEventLog).where(LifecycleEventLog.shipment_id == shipment_id).order_by(LifecycleEventLog.timestamp.asc())
    )
    rows = q.scalars().all()
    return [_timeline_entry_from_event(r) for r in rows]

