"""Pure tool functions for the agentic reroute system (testable, DB/OSRM-backed)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.agent_schemas import (
    FinalLegSummary,
    MemoryToolResult,
    RouteLegsToolResult,
    ThermalRiskToolResult,
    WarehouseLegSummary,
    WarehousesToolResult,
    WeatherToolResult,
)
from app.services.routing_service import route_legs_parallel_from_truck
from app.services.thermal_model import estimate_minutes_until_internal_at_or_below
from app.services.warehouse_service import list_ranked_cold_storage_warehouses
from app.services.weather_service import resolve_weather_for_simulation


async def tool_list_warehouses(
    session: AsyncSession,
    *,
    lat: float,
    lng: float,
    limit: int = 5,
) -> WarehousesToolResult:
    rows = await list_ranked_cold_storage_warehouses(session, lat=lat, lng=lng, limit=limit)
    return WarehousesToolResult(warehouses=rows)


async def tool_route_legs(
    *,
    truck_lat: float,
    truck_lng: float,
    warehouses: list[dict[str, Any]],
    final_destination_lat: float,
    final_destination_lng: float,
) -> RouteLegsToolResult:
    legs: list[tuple[str, str, dict[str, Any] | None, float, float]] = []
    for w in warehouses:
        wid = w.get("id")
        legs.append(
            (
                f"wh:{wid}",
                "warehouse",
                w,
                float(w["lat"]),
                float(w["lng"]),
            )
        )
    legs.append(("final", "final", None, float(final_destination_lat), float(final_destination_lng)))

    packages = await route_legs_parallel_from_truck(
        truck_lat=truck_lat,
        truck_lng=truck_lng,
        legs=legs,
    )
    raw_packages = [dict(p) for p in packages]

    wh_summaries: list[WarehouseLegSummary] = []
    final_sum = FinalLegSummary(distance_km=0.0, eta_minutes=0.0, routing_source="")
    for p in packages:
        tgt = p.get("target")
        if tgt == "final":
            final_sum = FinalLegSummary(
                distance_km=float(p.get("distance_km") or 0.0),
                eta_minutes=float(p.get("eta_minutes") or 0.0),
                routing_source=str(p.get("routing_source") or ""),
            )
        elif tgt == "warehouse":
            wh = p.get("warehouse") or {}
            wid = wh.get("id")
            if wid is not None:
                wh_summaries.append(
                    WarehouseLegSummary(
                        warehouse_id=int(wid),
                        name=str(wh.get("name") or ""),
                        distance_km=float(p.get("distance_km") or 0.0),
                        eta_minutes=float(p.get("eta_minutes") or 0.0),
                        routing_source=str(p.get("routing_source") or ""),
                    )
                )

    return RouteLegsToolResult(
        truck_lat=truck_lat,
        truck_lng=truck_lng,
        final=final_sum,
        warehouses=wh_summaries,
        raw_packages=raw_packages,
    )


def tool_estimate_thermal_risk(
    *,
    internal_temp_f: float,
    external_temp_f: float,
    threshold_f: float | None = None,
) -> ThermalRiskToolResult:
    settings = get_settings()
    thr = float(threshold_f if threshold_f is not None else settings.temperature_threshold_f)
    eta = estimate_minutes_until_internal_at_or_below(
        internal_temp_f=internal_temp_f,
        external_temp_f=external_temp_f,
        threshold_f=thr,
    )
    if eta is None:
        stress = "low"
    elif eta <= 0:
        stress = "critical"
    elif eta < 60:
        stress = "high"
    elif eta < 240:
        stress = "moderate"
    else:
        stress = "low"
    return ThermalRiskToolResult(
        temperature_threshold_f=thr,
        internal_temp_f=internal_temp_f,
        external_temp_f=external_temp_f,
        estimated_minutes_to_cold_threshold=eta,
        thermal_stress=stress,
        cold_violation=internal_temp_f <= thr,
    )


async def tool_get_weather(
    session: AsyncSession,
    *,
    lat: float,
    lng: float,
    blizzard_scenario_id: int | None,
) -> WeatherToolResult:
    w = await resolve_weather_for_simulation(session, lat, lng, blizzard_scenario_id=blizzard_scenario_id)
    return WeatherToolResult(
        weather_state=str(w.get("weather_state") or "unknown"),
        external_temp_f=float(w.get("external_temp_f") or 0.0),
        risk_level=float(w.get("risk_level") or 0.0),
        source=str(w.get("source") or ""),
    )
