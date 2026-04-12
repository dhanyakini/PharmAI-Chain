"""Deterministic LangGraph reroute pipeline (utility supervisor + optional Groq narration)."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models import Shipment, ShipmentStatus
from app.services.routing_service import route_legs_parallel_from_truck
from app.services.thermal_model import estimate_minutes_until_internal_at_or_below
from app.services.warehouse_service import (
    list_ranked_cold_storage_warehouses,
    nullify_warehouse_if_final_is_as_close_or_closer,
)

_MAX_STAGING_CANDIDATES = 5


class DeterministicAgentState(TypedDict):
    shipment_status: str
    internal_temp_f: float
    external_temp_f: float
    weather_state: str
    risk_level: float
    current_lat: float
    current_lng: float
    destination_lat: float
    destination_lng: float
    environment_assessment: NotRequired[dict[str, Any] | None]
    staging_options: NotRequired[list[dict[str, Any]]]
    route_packages: NotRequired[list[dict[str, Any]]]
    warehouse_candidate: NotRequired[dict[str, Any] | None]
    reroute_suggested: NotRequired[bool]
    decision_reason: NotRequired[str]
    reasoning_trace: NotRequired[str]
    llm_prompt: NotRequired[str]
    llm_response: NotRequired[str]
    confidence_score: NotRequired[float | None]


def _warehouse_for_api(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k != "straight_line_km"}


def _thermal_stress_label(eta_min: float | None) -> str:
    if eta_min is None:
        return "unknown"
    if eta_min <= 0:
        return "critical"
    if eta_min < 60:
        return "high"
    if eta_min < 240:
        return "moderate"
    return "low"


def _package_utility(
    pkg: dict[str, Any],
    *,
    risk_level: float,
    blizzard: bool,
    weights_safety: float,
    weights_time: float,
    weights_cost: float,
) -> float:
    eta_n = min(1.0, float(pkg.get("eta_minutes") or 0.0) / 180.0)
    dist_n = min(1.0, float(pkg.get("distance_km") or 0.0) / 600.0)
    is_wh = pkg.get("target") == "warehouse"
    safety = float(risk_level)
    if is_wh:
        safety += 0.2 if blizzard else 0.08
    wh = pkg.get("warehouse")
    if is_wh and isinstance(wh, dict) and int(wh.get("capacity_units") or 0) <= 0:
        safety -= 0.04
    return weights_safety * safety - weights_time * eta_n - weights_cost * dist_n


def _apply_prefer_final_if_no_farther_than_staging(
    *,
    packages: list[dict[str, Any]],
    warehouse_candidate: dict[str, Any] | None,
    truck_lat: float,
    truck_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> tuple[dict[str, Any] | None, str]:
    if warehouse_candidate is None:
        return None, ""
    final_pkg = next((p for p in packages if p.get("target") == "final"), None)
    wh_id = warehouse_candidate.get("id")
    wh_pkg = None
    for p in packages:
        if p.get("target") != "warehouse":
            continue
        w = p.get("warehouse") or {}
        if w.get("id") == wh_id:
            wh_pkg = p
            break
    if final_pkg is not None and wh_pkg is not None:
        fd = float(final_pkg.get("distance_km") or 0.0)
        wd = float(wh_pkg.get("distance_km") or 0.0)
        if fd <= wd:
            return None, (
                f"Original destination ({fd:.1f} km) is no farther than staging ({wd:.1f} km); "
                "continue toward initial destination."
            )
        return warehouse_candidate, ""
    dropped = nullify_warehouse_if_final_is_as_close_or_closer(
        truck_lat=truck_lat,
        truck_lng=truck_lng,
        final_lat=dest_lat,
        final_lng=dest_lng,
        warehouse=warehouse_candidate,
    )
    if dropped is None:
        return None, (
            "Straight-line distance to original destination is no greater than to staging; "
            "continue toward initial destination."
        )
    return dropped, ""


async def run_deterministic_langgraph(
    *,
    session: AsyncSession,
    shipment: Shipment,
    current_lat: float,
    current_lng: float,
    internal_temp_f: float,
    external_temp_f: float,
    weather_state: str,
    risk_level: float,
) -> dict[str, Any]:
    settings = get_settings()

    async def environment_agent(state: DeterministicAgentState) -> dict[str, Any]:
        threshold = float(settings.temperature_threshold_f)
        eta_min = estimate_minutes_until_internal_at_or_below(
            internal_temp_f=float(state["internal_temp_f"]),
            external_temp_f=float(state["external_temp_f"]),
            threshold_f=threshold,
        )
        stress = _thermal_stress_label(eta_min)
        summary = (
            f"internal={state['internal_temp_f']:.2f}F external={state['external_temp_f']:.2f}F "
            f"weather={state['weather_state']} risk={state['risk_level']:.2f}; "
            f"thermal_stress={stress}"
        )
        if eta_min is not None:
            summary += f"; est_min_to_threshold={eta_min:.0f}m"
        assessment = {
            "internal_temp_f": state["internal_temp_f"],
            "external_temp_f": state["external_temp_f"],
            "weather_state": state["weather_state"],
            "risk_level": state["risk_level"],
            "temperature_threshold_f": threshold,
            "estimated_minutes_to_cold_threshold": eta_min,
            "thermal_stress": stress,
            "summary": summary,
        }
        return {
            "environment_assessment": assessment,
            "decision_reason": summary,
        }

    async def staging_warehouse_agent(state: DeterministicAgentState) -> dict[str, Any]:
        ranked = await list_ranked_cold_storage_warehouses(
            session,
            lat=float(state["current_lat"]),
            lng=float(state["current_lng"]),
            limit=_MAX_STAGING_CANDIDATES,
        )
        return {"staging_options": ranked}

    async def navigation_agent(state: DeterministicAgentState) -> dict[str, Any]:
        staging = list(state.get("staging_options") or [])
        dlat = float(state["destination_lat"])
        dlng = float(state["destination_lng"])
        legs: list[tuple[str, str, dict[str, Any] | None, float, float]] = []
        for w in staging:
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
        legs.append(("final", "final", None, dlat, dlng))

        packages = await route_legs_parallel_from_truck(
            truck_lat=float(state["current_lat"]),
            truck_lng=float(state["current_lng"]),
            legs=legs,
        )
        return {"route_packages": packages}

    async def supervisor_agent(state: DeterministicAgentState) -> dict[str, Any]:
        packages = list(state.get("route_packages") or [])
        staging = list(state.get("staging_options") or [])
        assessment = state.get("environment_assessment") or {}
        cold = float(state["internal_temp_f"]) <= float(settings.temperature_threshold_f)
        blizzard = str(state["weather_state"]).lower() == "blizzard"
        risk = float(state["risk_level"])

        if not packages:
            wh0 = _warehouse_for_api(staging[0]) if staging else None
            reroute_suggested = cold or blizzard or risk >= 0.5
            warehouse_candidate = wh0 if reroute_suggested and wh0 else None
            warehouse_candidate = nullify_warehouse_if_final_is_as_close_or_closer(
                truck_lat=float(state["current_lat"]),
                truck_lng=float(state["current_lng"]),
                final_lat=float(state["destination_lat"]),
                final_lng=float(state["destination_lng"]),
                warehouse=warehouse_candidate,
            )
            confidence = max(0.1, min(0.95, risk * 0.85)) if reroute_suggested else None
            trace = "No OSRM leg summaries; fallback to staging policy."
            return {
                "warehouse_candidate": warehouse_candidate,
                "reroute_suggested": reroute_suggested,
                "confidence_score": confidence,
                "reasoning_trace": trace,
                "llm_prompt": "",
                "llm_response": "",
            }

        best = max(
            packages,
            key=lambda p: _package_utility(
                p,
                risk_level=risk,
                blizzard=blizzard,
                weights_safety=settings.supervisor_weight_safety,
                weights_time=settings.supervisor_weight_time,
                weights_cost=settings.supervisor_weight_cost,
            ),
        )

        warehouse_candidate: dict[str, Any] | None = None
        if best.get("target") == "warehouse" and isinstance(best.get("warehouse"), dict):
            warehouse_candidate = _warehouse_for_api(best["warehouse"])
        elif cold or blizzard:
            warehouse_candidate = _warehouse_for_api(staging[0]) if staging else None

        reroute_suggested = bool(
            cold or blizzard or risk >= 0.5 or best.get("target") == "warehouse"
        )
        if reroute_suggested and warehouse_candidate is None and staging:
            warehouse_candidate = _warehouse_for_api(staging[0])

        prefer_note = ""
        warehouse_candidate, prefer_note = _apply_prefer_final_if_no_farther_than_staging(
            packages=packages,
            warehouse_candidate=warehouse_candidate,
            truck_lat=float(state["current_lat"]),
            truck_lng=float(state["current_lng"]),
            dest_lat=float(state["destination_lat"]),
            dest_lng=float(state["destination_lng"]),
        )

        confidence = None
        if reroute_suggested:
            confidence = max(0.1, min(0.95, risk * 0.8 + (0.1 if blizzard else 0.0)))

        nav_summary = [
            {
                "leg_key": p.get("leg_key"),
                "target": p.get("target"),
                "distance_km": round(float(p.get("distance_km") or 0.0), 2),
                "eta_minutes": round(float(p.get("eta_minutes") or 0.0), 2),
                "routing_source": p.get("routing_source"),
            }
            for p in packages
        ]
        reasoning_trace = (
            f"Supervisor selected target={best.get('target')} leg={best.get('leg_key')} "
            f"via policy (cold={cold} blizzard={blizzard})."
        )
        if prefer_note:
            reasoning_trace = f"{prefer_note} ({reasoning_trace.strip()})"

        llm_prompt = (
            "You are a cold-chain logistics supervisor. Summarize the decision in at most 100 words "
            "for operators (safety, time, staging vs final).\n\n"
            f"{assessment.get('summary', '')}\n"
            f"reroute_suggested={reroute_suggested}\n"
            f"chosen_leg={best.get('leg_key')} target={best.get('target')}\n"
            f"navigation_options={nav_summary}\n"
            f"warehouse_candidate={warehouse_candidate}\n"
        )
        llm_response = ""
        try:
            key = (settings.groq_api_key or "").strip()
            if key:
                from openai import AsyncOpenAI

                client = AsyncOpenAI(api_key=key, base_url=settings.groq_base_url)
                resp = await client.chat.completions.create(
                    model=settings.groq_model,
                    messages=[{"role": "user", "content": llm_prompt}],
                    temperature=0.2,
                )
                llm_response = (resp.choices[0].message.content or "").strip()
                if llm_response:
                    reasoning_trace = llm_response[:200].strip()
        except Exception:
            llm_response = llm_response or reasoning_trace

        return {
            "warehouse_candidate": warehouse_candidate,
            "reroute_suggested": reroute_suggested,
            "confidence_score": confidence,
            "reasoning_trace": reasoning_trace,
            "llm_prompt": llm_prompt,
            "llm_response": llm_response,
        }

    graph = StateGraph(DeterministicAgentState)
    graph.add_node("environment_agent", environment_agent)
    graph.add_node("staging_warehouse_agent", staging_warehouse_agent)
    graph.add_node("navigation_agent", navigation_agent)
    graph.add_node("supervisor_agent", supervisor_agent)
    graph.set_entry_point("environment_agent")
    graph.add_edge("environment_agent", "staging_warehouse_agent")
    graph.add_edge("staging_warehouse_agent", "navigation_agent")
    graph.add_edge("navigation_agent", "supervisor_agent")
    graph.add_edge("supervisor_agent", END)
    app = graph.compile()

    initial_state: DeterministicAgentState = {
        "shipment_status": shipment.status.value,
        "internal_temp_f": internal_temp_f,
        "external_temp_f": external_temp_f,
        "weather_state": weather_state,
        "risk_level": risk_level,
        "current_lat": current_lat,
        "current_lng": current_lng,
        "destination_lat": shipment.destination_lat,
        "destination_lng": shipment.destination_lng,
        "environment_assessment": None,
        "staging_options": [],
        "route_packages": [],
        "warehouse_candidate": None,
        "reroute_suggested": False,
        "decision_reason": "",
        "reasoning_trace": "",
        "confidence_score": None,
    }

    result_state = await app.ainvoke(initial_state)

    nav_opts = [
        {
            "leg_key": p.get("leg_key"),
            "target": p.get("target"),
            "distance_km": round(float(p.get("distance_km") or 0.0), 3),
            "eta_minutes": round(float(p.get("eta_minutes") or 0.0), 3),
            "routing_source": p.get("routing_source"),
            "warehouse_name": (p.get("warehouse") or {}).get("name") if p.get("target") == "warehouse" else None,
        }
        for p in (result_state.get("route_packages") or [])
    ]
    staging_out = list(result_state.get("staging_options") or [])

    return {
        "reroute_suggested": bool(result_state.get("reroute_suggested")),
        "warehouse_candidate": result_state.get("warehouse_candidate"),
        "confidence_score": result_state.get("confidence_score"),
        "decision_reason": result_state.get("decision_reason", ""),
        "reasoning_trace": result_state.get("reasoning_trace", ""),
        "llm_prompt": result_state.get("llm_prompt") or "",
        "llm_response": result_state.get("llm_response") or "",
        "environment_assessment": result_state.get("environment_assessment"),
        "staging_options": staging_out,
        "navigation_options": nav_opts,
    }
