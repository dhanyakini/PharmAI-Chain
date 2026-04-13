"""Background simulation engine (telemetry + lifecycle publishing).

This module intentionally runs simulation logic outside the request lifecycle.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models import (
    InterventionLog,
    LifecycleEventLog,
    RouteHistory,
    Shipment,
    ShipmentStatus,
    TelemetryLog,
    utcnow,
)
from app.database.session import get_session_factory
from app.services.pubsub_service import CHANNEL_LIFECYCLE, CHANNEL_TELEMETRY, RedisPubSub, get_redis_client
from app.services.thermal_model import update_internal_temp_f
from app.services.routing_service import generate_route_polyline, route_truck_to_reroute_target
from app.services.warehouse_service import (
    nullify_warehouse_if_final_is_as_close_or_closer,
    pick_nearest_cold_storage_warehouse,
)
from app.services.weather_service import resolve_weather_for_simulation


SIM_STATE_KEY_PREFIX = "simulation_state"


simulation_task_registry: dict[int, asyncio.Task[None]] = {}


@dataclass
class SimulationRuntime:
    shipment_id: int
    route_polyline: list[list[float]]  # [[lat, lng], ...]

    # Current movement state along polyline.
    segment_idx: int = 0
    segment_progress_km: float = 0.0

    truck_lat: float = 0.0
    truck_lng: float = 0.0
    heading_deg: float = 0.0
    speed_kmh: float = 0.0

    internal_temp_f: float = 0.0
    temperature_violated: bool = False

    in_blizzard_zone: bool = False
    blizzard_prompted_in_current_zone: bool = False
    threshold_crossed_emitted: bool = False
    pending_reroute: dict[str, Any] | None = None
    paused_for_reroute_confirmation: bool = False
    shipment_status: ShipmentStatus = ShipmentStatus.in_transit
    route_total_km: float = 0.0
    target_duration_seconds: float = 120.0
    started_at_monotonic: float = 0.0
    # DB `blizzard_scenarios.id` — when set, overrides live API for this run (summer demos).
    blizzard_scenario_id: int | None = None

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


simulation_runtime_registry: dict[int, SimulationRuntime] = {}


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lambda = math.radians(lng2 - lng1)

    y = math.sin(d_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    brng = math.degrees(math.atan2(y, x))
    return (brng + 360.0) % 360.0


def _advance_along_polyline(
    *,
    polyline: list[list[float]],
    segment_idx: int,
    segment_progress_km: float,
    distance_to_travel_km: float,
) -> tuple[int, float, float, float, bool]:
    """Advance along a polyline by a distance, returning new movement state.

    Returns: (new_segment_idx, new_segment_progress_km, new_lat, new_lng, reached_destination)
    """
    if len(polyline) < 2:
        raise ValueError("Polyline must have at least 2 points")

    lat = polyline[segment_idx][0]
    lng = polyline[segment_idx][1]

    remaining = distance_to_travel_km
    idx = segment_idx
    prog = segment_progress_km

    while remaining > 1e-9 and idx < len(polyline) - 1:
        lat0, lng0 = polyline[idx]
        lat1, lng1 = polyline[idx + 1]
        seg_len = _haversine_km(lat0, lng0, lat1, lng1)

        if seg_len <= 1e-12:
            idx += 1
            prog = 0.0
            continue

        seg_remaining = seg_len - prog

        if remaining >= seg_remaining - 1e-9:
            # Move to end of this segment.
            remaining -= seg_remaining
            idx += 1
            prog = 0.0
            lat, lng = lat1, lng1
        else:
            # Move inside the segment by linear interpolation (good enough for small step sizes).
            prog += remaining
            frac = min(max(prog / seg_len, 0.0), 1.0)
            lat = lat0 + frac * (lat1 - lat0)
            lng = lng0 + frac * (lng1 - lng0)
            remaining = 0.0

    reached = idx >= len(polyline) - 1 and remaining <= 1e-8
    if reached:
        lat, lng = polyline[-1]
        idx = len(polyline) - 1
        prog = 0.0

    return idx, prog, lat, lng, reached


def _polyline_total_km(polyline: list[list[float]]) -> float:
    if len(polyline) < 2:
        return 0.0
    total = 0.0
    for i in range(len(polyline) - 1):
        lat0, lng0 = polyline[i]
        lat1, lng1 = polyline[i + 1]
        total += _haversine_km(lat0, lng0, lat1, lng1)
    return total


def _remaining_distance_km(
    *,
    polyline: list[list[float]],
    segment_idx: int,
    segment_progress_km: float,
) -> float:
    if len(polyline) < 2:
        return 0.0
    idx = max(0, min(segment_idx, len(polyline) - 1))
    if idx >= len(polyline) - 1:
        return 0.0

    remaining = 0.0
    lat0, lng0 = polyline[idx]
    lat1, lng1 = polyline[idx + 1]
    seg_len = _haversine_km(lat0, lng0, lat1, lng1)
    remaining += max(0.0, seg_len - segment_progress_km)
    for j in range(idx + 1, len(polyline) - 1):
        p0 = polyline[j]
        p1 = polyline[j + 1]
        remaining += _haversine_km(p0[0], p0[1], p1[0], p1[1])
    return remaining


async def _persist_lifecycle_event(
    *,
    session: AsyncSession,
    redis_pubsub: RedisPubSub,
    shipment_id: int,
    event_name: str,
    payload: dict[str, Any] | None = None,
) -> None:
    ts = utcnow()
    event_row = LifecycleEventLog(
        shipment_id=shipment_id,
        timestamp=ts,
        event=event_name,
        payload_json=payload,
    )
    session.add(event_row)
    await session.commit()

    msg = {
        "type": "lifecycle_event",
        "shipment_id": shipment_id,
        "timestamp": ts.isoformat(),
        "payload": {"event_name": event_name, **(payload or {})},
    }
    await redis_pubsub.publish_json(CHANNEL_LIFECYCLE, msg)


async def _persist_telemetry_and_publish(
    *,
    session: AsyncSession,
    redis_pubsub: RedisPubSub,
    shipment_id: int,
    lat: float,
    lng: float,
    heading_deg: float,
    speed_kmh: float,
    internal_temp_f: float,
    external_temp_f: float,
    weather_state: str,
    risk_level: float,
    route_segment: str,
    raw_payload: dict[str, Any] | None = None,
) -> None:
    ts = utcnow()
    row = TelemetryLog(
        shipment_id=shipment_id,
        timestamp=ts,
        lat=lat,
        lng=lng,
        internal_temp=internal_temp_f,
        external_temp=external_temp_f,
        weather_state=weather_state,
        route_segment=route_segment,
        risk_score=risk_level,
        raw_payload_json=raw_payload,
    )
    session.add(row)
    await session.commit()

    msg_payload = {
        "lat": lat,
        "lng": lng,
        "heading": heading_deg,
        "speed": speed_kmh,
        "weather_state": weather_state,
        "risk_level": risk_level,
        "internal_temp": internal_temp_f,
        "external_temp": external_temp_f,
        "route_segment": route_segment,
        **(raw_payload or {}),
    }
    msg = {
        "type": "telemetry",
        "shipment_id": shipment_id,
        "timestamp": ts.isoformat(),
        "payload": msg_payload,
    }
    await redis_pubsub.publish_json(CHANNEL_TELEMETRY, msg)


async def _persist_intervention_log(
    *,
    session: AsyncSession,
    shipment_id: int,
    agent_role: str,
    trigger_reason: str,
    reasoning_trace: str,
    action_taken: str,
    suggested_route_json: dict[str, Any] | None = None,
    confidence_score: float | None = None,
    raw_model_output_json: dict[str, Any] | None = None,
) -> None:
    row = InterventionLog(
        shipment_id=shipment_id,
        timestamp=utcnow(),
        agent_role=agent_role,
        trigger_reason=trigger_reason,
        reasoning_trace=reasoning_trace,
        action_taken=action_taken,
        suggested_route_json=suggested_route_json,
        confidence_score=confidence_score,
        raw_model_output_json=raw_model_output_json,
    )
    session.add(row)
    await session.commit()


def _route_polyline_from_db(polyline_json: Any) -> list[list[float]]:
    if polyline_json is None:
        raise ValueError("Route polyline not found")
    if not isinstance(polyline_json, list) or not polyline_json:
        raise ValueError("Route polyline invalid")
    # Expect [[lat,lng], ...]
    return [[float(p[0]), float(p[1])] for p in polyline_json]


def _closest_point_on_polyline(
    polyline: list[list[float]],
    lat: float,
    lng: float,
) -> tuple[int, float, float, float]:
    """Closest point on polyline to (lat, lng).

    Returns ``(segment_idx, progress_km_along_segment, snap_lat, snap_lng)`` so movement can continue
    from the snapped position without jumping back to the route origin.
    """
    if not polyline:
        raise ValueError("Polyline empty")
    if len(polyline) == 1:
        return 0, 0.0, float(polyline[0][0]), float(polyline[0][1])

    best_i = 0
    best_prog = 0.0
    best_lat = float(polyline[0][0])
    best_lng = float(polyline[0][1])
    best_d = float("inf")

    for i in range(len(polyline) - 1):
        lat0, lng0 = float(polyline[i][0]), float(polyline[i][1])
        lat1, lng1 = float(polyline[i + 1][0]), float(polyline[i + 1][1])
        seg_len = _haversine_km(lat0, lng0, lat1, lng1)
        if seg_len <= 1e-12:
            d = _haversine_km(lat, lng, lat0, lng0)
            if d < best_d:
                best_d, best_i, best_prog, best_lat, best_lng = d, i, 0.0, lat0, lng0
            continue
        dx, dy = lat1 - lat0, lng1 - lng0
        denom = dx * dx + dy * dy
        if denom < 1e-18:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((lat - lat0) * dx + (lng - lng0) * dy) / denom))
        pr_lat = lat0 + t * dx
        pr_lng = lng0 + t * dy
        prog = t * seg_len
        d = _haversine_km(lat, lng, pr_lat, pr_lng)
        if d < best_d:
            best_d = d
            best_i = i
            best_prog = prog
            best_lat, best_lng = pr_lat, pr_lng

    return best_i, best_prog, best_lat, best_lng


def _heading_from_snap_on_polyline(
    polyline: list[list[float]],
    segment_idx: int,
    snap_lat: float,
    snap_lng: float,
) -> float:
    if len(polyline) < 2:
        return 0.0
    idx = max(0, min(segment_idx, len(polyline) - 2))
    lat1, lng1 = float(polyline[idx + 1][0]), float(polyline[idx + 1][1])
    return _bearing_deg(snap_lat, snap_lng, lat1, lng1)


async def start_simulation_worker(shipment_id: int, blizzard_scenario_id: int | None = None) -> None:
    """Start a background simulation worker for a shipment."""
    if shipment_id in simulation_task_registry:
        raise RuntimeError("Simulation already running for this shipment")

    settings = get_settings()
    factory = get_session_factory()

    async with factory() as session:
        shipment_q = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
        shipment = shipment_q.scalar_one_or_none()
        if shipment is None:
            raise RuntimeError("Shipment not found")

        route_q = await session.execute(
            select(RouteHistory)
            .where(RouteHistory.shipment_id == shipment_id)
            .order_by(RouteHistory.timestamp.desc())
        )
        route_row = route_q.scalars().first()
        if route_row is None:
            raise RuntimeError("No saved route for shipment")

        route_polyline = _route_polyline_from_db(route_row.polyline_json)
        start_lat = float(shipment.current_lat if shipment.current_lat is not None else route_polyline[0][0])
        start_lng = float(shipment.current_lng if shipment.current_lng is not None else route_polyline[0][1])

        on_warehouse_detour = route_row.route_name == "reroute_applied" and (
            (route_row.reason or "") == "user_confirmed_to_warehouse"
        )
        replan_to_final = blizzard_scenario_id is None and (
            on_warehouse_detour or shipment.status == ShipmentStatus.rerouted
        )

        segment_idx = 0
        segment_progress_km = 0.0
        truck_lat = start_lat
        truck_lng = start_lng
        initial_heading = 0.0
        runtime_shipment_status = shipment.status

        if replan_to_final:
            seg_i, _, snap_lat, snap_lng = _closest_point_on_polyline(route_polyline, start_lat, start_lng)
            prefix = [list(p) for p in route_polyline[: seg_i + 1]]
            if prefix:
                prefix[-1] = [snap_lat, snap_lng]
            try:
                leg = await generate_route_polyline(
                    origin_lat=snap_lat,
                    origin_lng=snap_lng,
                    destination_lat=float(shipment.destination_lat),
                    destination_lng=float(shipment.destination_lng),
                )
                rem_raw = leg.get("polyline") or []
                rem = [[float(p[0]), float(p[1])] for p in rem_raw]
                if len(rem) < 2:
                    raise RuntimeError("OSRM returned insufficient points for resume-to-final")
                rem[0] = [snap_lat, snap_lng]
                full_for_db = prefix + rem[1:] if prefix else rem
                session.add(
                    RouteHistory(
                        shipment_id=shipment_id,
                        timestamp=utcnow(),
                        route_name="live_weather_resume_final",
                        reason="replan_truck_to_scheduled_destination",
                        polyline_json=full_for_db,
                        distance_km=float(leg.get("distance_km") or 0.0),
                        eta_minutes=float(leg.get("eta_minutes") or 0.0),
                    )
                )
                route_polyline = rem
                segment_idx = 0
                segment_progress_km = 0.0
                truck_lat, truck_lng = snap_lat, snap_lng
                shipment.status = ShipmentStatus.in_transit
                runtime_shipment_status = ShipmentStatus.in_transit
                initial_heading = _bearing_deg(snap_lat, snap_lng, route_polyline[1][0], route_polyline[1][1])
            except Exception:
                segment_idx, segment_progress_km, snap_lat, snap_lng = _closest_point_on_polyline(
                    route_polyline, start_lat, start_lng
                )
                truck_lat, truck_lng = snap_lat, snap_lng
                initial_heading = _heading_from_snap_on_polyline(route_polyline, segment_idx, snap_lat, snap_lng)
        else:
            segment_idx, segment_progress_km, snap_lat, snap_lng = _closest_point_on_polyline(
                route_polyline, start_lat, start_lng
            )
            truck_lat, truck_lng = snap_lat, snap_lng
            initial_heading = _heading_from_snap_on_polyline(route_polyline, segment_idx, snap_lat, snap_lng)

        runtime = SimulationRuntime(
            shipment_id=shipment_id,
            route_polyline=route_polyline,
            segment_idx=segment_idx,
            segment_progress_km=segment_progress_km,
            truck_lat=truck_lat,
            truck_lng=truck_lng,
            heading_deg=initial_heading,
            speed_kmh=60.0,
            internal_temp_f=settings.hvac_setpoint_f,
            temperature_violated=False,
            in_blizzard_zone=False,
            blizzard_prompted_in_current_zone=False,
            threshold_crossed_emitted=False,
            pending_reroute=None,
            paused_for_reroute_confirmation=False,
            shipment_status=runtime_shipment_status,
            route_total_km=_polyline_total_km(route_polyline),
            target_duration_seconds=max(30.0, float(settings.simulation_target_duration_seconds)),
            started_at_monotonic=time.monotonic(),
            blizzard_scenario_id=blizzard_scenario_id,
        )

        simulation_runtime_registry[shipment_id] = runtime

        shipment.current_lat = truck_lat
        shipment.current_lng = truck_lng
        session.add(shipment)
        await session.commit()

    # Start async loop with its own DB + Redis connections.
    task = asyncio.create_task(_simulation_loop(shipment_id))
    simulation_task_registry[shipment_id] = task

    # Immediately mark started in DB/Redis from outside loop as well (best-effort).
    # The loop also emits simulation_started; this keeps the first timeline tick consistent.


async def stop_simulation_worker(shipment_id: int) -> None:
    task = simulation_task_registry.get(shipment_id)
    if task is None:
        return
    task.cancel()
    # Best-effort: wait briefly for the task to exit so telemetry stops quickly.
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except Exception:
        pass

    # Remove from registries immediately so dashboards/state consumers update fast.
    simulation_task_registry.pop(shipment_id, None)
    simulation_runtime_registry.pop(shipment_id, None)
    # Persist last truck position from Redis cache so the next start resumes from the stop location.
    try:
        redis_client = get_redis_client()
        state_key = f"{SIM_STATE_KEY_PREFIX}:{shipment_id}"
        raw = await redis_client.get(state_key)
        if raw:
            try:
                cached = json.loads(raw)
                t = cached.get("truck") or {}
                lat, lng = t.get("lat"), t.get("lng")
                if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                    factory = get_session_factory()
                    async with factory() as persist_session:
                        sh_q = await persist_session.execute(
                            select(Shipment).where(Shipment.id == shipment_id)
                        )
                        sh = sh_q.scalar_one_or_none()
                        if sh is not None:
                            sh.current_lat = float(lat)
                            sh.current_lng = float(lng)
                            persist_session.add(sh)
                            await persist_session.commit()
            except Exception:
                pass
        await redis_client.delete(state_key)
        await redis_client.close()
    except Exception:
        pass


async def apply_reroute_to_running_shipment(shipment_id: int, new_polyline: list[list[float]]) -> None:
    """Update route polyline in-memory for a running simulation."""
    runtime = simulation_runtime_registry.get(shipment_id)
    if runtime is None:
        raise RuntimeError("Simulation not running")

    async with runtime.lock:
        # Route must start from the current truck coordinate to avoid teleporting.
        if not new_polyline:
            raise ValueError("New polyline empty")
        runtime.route_polyline = new_polyline
        runtime.segment_idx = 0
        runtime.segment_progress_km = 0.0
        runtime.route_total_km = _polyline_total_km(new_polyline)


async def _simulation_loop(shipment_id: int) -> None:
    settings = get_settings()
    factory = get_session_factory()
    redis_client = None
    state_key = f"{SIM_STATE_KEY_PREFIX}:{shipment_id}"
    try:
        redis_client = get_redis_client()
        pubsub = RedisPubSub(redis_client)

        # Worker has its own DB session for consistency.
        async with factory() as session:
            # Load current shipment + route snapshot.
            shipment_q = await session.execute(select(Shipment).where(Shipment.id == shipment_id))
            shipment = shipment_q.scalar_one_or_none()
            if shipment is None:
                return

            runtime = simulation_runtime_registry.get(shipment_id)
            if runtime is None:
                return

            # Emit simulation_started once.
            await _persist_lifecycle_event(
                session=session,
                redis_pubsub=pubsub,
                shipment_id=shipment_id,
                event_name="simulation_started",
                payload={},
            )

            tick_seconds = float(settings.simulation_tick_seconds)
            dt_hours = float(settings.simulated_minutes_per_tick) / 60.0

            # Send initial telemetry immediately.
            while True:
                async with runtime.lock:
                    w_lat = float(runtime.truck_lat)
                    w_lng = float(runtime.truck_lng)
                    w_scenario = runtime.blizzard_scenario_id

                weather = await resolve_weather_for_simulation(
                    session, w_lat, w_lng, blizzard_scenario_id=w_scenario
                )

                async with runtime.lock:
                    weather_state = str(weather["weather_state"])
                    external_temp_f = float(weather["external_temp_f"])
                    weather_risk = float(weather["risk_level"])

                    # Temperature dynamics.
                    # The first tick uses current internal temp and advances it by dt_hours.
                    runtime.internal_temp_f = update_internal_temp_f(
                        internal_temp_f=runtime.internal_temp_f,
                        external_temp_f=external_temp_f,
                        dt_hours=dt_hours,
                    )

                    if runtime.internal_temp_f <= settings.temperature_threshold_f:
                        runtime.temperature_violated = True

                    just_crossed_threshold = (
                        runtime.internal_temp_f <= settings.temperature_threshold_f
                        and not runtime.threshold_crossed_emitted
                    )

                    if just_crossed_threshold:
                        runtime.threshold_crossed_emitted = True
                        await _persist_lifecycle_event(
                            session=session,
                            redis_pubsub=pubsub,
                            shipment_id=shipment_id,
                            event_name="temperature_threshold_crossed",
                            payload={"internal_temp_f": runtime.internal_temp_f},
                        )

                    if (
                        runtime.internal_temp_f > settings.temperature_threshold_f
                        and runtime.threshold_crossed_emitted
                    ):
                        await _persist_lifecycle_event(
                            session=session,
                            redis_pubsub=pubsub,
                            shipment_id=shipment_id,
                            event_name="temperature_recovered",
                            payload={"internal_temp_f": runtime.internal_temp_f},
                        )
                        runtime.threshold_crossed_emitted = False
                        runtime.pending_reroute = None
                        if runtime.shipment_status == ShipmentStatus.rerouted:
                            runtime.shipment_status = ShipmentStatus.in_transit

                    # Weather zone lifecycle event.
                    now_in_zone = str(weather_state) == "blizzard"
                    if now_in_zone and not runtime.in_blizzard_zone:
                        runtime.in_blizzard_zone = True
                        await _persist_lifecycle_event(
                            session=session,
                            redis_pubsub=pubsub,
                            shipment_id=shipment_id,
                            event_name="entered_blizzard_zone",
                            payload={"weather_state": weather_state},
                        )
                        # Hard safety gate: immediately pause and request user reroute decision
                        # on first blizzard entry, independent of agent-model output timing.
                        if runtime.pending_reroute is None and not runtime.blizzard_prompted_in_current_zone:
                            wh_blizz = await pick_nearest_cold_storage_warehouse(
                                session,
                                lat=float(runtime.truck_lat),
                                lng=float(runtime.truck_lng),
                            )
                            wh_blizz = nullify_warehouse_if_final_is_as_close_or_closer(
                                truck_lat=float(runtime.truck_lat),
                                truck_lng=float(runtime.truck_lng),
                                final_lat=float(shipment.destination_lat),
                                final_lng=float(shipment.destination_lng),
                                warehouse=wh_blizz,
                            )
                            preview_payload: dict[str, Any] = {}
                            try:
                                alt = await route_truck_to_reroute_target(
                                    truck_lat=float(runtime.truck_lat),
                                    truck_lng=float(runtime.truck_lng),
                                    final_destination_lat=float(shipment.destination_lat),
                                    final_destination_lng=float(shipment.destination_lng),
                                    warehouse_candidate=wh_blizz,
                                )
                                preview_polyline = alt.get("polyline") or []
                                if preview_polyline:
                                    preview_polyline[0] = [float(runtime.truck_lat), float(runtime.truck_lng)]
                                    preview_payload = {
                                        "proposed_remaining_polyline": preview_polyline,
                                        "proposed_distance_km": alt.get("distance_km"),
                                        "proposed_eta_minutes": alt.get("eta_minutes"),
                                    }
                            except Exception:
                                preview_payload = {}

                            runtime.pending_reroute = {
                                "reroute_suggested": True,
                                "confidence_score": None,
                                "warehouse_candidate": wh_blizz,
                                "decision_reason": (
                                    "Blizzard detected on active route. Confirm reroute to continue safely."
                                    if wh_blizz
                                    else (
                                        "Blizzard detected. Original destination is as close or closer than staging; "
                                        "confirm continuing toward scheduled delivery."
                                    )
                                ),
                                "reasoning_trace": "Simulation paused for mandatory user reroute confirmation.",
                                "trigger_reason": "blizzard_detected",
                                **preview_payload,
                            }
                            runtime.blizzard_prompted_in_current_zone = True
                            runtime.paused_for_reroute_confirmation = True
                            await _persist_lifecycle_event(
                                session=session,
                                redis_pubsub=pubsub,
                                shipment_id=shipment_id,
                                event_name="simulation_paused_for_reroute",
                                payload={"reason": "blizzard_detected"},
                            )
                            await _persist_lifecycle_event(
                                session=session,
                                redis_pubsub=pubsub,
                                shipment_id=shipment_id,
                                event_name="reroute_suggested",
                                payload=runtime.pending_reroute,
                            )
                            # Same supervised event as the agent pipeline path, so Audits /interventions
                            # stays in sync when blizzard triggers the fast gate (pending_reroute is set
                            # here, which prevents should_evaluate_reroute from running the full pipeline).
                            await _persist_intervention_log(
                                session=session,
                                shipment_id=shipment_id,
                                agent_role="supervisor_agent",
                                trigger_reason="blizzard_detected",
                                reasoning_trace=str(
                                    runtime.pending_reroute.get("reasoning_trace")
                                    or runtime.pending_reroute.get("decision_reason")
                                    or ""
                                ),
                                action_taken="reroute_confirmation_requested",
                                suggested_route_json={
                                    "proposed_remaining_polyline": runtime.pending_reroute.get(
                                        "proposed_remaining_polyline"
                                    ),
                                    "proposed_distance_km": runtime.pending_reroute.get("proposed_distance_km"),
                                    "proposed_eta_minutes": runtime.pending_reroute.get("proposed_eta_minutes"),
                                },
                                raw_model_output_json=dict(runtime.pending_reroute),
                            )
                    if not now_in_zone:
                        runtime.in_blizzard_zone = False
                        runtime.blizzard_prompted_in_current_zone = False

                    # Risk level combines thermal risk + weather risk.
                    temp_risk = 1.0 if runtime.internal_temp_f <= settings.temperature_threshold_f else 0.0
                    risk_level = max(weather_risk, temp_risk)

                    # Drive the simulation to complete in the configured real-time duration.
                    remaining_distance_km = _remaining_distance_km(
                        polyline=runtime.route_polyline,
                        segment_idx=runtime.segment_idx,
                        segment_progress_km=runtime.segment_progress_km,
                    )
                    elapsed_real_seconds = max(0.0, time.monotonic() - runtime.started_at_monotonic)
                    remaining_real_seconds = max(1.0, runtime.target_duration_seconds - elapsed_real_seconds)
                    ticks_left = max(1, int(math.ceil(remaining_real_seconds / tick_seconds)))
                    planned_distance_km = remaining_distance_km / ticks_left
                    weather_multiplier = 0.7 if now_in_zone else 1.0
                    distance_to_travel_km = min(
                        remaining_distance_km,
                        max(0.03, planned_distance_km * weather_multiplier),
                    )
                    runtime.speed_kmh = distance_to_travel_km / max(dt_hours, 1e-6)

                    should_evaluate_reroute = (
                        (
                            just_crossed_threshold
                            or (
                                now_in_zone
                                and runtime.pending_reroute is None
                                and not runtime.blizzard_prompted_in_current_zone
                            )
                        )
                        and runtime.pending_reroute is None
                    )
                    if should_evaluate_reroute:
                        # Agent pipeline is invoked only on the initial threshold crossing.
                        env_reason = (
                            f"internal_temp_f={runtime.internal_temp_f:.2f}F, "
                            f"weather_state={weather_state}, risk_level={risk_level:.2f}"
                        )
                        await _persist_lifecycle_event(
                            session=session,
                            redis_pubsub=pubsub,
                            shipment_id=shipment_id,
                            event_name="environment_agent_called",
                            payload={
                                "weather_state": weather_state,
                                "internal_temp_f": runtime.internal_temp_f,
                                "external_temp_f": external_temp_f,
                                "risk_level": risk_level,
                                "decision_reason": env_reason,
                            },
                        )
                        await _persist_intervention_log(
                            session=session,
                            shipment_id=shipment_id,
                            agent_role="environment_agent",
                            trigger_reason="thermal_or_weather_risk_detected",
                            reasoning_trace=env_reason,
                            action_taken="risk_assessment_completed",
                            raw_model_output_json={
                                "weather_state": weather_state,
                                "risk_level": risk_level,
                                "internal_temp_f": runtime.internal_temp_f,
                                "external_temp_f": external_temp_f,
                            },
                        )

                        try:
                            from app.services.agent_pipeline import suggest_reroute

                            suggestion = await suggest_reroute(
                                session=session,
                                shipment=shipment,
                                current_lat=runtime.truck_lat,
                                current_lng=runtime.truck_lng,
                                internal_temp_f=runtime.internal_temp_f,
                                external_temp_f=external_temp_f,
                                weather_state=weather_state,
                                risk_level=risk_level,
                                blizzard_scenario_id=w_scenario,
                            )

                            staging_opts = suggestion.get("staging_options") or []
                            top_wh = staging_opts[0] if staging_opts else None
                            await _persist_lifecycle_event(
                                session=session,
                                redis_pubsub=pubsub,
                                shipment_id=shipment_id,
                                event_name="staging_warehouse_agent_called",
                                payload={
                                    "candidate_count": len(staging_opts),
                                    "top_warehouse_name": top_wh.get("name") if isinstance(top_wh, dict) else None,
                                },
                            )
                            await _persist_intervention_log(
                                session=session,
                                shipment_id=shipment_id,
                                agent_role="staging_warehouse_agent",
                                trigger_reason="environment_assessment_completed",
                                reasoning_trace=f"Ranked {len(staging_opts)} cold-storage staging candidate(s).",
                                action_taken="warehouse_candidates_ranked",
                                raw_model_output_json={"staging_options": staging_opts},
                            )

                            nav_opts = suggestion.get("navigation_options") or []
                            await _persist_lifecycle_event(
                                session=session,
                                redis_pubsub=pubsub,
                                shipment_id=shipment_id,
                                event_name="navigation_agent_called",
                                payload={
                                    "legs_resolved": len(nav_opts),
                                },
                            )
                            await _persist_intervention_log(
                                session=session,
                                shipment_id=shipment_id,
                                agent_role="navigation_agent",
                                trigger_reason="staging_options_available",
                                reasoning_trace="Resolved OSRM (or fallback) legs from truck to each staging option and final destination.",
                                action_taken="route_legs_evaluated",
                                raw_model_output_json={"navigation_options": nav_opts},
                            )

                            await _persist_lifecycle_event(
                                session=session,
                                redis_pubsub=pubsub,
                                shipment_id=shipment_id,
                                event_name="supervisor_decision_selected",
                                payload={
                                    "reroute_suggested": suggestion.get("reroute_suggested"),
                                    "confidence_score": suggestion.get("confidence_score"),
                                    "warehouse_candidate": suggestion.get("warehouse_candidate"),
                                    "decision_reason": suggestion.get("decision_reason"),
                                    "reasoning_trace": suggestion.get("reasoning_trace"),
                                    "llm_prompt": suggestion.get("llm_prompt"),
                                    "llm_response": suggestion.get("llm_response"),
                                    "environment_assessment": suggestion.get("environment_assessment"),
                                    "staging_options": staging_opts,
                                    "navigation_options": nav_opts,
                                    "agent_decision": suggestion.get("agent_decision"),
                                },
                            )
                            await _persist_intervention_log(
                                session=session,
                                shipment_id=shipment_id,
                                agent_role="supervisor_agent",
                                trigger_reason=(
                                    "blizzard_detected"
                                    if now_in_zone
                                    else "temperature_threshold_crossed"
                                ),
                                reasoning_trace=str(suggestion.get("reasoning_trace") or ""),
                                action_taken=(
                                    "reroute_suggested"
                                    if suggestion.get("reroute_suggested")
                                    else "reroute_not_recommended"
                                ),
                                confidence_score=(
                                    float(suggestion.get("confidence_score"))
                                    if suggestion.get("confidence_score") is not None
                                    else None
                                ),
                                raw_model_output_json={
                                    "decision_reason": suggestion.get("decision_reason"),
                                    "llm_prompt": suggestion.get("llm_prompt"),
                                    "llm_response": suggestion.get("llm_response"),
                                    "environment_assessment": suggestion.get("environment_assessment"),
                                    "staging_options": staging_opts,
                                    "navigation_options": nav_opts,
                                    "agent_decision": suggestion.get("agent_decision"),
                                },
                            )

                            should_prompt_user = bool(suggestion.get("reroute_suggested")) or now_in_zone
                            if should_prompt_user:
                                preview_payload: dict[str, Any] = {}
                                try:
                                    wh = suggestion.get("warehouse_candidate")
                                    alt = await route_truck_to_reroute_target(
                                        truck_lat=float(runtime.truck_lat),
                                        truck_lng=float(runtime.truck_lng),
                                        final_destination_lat=float(shipment.destination_lat),
                                        final_destination_lng=float(shipment.destination_lng),
                                        warehouse_candidate=wh if isinstance(wh, dict) else None,
                                    )
                                    preview_polyline = alt.get("polyline") or []
                                    if preview_polyline:
                                        preview_polyline[0] = [float(runtime.truck_lat), float(runtime.truck_lng)]
                                        preview_payload = {
                                            "proposed_remaining_polyline": preview_polyline,
                                            "proposed_distance_km": alt.get("distance_km"),
                                            "proposed_eta_minutes": alt.get("eta_minutes"),
                                        }
                                except Exception:
                                    preview_payload = {}

                                if now_in_zone and not suggestion.get("reroute_suggested"):
                                    suggestion = {
                                        **suggestion,
                                        "reroute_suggested": True,
                                        "decision_reason": suggestion.get("decision_reason")
                                        or "Blizzard detected on active route. User confirmation required.",
                                        "reasoning_trace": suggestion.get("reasoning_trace")
                                        or "Route intersects blizzard zone; proposing safer alternate path.",
                                    }
                                runtime.pending_reroute = {
                                    **suggestion,
                                    **preview_payload,
                                    "trigger_reason": "blizzard_detected" if now_in_zone else "temperature_threshold_crossed",
                                }
                                if now_in_zone:
                                    runtime.blizzard_prompted_in_current_zone = True
                                    runtime.paused_for_reroute_confirmation = True
                                    await _persist_lifecycle_event(
                                        session=session,
                                        redis_pubsub=pubsub,
                                        shipment_id=shipment_id,
                                        event_name="simulation_paused_for_reroute",
                                        payload={"reason": "blizzard_detected"},
                                    )
                                await _persist_lifecycle_event(
                                    session=session,
                                    redis_pubsub=pubsub,
                                    shipment_id=shipment_id,
                                    event_name="reroute_suggested",
                                    payload=runtime.pending_reroute,
                                )
                                await _persist_intervention_log(
                                    session=session,
                                    shipment_id=shipment_id,
                                    agent_role="supervisor_agent",
                                    trigger_reason="blizzard_detected",
                                    reasoning_trace="Fallback blizzard safety gate requested manual reroute confirmation.",
                                    action_taken="reroute_confirmation_requested",
                                    suggested_route_json={
                                        "proposed_remaining_polyline": runtime.pending_reroute.get(
                                            "proposed_remaining_polyline"
                                        ),
                                        "proposed_distance_km": runtime.pending_reroute.get("proposed_distance_km"),
                                        "proposed_eta_minutes": runtime.pending_reroute.get("proposed_eta_minutes"),
                                    },
                                    raw_model_output_json=runtime.pending_reroute,
                                )
                                await _persist_intervention_log(
                                    session=session,
                                    shipment_id=shipment_id,
                                    agent_role="supervisor_agent",
                                    trigger_reason=str(runtime.pending_reroute.get("trigger_reason") or ""),
                                    reasoning_trace=str(runtime.pending_reroute.get("reasoning_trace") or ""),
                                    action_taken="reroute_confirmation_requested",
                                    suggested_route_json={
                                        "proposed_remaining_polyline": runtime.pending_reroute.get(
                                            "proposed_remaining_polyline"
                                        ),
                                        "proposed_distance_km": runtime.pending_reroute.get("proposed_distance_km"),
                                        "proposed_eta_minutes": runtime.pending_reroute.get("proposed_eta_minutes"),
                                    },
                                    confidence_score=(
                                        float(runtime.pending_reroute.get("confidence_score"))
                                        if runtime.pending_reroute.get("confidence_score") is not None
                                        else None
                                    ),
                                    raw_model_output_json=runtime.pending_reroute,
                                )
                        except Exception:
                            # Agent suggestion is best-effort. For blizzard entry, force user confirmation flow.
                            if now_in_zone and not runtime.blizzard_prompted_in_current_zone:
                                wh_fallback = await pick_nearest_cold_storage_warehouse(
                                    session,
                                    lat=float(runtime.truck_lat),
                                    lng=float(runtime.truck_lng),
                                )
                                wh_fallback = nullify_warehouse_if_final_is_as_close_or_closer(
                                    truck_lat=float(runtime.truck_lat),
                                    truck_lng=float(runtime.truck_lng),
                                    final_lat=float(shipment.destination_lat),
                                    final_lng=float(shipment.destination_lng),
                                    warehouse=wh_fallback,
                                )
                                preview_payload: dict[str, Any] = {}
                                try:
                                    alt = await route_truck_to_reroute_target(
                                        truck_lat=float(runtime.truck_lat),
                                        truck_lng=float(runtime.truck_lng),
                                        final_destination_lat=float(shipment.destination_lat),
                                        final_destination_lng=float(shipment.destination_lng),
                                        warehouse_candidate=wh_fallback,
                                    )
                                    preview_polyline = alt.get("polyline") or []
                                    if preview_polyline:
                                        preview_polyline[0] = [float(runtime.truck_lat), float(runtime.truck_lng)]
                                        preview_payload = {
                                            "proposed_remaining_polyline": preview_polyline,
                                            "proposed_distance_km": alt.get("distance_km"),
                                            "proposed_eta_minutes": alt.get("eta_minutes"),
                                        }
                                except Exception:
                                    preview_payload = {}

                                runtime.pending_reroute = {
                                    "reroute_suggested": True,
                                    "confidence_score": None,
                                    "warehouse_candidate": wh_fallback,
                                    "decision_reason": "Blizzard detected on route. Manual reroute confirmation required.",
                                    "reasoning_trace": "Safety gate triggered by blizzard zone entry.",
                                    "trigger_reason": "blizzard_detected",
                                    **preview_payload,
                                }
                                runtime.blizzard_prompted_in_current_zone = True
                                runtime.paused_for_reroute_confirmation = True
                                await _persist_lifecycle_event(
                                    session=session,
                                    redis_pubsub=pubsub,
                                    shipment_id=shipment_id,
                                    event_name="simulation_paused_for_reroute",
                                    payload={"reason": "blizzard_detected"},
                                )
                                await _persist_lifecycle_event(
                                    session=session,
                                    redis_pubsub=pubsub,
                                    shipment_id=shipment_id,
                                    event_name="reroute_suggested",
                                    payload=runtime.pending_reroute,
                                )

                    # Advance route only when not waiting on explicit reroute confirmation.
                    if runtime.paused_for_reroute_confirmation:
                        reached = False
                        runtime.speed_kmh = 0.0
                    else:
                        prev_lat, prev_lng = runtime.truck_lat, runtime.truck_lng
                        runtime.segment_idx, runtime.segment_progress_km, runtime.truck_lat, runtime.truck_lng, reached = (
                            _advance_along_polyline(
                                polyline=runtime.route_polyline,
                                segment_idx=runtime.segment_idx,
                                segment_progress_km=runtime.segment_progress_km,
                                distance_to_travel_km=distance_to_travel_km,
                            )
                        )
                        runtime.heading_deg = _bearing_deg(prev_lat, prev_lng, runtime.truck_lat, runtime.truck_lng)

                    route_segment = f"segment_{runtime.segment_idx}"

                    await _persist_telemetry_and_publish(
                        session=session,
                        redis_pubsub=pubsub,
                        shipment_id=shipment_id,
                        lat=runtime.truck_lat,
                        lng=runtime.truck_lng,
                        heading_deg=runtime.heading_deg,
                        speed_kmh=runtime.speed_kmh,
                        internal_temp_f=runtime.internal_temp_f,
                        external_temp_f=external_temp_f,
                        weather_state=weather_state,
                        risk_level=risk_level,
                        route_segment=route_segment,
                        raw_payload={
                            "weather_source": weather.get("source"),
                            "blizzard_scenario_id": weather.get("blizzard_scenario_id"),
                            "blizzard_scenario_slug": weather.get("blizzard_scenario_slug"),
                            "segment_idx": runtime.segment_idx,
                            "segment_progress_km": runtime.segment_progress_km,
                            "remaining_distance_km": max(0.0, remaining_distance_km - distance_to_travel_km),
                            "route_total_km": runtime.route_total_km,
                            "progress_pct": (
                                0.0
                                if runtime.route_total_km <= 1e-6
                                else max(
                                    0.0,
                                    min(
                                        100.0,
                                        (
                                            (runtime.route_total_km - max(0.0, remaining_distance_km - distance_to_travel_km))
                                            / runtime.route_total_km
                                        )
                                        * 100.0,
                                    ),
                                )
                            ),
                        },
                    )

                    # Check delivery at destination.
                    if reached:
                        if not runtime.temperature_violated:
                            shipment.status = ShipmentStatus.delivered
                            await _persist_lifecycle_event(
                                session=session,
                                redis_pubsub=pubsub,
                                shipment_id=shipment_id,
                                event_name="shipment_delivered",
                                payload={},
                            )
                        else:
                            shipment.status = ShipmentStatus.compromised
                            await _persist_lifecycle_event(
                                session=session,
                                redis_pubsub=pubsub,
                                shipment_id=shipment_id,
                                event_name="shipment_compromised",
                                payload={},
                            )
                        session.add(shipment)
                        await session.commit()
                        return

                    # Persist current position/status.
                    shipment.current_lat = runtime.truck_lat
                    shipment.current_lng = runtime.truck_lng
                    shipment.status = runtime.shipment_status
                    session.add(shipment)
                    await session.commit()

                    # Best-effort simulation state cache for reroute/synchronization.
                    state_key = f"{SIM_STATE_KEY_PREFIX}:{shipment_id}"
                    state = {
                        "truck": {
                            "lat": runtime.truck_lat,
                            "lng": runtime.truck_lng,
                            "heading": runtime.heading_deg,
                            "speed_kmh": runtime.speed_kmh,
                        },
                        "progress": {
                            "segment_idx": runtime.segment_idx,
                            "segment_progress_km": runtime.segment_progress_km,
                        },
                        "thermal": {
                            "internal_temp_f": runtime.internal_temp_f,
                            "temperature_violated": runtime.temperature_violated,
                        },
                        "weather": {
                            "weather_state": weather_state,
                            "risk_level": risk_level,
                            "external_temp_f": external_temp_f,
                            "source": weather.get("source"),
                            "blizzard_scenario_id": weather.get("blizzard_scenario_id"),
                        },
                        "controls": {
                            "paused_for_reroute_confirmation": runtime.paused_for_reroute_confirmation,
                            "pending_reroute": runtime.pending_reroute,
                        },
                        "timestamp": utcnow().isoformat(),
                    }
                    await redis_client.set(state_key, json.dumps(state, default=str))

                # Outside lock: wait for next tick.
                await asyncio.sleep(tick_seconds)

    except asyncio.CancelledError:
        # Best-effort stop event.
        try:
            if redis_client is not None:
                pubsub = RedisPubSub(redis_client)
            else:
                pubsub = None  # type: ignore[assignment]
            async with factory() as session:
                if pubsub is not None:
                    await _persist_lifecycle_event(
                        session=session,
                        redis_pubsub=pubsub,
                        shipment_id=shipment_id,
                        event_name="simulation_stopped",
                        payload={},
                    )
        except Exception:
            pass
        return
    finally:
        simulation_task_registry.pop(shipment_id, None)
        simulation_runtime_registry.pop(shipment_id, None)
        if redis_client is not None:
            try:
                # Ensure the websocket/state consumers don't think the shipment is still running.
                await redis_client.delete(state_key)
                await redis_client.close()
            except Exception:
                pass

