"""DB persistence for agent memory and decision observability."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AgentDecisionLog, AgentShipmentMemory, utcnow


async def tool_get_memory(session: AsyncSession, shipment_id: int) -> dict[str, Any]:
    q = await session.execute(
        select(AgentShipmentMemory).where(AgentShipmentMemory.shipment_id == shipment_id)
    )
    row = q.scalar_one_or_none()
    if row is None:
        return {
            "rejected_warehouse_ids": [],
            "rejected_targets": [],
            "last_suggestion": None,
        }
    data = dict(row.memory_json) if isinstance(row.memory_json, dict) else {}
    data.setdefault("rejected_warehouse_ids", [])
    data.setdefault("rejected_targets", [])
    data.setdefault("last_suggestion", None)
    return data


async def tool_put_memory_merge(
    session: AsyncSession,
    shipment_id: int,
    patch: dict[str, Any],
) -> None:
    q = await session.execute(
        select(AgentShipmentMemory).where(AgentShipmentMemory.shipment_id == shipment_id)
    )
    row = q.scalar_one_or_none()
    if row is None:
        row = AgentShipmentMemory(shipment_id=shipment_id, memory_json=dict(patch))
        session.add(row)
    else:
        base = dict(row.memory_json) if isinstance(row.memory_json, dict) else {}
        base.update(patch)
        row.memory_json = base
        session.add(row)


async def record_suggestion_in_memory(
    session: AsyncSession,
    shipment_id: int,
    *,
    target: str | None,
    warehouse_id: int | None,
    reroute_suggested: bool,
) -> None:
    mem = await tool_get_memory(session, shipment_id)
    mem["last_suggestion"] = {
        "target": target,
        "warehouse_id": warehouse_id,
        "reroute_suggested": reroute_suggested,
        "at": utcnow().isoformat(),
    }
    await tool_put_memory_merge(session, shipment_id, mem)


async def append_rejected_suggestion(
    session: AsyncSession,
    shipment_id: int,
    *,
    target: str | None,
    warehouse_id: int | None,
) -> None:
    mem = await tool_get_memory(session, shipment_id)
    rids = list(mem.get("rejected_warehouse_ids") or [])
    if warehouse_id is not None and target == "warehouse" and warehouse_id not in rids:
        rids.append(int(warehouse_id))
    mem["rejected_warehouse_ids"] = rids
    rt = list(mem.get("rejected_targets") or [])
    rt.append({"target": target, "warehouse_id": warehouse_id, "at": utcnow().isoformat()})
    mem["rejected_targets"] = rt[-20:]
    await tool_put_memory_merge(session, shipment_id, mem)


async def persist_agent_decision_log(
    session: AsyncSession,
    *,
    shipment_id: int,
    decision_json: dict[str, Any],
    planner_json: dict[str, Any] | None = None,
    critic_json: dict[str, Any] | None = None,
    tool_traces_json: dict[str, Any] | None = None,
    supervisor_json: dict[str, Any] | None = None,
) -> int:
    row = AgentDecisionLog(
        shipment_id=shipment_id,
        decision_json=decision_json,
        planner_json=planner_json,
        critic_json=critic_json,
        tool_traces_json=tool_traces_json,
        supervisor_json=supervisor_json,
        operator_feedback=None,
    )
    session.add(row)
    await session.flush()
    return int(row.id)


async def mark_latest_pending_feedback(
    session: AsyncSession,
    shipment_id: int,
    feedback: str,
) -> None:
    """Set operator_feedback on the most recent log row that is still pending."""
    q = await session.execute(
        select(AgentDecisionLog)
        .where(
            AgentDecisionLog.shipment_id == shipment_id,
            AgentDecisionLog.operator_feedback.is_(None),
        )
        .order_by(AgentDecisionLog.created_at.desc())
        .limit(1)
    )
    row = q.scalar_one_or_none()
    if row is not None:
        row.operator_feedback = feedback
        session.add(row)


async def list_agent_decision_logs(
    session: AsyncSession,
    shipment_id: int,
    *,
    limit: int = 50,
) -> list[AgentDecisionLog]:
    q = await session.execute(
        select(AgentDecisionLog)
        .where(AgentDecisionLog.shipment_id == shipment_id)
        .order_by(AgentDecisionLog.created_at.desc())
        .limit(limit)
    )
    return list(q.scalars().all())
