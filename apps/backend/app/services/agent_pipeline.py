"""Reroute suggestion entrypoint: agentic planner/critic/supervisor + deterministic fallback + observability."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models import Shipment, ShipmentStatus
from app.schemas.agent_schemas import AgentDecision
from app.services.agent_graph import run_agentic_planner_critic_supervisor
from app.services.agent_memory_service import (
    persist_agent_decision_log,
    record_suggestion_in_memory,
)
from app.services.warehouse_service import (
    nullify_warehouse_if_final_is_as_close_or_closer,
    pick_nearest_cold_storage_warehouse,
)


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
    blizzard_scenario_id: int | None = None,
) -> dict[str, Any]:
    """Return reroute suggestion only (no auto-apply). Persists observability rows (same transaction as caller)."""
    settings = get_settings()

    if shipment.status == ShipmentStatus.rerouted and internal_temp_f <= settings.temperature_threshold_f:
        wh = await pick_nearest_cold_storage_warehouse(session, lat=current_lat, lng=current_lng)
        wh = nullify_warehouse_if_final_is_as_close_or_closer(
            truck_lat=current_lat,
            truck_lng=current_lng,
            final_lat=float(shipment.destination_lat),
            final_lng=float(shipment.destination_lng),
            warehouse=wh,
        )
        ad = AgentDecision(
            reroute_suggested=False,
            target="warehouse" if wh else "final",
            warehouse_id=int(wh["id"]) if wh and wh.get("id") is not None else None,
            confidence=None,
            reasoning="Reroute already active; nearest staging attached for routing context.",
            constraints_checked={"spam_guard": "rerouted_and_cold"},
            candidate_actions=[],
            agentic_path="spam_guard",
        )
        out = {
            "reroute_suggested": False,
            "reason": "Reroute already active; waiting for temperature stabilization",
            "warehouse_candidate": wh,
            "decision_reason": (
                f"internal_temp_f={internal_temp_f:.2f}F; reroute active, ambient risk continues."
            ),
            "reasoning_trace": "Nearest cold-storage staging point attached for routing while cargo recovers.",
            "confidence_score": None,
            "llm_prompt": "",
            "llm_response": "",
            "environment_assessment": None,
            "staging_options": [wh] if wh else [],
            "navigation_options": [],
            "agent_decision": ad.model_dump(),
        }
        await persist_agent_decision_log(
            session,
            shipment_id=shipment.id,
            decision_json=ad.model_dump(),
            planner_json=None,
            critic_json=None,
            tool_traces_json={"spam_guard": True},
            supervisor_json=None,
        )
        await record_suggestion_in_memory(
            session,
            shipment.id,
            target=ad.target,
            warehouse_id=ad.warehouse_id,
            reroute_suggested=False,
        )
        return out

    legacy, ad, obs = await run_agentic_planner_critic_supervisor(
        session,
        shipment,
        current_lat=current_lat,
        current_lng=current_lng,
        internal_temp_f=internal_temp_f,
        external_temp_f=external_temp_f,
        weather_state=weather_state,
        risk_level=risk_level,
        blizzard_scenario_id=blizzard_scenario_id,
    )

    steps = list(obs.get("steps") or [])
    planner_step = next((s for s in steps if s.get("name") == "planner"), None)
    critic_step = next((s for s in steps if s.get("name") == "critic"), None)
    supervisor_step = next((s for s in steps if s.get("name") == "supervisor"), None)
    await persist_agent_decision_log(
        session,
        shipment_id=shipment.id,
        decision_json=ad.model_dump(),
        planner_json=planner_step,
        critic_json=critic_step,
        tool_traces_json=obs,
        supervisor_json=supervisor_step,
    )
    await record_suggestion_in_memory(
        session,
        shipment.id,
        target=ad.target,
        warehouse_id=ad.warehouse_id,
        reroute_suggested=ad.reroute_suggested,
    )

    legacy["agent_decision"] = ad.model_dump()
    return legacy
