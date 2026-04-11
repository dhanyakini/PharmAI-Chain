"""Reroute suggestion agent pipeline (LangGraph + optional Groq reasoning)."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models import Shipment, ShipmentStatus
from app.services.warehouse_service import haversine_km, pick_nearest_cold_storage_warehouse


class AgentState(TypedDict):
    shipment_status: str
    internal_temp_f: float
    weather_state: str
    risk_level: float
    current_lat: float
    current_lng: float
    destination_lat: float
    destination_lng: float
    warehouse_candidate: NotRequired[dict[str, Any] | None]
    reroute_suggested: NotRequired[bool]
    decision_reason: NotRequired[str]
    reasoning_trace: NotRequired[str]
    llm_prompt: NotRequired[str]
    llm_response: NotRequired[str]
    confidence_score: NotRequired[float | None]


async def suggest_reroute(
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
    """Return reroute suggestion only (no auto-apply)."""
    settings = get_settings()

    # Spam guard: skip full LangGraph re-run while reroute is active and still cold — but still
    # attach nearest warehouse so blizzard/confirm paths can route truck → staging, not → final only.
    if shipment.status == ShipmentStatus.rerouted and internal_temp_f <= settings.temperature_threshold_f:
        wh = await pick_nearest_cold_storage_warehouse(session, lat=current_lat, lng=current_lng)
        return {
            "reroute_suggested": False,
            "reason": "Reroute already active; waiting for temperature stabilization",
            "warehouse_candidate": wh,
            "decision_reason": (
                f"internal_temp_f={internal_temp_f:.2f}F; reroute active, ambient risk continues."
            ),
            "reasoning_trace": "Nearest cold-storage staging point attached for routing while cargo recovers.",
            "confidence_score": None,
        }

    # --- Node implementations (capture session/settings in closures) ---
    async def environment_agent(state: AgentState) -> dict[str, Any]:
        # Trigger happens at threshold; environment agent summarizes risk.
        env_reason = (
            f"internal_temp_f={state['internal_temp_f']:.2f}F, "
            f"weather_state={state['weather_state']}, risk_level={state['risk_level']:.2f}"
        )
        return {
            "decision_reason": env_reason,
        }

    async def dispatcher_agent(state: AgentState) -> dict[str, Any]:
        wh = await pick_nearest_cold_storage_warehouse(
            session,
            lat=float(state["current_lat"]),
            lng=float(state["current_lng"]),
        )
        return {"warehouse_candidate": wh}

    async def supervisor_agent(state: AgentState) -> dict[str, Any]:
        # Weighted decision model (safety/time/cost approximations).
        safety_score = float(state["risk_level"])

        destination_dist_km = haversine_km(
            state["current_lat"],
            state["current_lng"],
            state["destination_lat"],
            state["destination_lng"],
        )
        # Approx time/cost: being closer to a warehouse should reduce emergency staging cost.
        wh = state.get("warehouse_candidate")
        if wh is not None:
            wh_dist_km = haversine_km(
                state["current_lat"], state["current_lng"], float(wh["lat"]), float(wh["lng"])
            )
            extra_cost_penalty = min(1.0, wh_dist_km / (destination_dist_km + 1e-6))
        else:
            extra_cost_penalty = 0.3

        # Decision: reroute if safety outweighs penalty and temperature is cold.
        cold = state["internal_temp_f"] <= settings.temperature_threshold_f
        score = (
            settings.supervisor_weight_safety * safety_score
            - settings.supervisor_weight_cost * extra_cost_penalty
            - settings.supervisor_weight_time * min(1.0, destination_dist_km / 500.0)
        )

        reroute_suggested = bool(cold and score >= 0.1)

        confidence = None
        if reroute_suggested:
            confidence = max(0.1, min(0.95, safety_score * 0.8))

        # Optional Groq reasoning trace for UI/tooling; if it fails, fall back to deterministic text.
        reasoning_trace = state.get("decision_reason", "")
        llm_prompt = (
            "You are a logistics supervisor. Given shipment thermal risk and weather disruption, "
            "decide whether to suggest a mid-route reroute and (optionally) a cold-storage staging warehouse. "
            "Return a short reasoning trace (max 120 words) focusing on safety, time, and cost.\n\n"
            f"shipment_status={state['shipment_status']}\n"
            f"internal_temp_f={state['internal_temp_f']}\n"
            f"weather_state={state['weather_state']}\n"
            f"risk_level={state['risk_level']}\n"
            f"warehouse_candidate={state.get('warehouse_candidate')}\n"
            f"reroute_suggested={reroute_suggested}\n"
        )
        llm_response: str = ""
        try:
            if settings.groq_api_key and settings.groq_api_key.strip():
                from openai import AsyncOpenAI

                client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)
                resp = await client.chat.completions.create(
                    model=settings.groq_model,
                    messages=[{"role": "user", "content": llm_prompt}],
                    temperature=0.2,
                )
                llm_response = (resp.choices[0].message.content or "").strip()
                reasoning_trace = llm_response[:120].strip()
        except Exception:
            reasoning_trace = reasoning_trace or "Cold-chain risk triggered; supervisor recommends reroute."
            llm_response = llm_response or reasoning_trace

        return {
            "reroute_suggested": reroute_suggested,
            "reasoning_trace": reasoning_trace,
            "llm_prompt": llm_prompt,
            "llm_response": llm_response,
            "confidence_score": confidence,
        }

    # --- LangGraph graph wiring ---
    graph = StateGraph(AgentState)
    graph.add_node("environment_agent", environment_agent)
    graph.add_node("dispatcher_agent", dispatcher_agent)
    graph.add_node("supervisor_agent", supervisor_agent)

    graph.set_entry_point("environment_agent")
    graph.add_edge("environment_agent", "dispatcher_agent")
    graph.add_edge("dispatcher_agent", "supervisor_agent")
    graph.add_edge("supervisor_agent", END)

    app = graph.compile()

    initial_state: AgentState = {
        "shipment_status": shipment.status.value,
        "internal_temp_f": internal_temp_f,
        "weather_state": weather_state,
        "risk_level": risk_level,
        "current_lat": current_lat,
        "current_lng": current_lng,
        "destination_lat": shipment.destination_lat,
        "destination_lng": shipment.destination_lng,
        "warehouse_candidate": None,
        "reroute_suggested": False,
        "decision_reason": "",
        "reasoning_trace": "",
        "confidence_score": None,
    }

    result_state = await app.ainvoke(initial_state)
    return {
        "reroute_suggested": bool(result_state.get("reroute_suggested")),
        "warehouse_candidate": result_state.get("warehouse_candidate"),
        "confidence_score": result_state.get("confidence_score"),
        "decision_reason": result_state.get("decision_reason", ""),
        "reasoning_trace": result_state.get("reasoning_trace", ""),
    }

