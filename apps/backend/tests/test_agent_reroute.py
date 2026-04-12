"""Deterministic agentic reroute scenarios (no Groq): structure, allowlists, persistence."""

from __future__ import annotations

import pytest

from app.database.models import AgentDecisionLog, AgentShipmentMemory, BlizzardScenario
from app.schemas.agent_schemas import AgentDecision
from app.services.agent_memory_service import append_rejected_suggestion, tool_get_memory
from app.services.agent_pipeline import suggest_reroute
from sqlalchemy import func, select


@pytest.mark.parametrize(
    "scenario_slug",
    [
        "test_great_lakes_whiteout",
        "test_polar_vortex",
        "test_mild_snow",
    ],
)
async def test_suggest_reroute_seeded_scenarios_structured(
    seeded_simulation,
    scenario_slug: str,
) -> None:
    bundle = seeded_simulation
    session = bundle["session"]
    ship = bundle["shipment"]
    sid = bundle["scenario_ids"][scenario_slug]

    row = (
        await session.execute(select(BlizzardScenario).where(BlizzardScenario.id == sid))
    ).scalar_one()

    out = await suggest_reroute(
        session=session,
        shipment=ship,
        current_lat=float(ship.current_lat or 0),
        current_lng=float(ship.current_lng or 0),
        internal_temp_f=34.0,
        external_temp_f=float(row.external_temp_f),
        weather_state=str(row.weather_state),
        risk_level=float(row.risk_level),
        blizzard_scenario_id=sid,
    )
    await session.commit()

    ad = AgentDecision.model_validate(out["agent_decision"])
    assert ad.agentic_path == "deterministic_fallback"
    assert isinstance(ad.constraints_checked, dict)
    assert isinstance(out.get("staging_options"), list)
    assert len(out["staging_options"]) >= 1
    # Policy with staging + stub legs typically suggests reroute toward a hub.
    assert out["reroute_suggested"] is True
    allowed_ids = {int(w["id"]) for w in out["staging_options"] if w.get("id") is not None}
    if ad.warehouse_id is not None:
        assert ad.warehouse_id in allowed_ids


async def test_blizzard_scenario_high_risk_reroute_suggested(seeded_simulation) -> None:
    bundle = seeded_simulation
    session = bundle["session"]
    ship = bundle["shipment"]
    sid = bundle["scenario_ids"]["test_great_lakes_whiteout"]

    row = (
        await session.execute(select(BlizzardScenario).where(BlizzardScenario.id == sid))
    ).scalar_one()

    out = await suggest_reroute(
        session=session,
        shipment=ship,
        current_lat=float(ship.current_lat or 0),
        current_lng=float(ship.current_lng or 0),
        internal_temp_f=33.0,
        external_temp_f=float(row.external_temp_f),
        weather_state="blizzard",
        risk_level=0.95,
        blizzard_scenario_id=sid,
    )
    await session.commit()

    assert out["reroute_suggested"] is True
    ad = AgentDecision.model_validate(out["agent_decision"])
    assert ad.reroute_suggested is True
    assert row.weather_state == "blizzard"


async def test_observability_persists_decision_log(seeded_simulation) -> None:
    bundle = seeded_simulation
    session = bundle["session"]
    ship = bundle["shipment"]
    sid = bundle["scenario_ids"]["test_mild_snow"]

    row = (
        await session.execute(select(BlizzardScenario).where(BlizzardScenario.id == sid))
    ).scalar_one()

    before = (
        await session.execute(
            select(func.count()).select_from(AgentDecisionLog).where(AgentDecisionLog.shipment_id == ship.id)
        )
    ).scalar_one()
    assert before == 0

    await suggest_reroute(
        session=session,
        shipment=ship,
        current_lat=float(ship.current_lat or 0),
        current_lng=float(ship.current_lng or 0),
        internal_temp_f=36.0,
        external_temp_f=float(row.external_temp_f),
        weather_state=str(row.weather_state),
        risk_level=float(row.risk_level),
        blizzard_scenario_id=sid,
    )
    await session.commit()

    after = (
        await session.execute(
            select(func.count()).select_from(AgentDecisionLog).where(AgentDecisionLog.shipment_id == ship.id)
        )
    ).scalar_one()
    assert after == 1


async def test_memory_records_rejection(seeded_simulation) -> None:
    bundle = seeded_simulation
    session = bundle["session"]
    ship = bundle["shipment"]

    await append_rejected_suggestion(session, ship.id, target="warehouse", warehouse_id=999)
    await session.commit()

    mem = await tool_get_memory(session, ship.id)
    assert 999 in mem["rejected_warehouse_ids"]


async def test_shipment_memory_row_after_suggestion(seeded_simulation) -> None:
    bundle = seeded_simulation
    session = bundle["session"]
    ship = bundle["shipment"]
    sid = bundle["scenario_ids"]["test_polar_vortex"]

    row = (
        await session.execute(select(BlizzardScenario).where(BlizzardScenario.id == sid))
    ).scalar_one()

    await suggest_reroute(
        session=session,
        shipment=ship,
        current_lat=float(ship.current_lat or 0),
        current_lng=float(ship.current_lng or 0),
        internal_temp_f=34.0,
        external_temp_f=float(row.external_temp_f),
        weather_state=str(row.weather_state),
        risk_level=float(row.risk_level),
        blizzard_scenario_id=sid,
    )
    await session.commit()

    mem_row = (
        await session.execute(select(AgentShipmentMemory).where(AgentShipmentMemory.shipment_id == ship.id))
    ).scalar_one_or_none()
    assert mem_row is not None
    assert isinstance(mem_row.memory_json, dict)
    assert mem_row.memory_json.get("last_suggestion") is not None
