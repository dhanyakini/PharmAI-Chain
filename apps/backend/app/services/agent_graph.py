"""Planner → evaluate → critic → supervisor agentic loop with structured LLM output."""

from __future__ import annotations

import json
import logging
from typing import Any, NotRequired, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models import Shipment
from app.schemas.agent_schemas import (
    AgentDecision,
    EvaluatedCandidate,
    PlannerCandidate,
    PlannerOutput,
    SupervisorPick,
)
from app.services.agent_deterministic_runner import _package_utility
from app.services.agent_memory_service import tool_get_memory
from app.services.agent_tools import (
    tool_estimate_thermal_risk,
    tool_get_weather,
    tool_list_warehouses,
    tool_route_legs,
)

log = logging.getLogger(__name__)


class AgenticState(TypedDict, total=False):
    shipment_id: int
    current_lat: float
    current_lng: float
    destination_lat: float
    destination_lng: float
    weather_state_input: str
    risk_level_input: float
    internal_temp_f: float
    external_temp_f: float
    blizzard_scenario_id: int | None
    # perception
    memory: dict[str, Any]
    warehouses: list[dict[str, Any]]
    route_tool: dict[str, Any]
    thermal: dict[str, Any]
    weather_tool: dict[str, Any]
    allowed_warehouse_ids: list[int]
    route_packages: list[dict[str, Any]]
    # planner
    planner_output: dict[str, Any]
    planner_prompt: str
    planner_raw: str
    planner_error: str
    # evaluation
    evaluated: list[dict[str, Any]]
    # critic
    critic_pass_ids: list[str]
    critic_report: dict[str, Any]
    # supervisor
    supervisor_pick: dict[str, Any]
    supervisor_prompt: str
    supervisor_raw: str
    supervisor_error: str
    # outcome
    agent_decision: dict[str, Any]
    fallback_deterministic: bool


async def _perception_block(
    session: AsyncSession,
    shipment: Shipment,
    *,
    current_lat: float,
    current_lng: float,
    internal_temp_f: float,
    external_temp_f: float,
    weather_state: str,
    risk_level: float,
    blizzard_scenario_id: int | None,
) -> dict[str, Any]:
    mem = await tool_get_memory(session, shipment.id)
    wh_res = await tool_list_warehouses(session, lat=current_lat, lng=current_lng, limit=5)
    warehouses = wh_res.warehouses
    routes = await tool_route_legs(
        truck_lat=current_lat,
        truck_lng=current_lng,
        warehouses=warehouses,
        final_destination_lat=float(shipment.destination_lat),
        final_destination_lng=float(shipment.destination_lng),
    )
    thermal = tool_estimate_thermal_risk(
        internal_temp_f=internal_temp_f,
        external_temp_f=external_temp_f,
    )
    weather_t = await tool_get_weather(
        session,
        lat=current_lat,
        lng=current_lng,
        blizzard_scenario_id=blizzard_scenario_id,
    )
    allowed_ids = [int(w["id"]) for w in warehouses if w.get("id") is not None]
    route_packages = list(routes.raw_packages)

    return {
        "memory": mem,
        "warehouses": warehouses,
        "route_tool": routes.model_dump(),
        "thermal": thermal.model_dump(),
        "weather_tool": weather_t.model_dump(),
        "allowed_warehouse_ids": allowed_ids,
        "route_packages": route_packages,
        "weather_state_input": weather_state,
        "risk_level_input": risk_level,
    }


async def run_agentic_planner_critic_supervisor(
    session: AsyncSession,
    shipment: Shipment,
    *,
    current_lat: float,
    current_lng: float,
    internal_temp_f: float,
    external_temp_f: float,
    weather_state: str,
    risk_level: float,
    blizzard_scenario_id: int | None = None,
) -> tuple[dict[str, Any], AgentDecision, dict[str, Any]]:
    """Returns (legacy_api_dict, AgentDecision, observability_bundle)."""
    settings = get_settings()
    obs: dict[str, Any] = {"steps": []}

    perc = await _perception_block(
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
    obs["steps"].append({"name": "perception", "tool_traces": perc})

    memory = perc["memory"]
    rejected_ids = set(int(x) for x in (memory.get("rejected_warehouse_ids") or []) if x is not None)
    warehouses = perc["warehouses"]
    route_packages = perc["route_packages"]
    allowed_ids = set(perc["allowed_warehouse_ids"])

    key = (settings.groq_api_key or "").strip()
    if not key:
        det = await _run_deterministic_and_merge(
            session,
            shipment,
            current_lat=current_lat,
            current_lng=current_lng,
            internal_temp_f=internal_temp_f,
            external_temp_f=external_temp_f,
            weather_state=weather_state,
            risk_level=risk_level,
            perc=perc,
        )
        return det

    # --- LangGraph: planner → evaluate → critic → supervisor ---
    async def planner_node(state: AgenticState) -> dict[str, Any]:
        schema_hint = PlannerOutput.model_json_schema()
        prompt = (
            "You are a cold-chain logistics PLANNER. Propose 2-3 DISTINCT candidate actions.\n"
            "Rules:\n"
            "- Each candidate must have target 'final' OR 'warehouse'.\n"
            "- If warehouse, warehouse_id MUST be one of these integers ONLY: "
            f"{sorted(allowed_ids) if allowed_ids else '[] (no warehouses — use final only)'}.\n"
            "- Do NOT propose warehouse_id in this rejected set (operator already declined): "
            f"{sorted(rejected_ids)}.\n"
            "- Prefer safety when weather risk is high or internal temp is at/below threshold.\n\n"
            f"Simulation inputs: weather_state={state['weather_state_input']}, risk={state['risk_level_input']}, "
            f"internal_temp_f={state['internal_temp_f']}, external_temp_f={state['external_temp_f']}.\n"
            f"Thermal tool: {json.dumps(state.get('thermal') or {})}\n"
            f"Weather tool: {json.dumps(state.get('weather_tool') or {})}\n"
            f"Allowed warehouse ids: {list(allowed_ids)}\n\n"
            "Respond with JSON ONLY matching this schema keys:\n"
            f"{json.dumps(schema_hint, indent=0)[:3500]}\n"
        )
        raw = ""
        err = ""
        out_dict: dict[str, Any] = {}
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=key, base_url=settings.groq_base_url)
            resp = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.15,
                response_format={"type": "json_object"},
            )
            raw = (resp.choices[0].message.content or "").strip()
            parsed = json.loads(raw)
            PlannerOutput.model_validate(parsed)
            out_dict = parsed
        except Exception as e:
            err = str(e)
            log.warning("planner LLM failed: %s", e)
            try:
                fix_prompt = (
                    "Your previous output was invalid. Emit ONLY valid JSON for keys "
                    '{"candidates":[{"candidate_id":str,"target":"final"|"warehouse",'
                    '"warehouse_id":int|null,"rationale":str},...]} with 2-3 items.\n'
                    f"Error: {err}\nRaw: {raw[:800]}"
                )
                from openai import AsyncOpenAI

                client = AsyncOpenAI(api_key=key, base_url=settings.groq_base_url)
                resp2 = await client.chat.completions.create(
                    model=settings.groq_model,
                    messages=[{"role": "user", "content": fix_prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                raw = (resp2.choices[0].message.content or "").strip()
                parsed = json.loads(raw)
                PlannerOutput.model_validate(parsed)
                out_dict = parsed
                err = ""
            except Exception as e2:
                err = f"{err}; retry: {e2}"
        if err or not (out_dict.get("candidates")):
            fb: list[dict[str, Any]] = [
                {
                    "candidate_id": "fallback_final",
                    "target": "final",
                    "warehouse_id": None,
                    "rationale": "Planner LLM unavailable or invalid; default continue to destination.",
                }
            ]
            if allowed_ids:
                fb.append(
                    {
                        "candidate_id": "fallback_wh",
                        "target": "warehouse",
                        "warehouse_id": sorted(allowed_ids)[0],
                        "rationale": "Planner fallback: nearest tool-listed cold hub.",
                    }
                )
            out_dict = {"candidates": fb}
            err = (err + "; used structured fallback candidates").strip("; ")
        return {
            "planner_output": out_dict,
            "planner_prompt": prompt,
            "planner_raw": raw,
            "planner_error": err,
        }

    async def evaluate_node(state: AgenticState) -> dict[str, Any]:
        try:
            parsed = PlannerOutput.model_validate(state.get("planner_output") or {"candidates": []})
        except Exception:
            parsed = PlannerOutput(
                candidates=[
                    PlannerCandidate(
                        candidate_id="eval_fallback",
                        target="final",
                        warehouse_id=None,
                        rationale="invalid planner json",
                    )
                ]
            )
        evaluated: list[dict[str, Any]] = []
        by_leg: dict[str, dict[str, Any]] = {}
        for p in state.get("route_packages") or []:
            if p.get("target") == "final":
                by_leg["final"] = p
            elif p.get("target") == "warehouse":
                w = p.get("warehouse") or {}
                if w.get("id") is not None:
                    by_leg[f"wh:{w['id']}"] = p

        for c in parsed.candidates:
            ev: dict[str, Any] = {
                "candidate_id": c.candidate_id,
                "target": c.target,
                "warehouse_id": c.warehouse_id,
                "rationale": c.rationale,
                "distance_km": None,
                "eta_minutes": None,
                "routing_source": None,
            }
            if c.target == "final":
                leg = by_leg.get("final")
            else:
                leg = by_leg.get(f"wh:{c.warehouse_id}") if c.warehouse_id is not None else None
            if leg:
                ev["distance_km"] = float(leg.get("distance_km") or 0.0)
                ev["eta_minutes"] = float(leg.get("eta_minutes") or 0.0)
                ev["routing_source"] = leg.get("routing_source")
            evaluated.append(ev)
        return {"evaluated": evaluated}

    async def critic_node(state: AgenticState) -> dict[str, Any]:
        evaluated = state.get("evaluated") or []
        pass_ids: list[str] = []
        violations: dict[str, list[str]] = {}
        for ev in evaluated:
            cid = str(ev.get("candidate_id") or "")
            bad: list[str] = []
            tgt = ev.get("target")
            wid = ev.get("warehouse_id")
            if tgt == "warehouse":
                if wid is None:
                    bad.append("warehouse target missing warehouse_id")
                elif int(wid) not in allowed_ids:
                    bad.append(f"warehouse_id {wid} not in tool allowlist")
                elif int(wid) in rejected_ids:
                    bad.append(f"warehouse_id {wid} was rejected by operator previously")
            elif tgt != "final":
                bad.append("invalid target")
            if tgt == "warehouse" and wid is not None and not bad:
                leg = None
                for p in route_packages:
                    if p.get("target") == "warehouse":
                        w = p.get("warehouse") or {}
                        if w.get("id") == wid:
                            leg = p
                            break
                if leg is None:
                    bad.append("no OSRM leg for warehouse")
            if not bad:
                pass_ids.append(cid)
            violations[cid] = bad
        return {
            "critic_pass_ids": pass_ids,
            "critic_report": {"violations": violations, "passed": pass_ids},
        }

    async def supervisor_node(state: AgenticState) -> dict[str, Any]:
        evaluated = state.get("evaluated") or []
        pass_ids = set(state.get("critic_pass_ids") or [])
        passing = [e for e in evaluated if e.get("candidate_id") in pass_ids]
        cold = float(state["internal_temp_f"]) <= float(settings.temperature_threshold_f)
        blizzard = str(state["weather_state_input"]).lower() == "blizzard"
        risk = float(state["risk_level_input"])

        if not passing:
            best = max(
                route_packages,
                key=lambda p: _package_utility(
                    p,
                    risk_level=risk,
                    blizzard=blizzard,
                    weights_safety=settings.supervisor_weight_safety,
                    weights_time=settings.supervisor_weight_time,
                    weights_cost=settings.supervisor_weight_cost,
                ),
            )
            dec = _decision_from_package(
                best,
                warehouses,
                cold,
                blizzard,
                risk,
                route_packages,
                truck_lat=float(state["current_lat"]),
                truck_lng=float(state["current_lng"]),
                dest_lat=float(state["destination_lat"]),
                dest_lng=float(state["destination_lng"]),
            )
            ad = _agent_decision_from_evaluated(
                dec,
                evaluated,
                agentic_path="deterministic_fallback",
                constraints={"critic": "all planner candidates failed constraints; utility fallback"},
            )
            return {
                "supervisor_pick": {},
                "supervisor_prompt": "",
                "supervisor_raw": "critic_failed_utility_fallback",
                "supervisor_error": "",
                "agent_decision": ad.model_dump(),
                "fallback_deterministic": True,
            }

        prompt = (
            "You are the SUPERVISOR. Pick exactly one candidate_id from the list that passed safety checks.\n"
            f"Passing candidates JSON: {json.dumps(passing)}\n"
            f"Context: cold_chain_violation_risk cold={cold}, blizzard={blizzard}, risk={risk}.\n"
            "Respond JSON ONLY: {\"chosen_candidate_id\": str, \"confidence\": float 0-1, \"reasoning\": str}\n"
        )
        raw = ""
        err = ""
        pick_dict: dict[str, Any] = {}
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=key, base_url=settings.groq_base_url)
            resp = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            raw = (resp.choices[0].message.content or "").strip()
            pick_dict = json.loads(raw)
            SupervisorPick.model_validate(pick_dict)
        except Exception as e:
            err = str(e)
            try:
                from openai import AsyncOpenAI

                fix = f"Invalid JSON. Error: {err}. Emit only {{\"chosen_candidate_id\",\"confidence\",\"reasoning\"}}.\nRaw:{raw[:500]}"
                client = AsyncOpenAI(api_key=key, base_url=settings.groq_base_url)
                resp2 = await client.chat.completions.create(
                    model=settings.groq_model,
                    messages=[{"role": "user", "content": fix}],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                raw = (resp2.choices[0].message.content or "").strip()
                pick_dict = json.loads(raw)
                SupervisorPick.model_validate(pick_dict)
                err = ""
            except Exception as e2:
                err = str(e2)
                pick_dict = {}

        chosen_id = str(pick_dict.get("chosen_candidate_id") or "")
        if chosen_id not in pass_ids and passing:
            chosen_id = str(passing[0].get("candidate_id") or "")
            err = (err + "; invalid pick, default first passing").strip("; ")

        chosen_ev = next((e for e in passing if e.get("candidate_id") == chosen_id), passing[0])
        tgt = chosen_ev.get("target")
        wid = chosen_ev.get("warehouse_id")
        reroute = bool(cold or blizzard or risk >= 0.5 or tgt == "warehouse")
        wh_cand = None
        if tgt == "warehouse" and wid is not None:
            for w in warehouses:
                if w.get("id") == wid:
                    wh_cand = {k: v for k, v in w.items() if k != "straight_line_km"}
                    break
        if reroute and wh_cand is None and tgt == "warehouse":
            reroute = cold or blizzard or risk >= 0.5

        conf = pick_dict.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf_f = None
        if conf_f is None:
            conf_f = max(0.1, min(0.95, risk * 0.8 + (0.1 if blizzard else 0.0))) if reroute else None

        reasoning = str(pick_dict.get("reasoning") or "") or f"Selected {chosen_id}"

        ec_list = [EvaluatedCandidate.model_validate({**e}) for e in evaluated]
        ad = AgentDecision(
            reroute_suggested=reroute,
            target=tgt if tgt in ("final", "warehouse") else "final",
            warehouse_id=int(wid) if wid is not None and tgt == "warehouse" else None,
            confidence=conf_f,
            reasoning=reasoning,
            constraints_checked={
                "critic_pass_ids": list(pass_ids),
                "critic": state.get("critic_report") or {},
            },
            candidate_actions=ec_list,
            agentic_path="llm",
        )
        return {
            "supervisor_pick": pick_dict,
            "supervisor_prompt": prompt,
            "supervisor_raw": raw,
            "supervisor_error": err,
            "agent_decision": ad.model_dump(),
            "fallback_deterministic": False,
        }

    graph = StateGraph(AgenticState)
    graph.add_node("planner", planner_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("critic", critic_node)
    graph.add_node("supervisor", supervisor_node)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "evaluate")
    graph.add_edge("evaluate", "critic")
    graph.add_edge("critic", "supervisor")
    graph.add_edge("supervisor", END)
    app = graph.compile()

    initial: AgenticState = {
        "shipment_id": shipment.id,
        "current_lat": current_lat,
        "current_lng": current_lng,
        "destination_lat": float(shipment.destination_lat),
        "destination_lng": float(shipment.destination_lng),
        "weather_state_input": weather_state,
        "risk_level_input": risk_level,
        "internal_temp_f": internal_temp_f,
        "external_temp_f": external_temp_f,
        "blizzard_scenario_id": blizzard_scenario_id,
        "memory": memory,
        "warehouses": warehouses,
        "route_tool": perc["route_tool"],
        "thermal": perc["thermal"],
        "weather_tool": perc["weather_tool"],
        "allowed_warehouse_ids": list(allowed_ids),
        "route_packages": route_packages,
    }

    final_state = await app.ainvoke(initial)
    obs["steps"].extend(
        [
            {"name": "planner", "output": final_state.get("planner_output"), "error": final_state.get("planner_error")},
            {"name": "evaluate", "evaluated": final_state.get("evaluated")},
            {"name": "critic", "report": final_state.get("critic_report")},
            {
                "name": "supervisor",
                "pick": final_state.get("supervisor_pick"),
                "error": final_state.get("supervisor_error"),
            },
        ]
    )

    ad = AgentDecision.model_validate(final_state.get("agent_decision") or {})
    legacy = _legacy_dict_from_agent_decision(
        ad,
        final_state,
        warehouses,
        route_packages,
        perc,
        settings,
    )
    return legacy, ad, obs


def _decision_from_package(
    best: dict[str, Any],
    warehouses: list[dict[str, Any]],
    cold: bool,
    blizzard: bool,
    risk: float,
    route_packages: list[dict[str, Any]],
    *,
    truck_lat: float,
    truck_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict[str, Any]:
    from app.services.agent_deterministic_runner import (
        _apply_prefer_final_if_no_farther_than_staging,
        _warehouse_for_api,
    )

    staging = warehouses
    warehouse_candidate = None
    if best.get("target") == "warehouse" and isinstance(best.get("warehouse"), dict):
        warehouse_candidate = _warehouse_for_api(best["warehouse"])
    elif cold or blizzard:
        warehouse_candidate = _warehouse_for_api(staging[0]) if staging else None
    reroute_suggested = bool(
        cold or blizzard or risk >= 0.5 or best.get("target") == "warehouse"
    )
    if reroute_suggested and warehouse_candidate is None and staging:
        warehouse_candidate = _warehouse_for_api(staging[0])
    note = ""
    warehouse_candidate, note = _apply_prefer_final_if_no_farther_than_staging(
        packages=route_packages,
        warehouse_candidate=warehouse_candidate,
        truck_lat=truck_lat,
        truck_lng=truck_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
    )
    return {
        "warehouse_candidate": warehouse_candidate,
        "reroute_suggested": reroute_suggested,
        "confidence": max(0.1, min(0.95, risk * 0.8 + (0.1 if blizzard else 0.0)))
        if reroute_suggested
        else None,
        "reasoning": note or "utility_fallback",
    }


def _agent_decision_from_evaluated(
    dec: dict[str, Any],
    evaluated: list[dict[str, Any]],
    *,
    agentic_path: Any,
    constraints: dict[str, Any],
) -> AgentDecision:
    wh = dec.get("warehouse_candidate")
    wid = int(wh["id"]) if isinstance(wh, dict) and wh.get("id") is not None else None
    tgt = "warehouse" if wid is not None else "final"
    ec_list = [EvaluatedCandidate.model_validate({**e}) for e in evaluated]
    return AgentDecision(
        reroute_suggested=bool(dec.get("reroute_suggested")),
        target=tgt,
        warehouse_id=wid,
        confidence=dec.get("confidence"),
        reasoning=str(dec.get("reasoning") or ""),
        constraints_checked=constraints,
        candidate_actions=ec_list,
        agentic_path=agentic_path,
    )


def _legacy_dict_from_agent_decision(
    ad: AgentDecision,
    final_state: AgenticState,
    warehouses: list[dict[str, Any]],
    route_packages: list[dict[str, Any]],
    perc: dict[str, Any],
    settings: Any,
) -> dict[str, Any]:
    wh_cand = None
    if ad.target == "warehouse" and ad.warehouse_id is not None:
        for w in warehouses:
            if w.get("id") == ad.warehouse_id:
                wh_cand = {k: v for k, v in w.items() if k != "straight_line_km"}
                break
    from app.services.warehouse_service import nullify_warehouse_if_final_is_as_close_or_closer

    truck_lat = float(final_state.get("current_lat") or 0)
    truck_lng = float(final_state.get("current_lng") or 0)
    dest_lat = float(final_state.get("destination_lat") or 0)
    dest_lng = float(final_state.get("destination_lng") or 0)
    wh_cand = nullify_warehouse_if_final_is_as_close_or_closer(
        truck_lat=truck_lat,
        truck_lng=truck_lng,
        final_lat=dest_lat,
        final_lng=dest_lng,
        warehouse=wh_cand,
    )
    nav_opts = [
        {
            "leg_key": p.get("leg_key"),
            "target": p.get("target"),
            "distance_km": round(float(p.get("distance_km") or 0.0), 3),
            "eta_minutes": round(float(p.get("eta_minutes") or 0.0), 3),
            "routing_source": p.get("routing_source"),
            "warehouse_name": (p.get("warehouse") or {}).get("name") if p.get("target") == "warehouse" else None,
        }
        for p in route_packages
    ]
    th = perc.get("thermal") if isinstance(perc.get("thermal"), dict) else {}
    env_assembly = {
        "internal_temp_f": final_state.get("internal_temp_f"),
        "external_temp_f": final_state.get("external_temp_f"),
        "weather_state": final_state.get("weather_state_input"),
        "risk_level": final_state.get("risk_level_input"),
        **th,
    }
    decision_reason = (
        f"internal={th.get('internal_temp_f')}F external={th.get('external_temp_f')}F "
        f"thermal_stress={th.get('thermal_stress')} weather={final_state.get('weather_state_input')} "
        f"risk={final_state.get('risk_level_input')}"
    )
    return {
        "reroute_suggested": ad.reroute_suggested,
        "warehouse_candidate": wh_cand,
        "confidence_score": ad.confidence,
        "decision_reason": decision_reason,
        "reasoning_trace": ad.reasoning,
        "llm_prompt": (final_state.get("planner_prompt") or "") + "\n---\n" + (final_state.get("supervisor_prompt") or ""),
        "llm_response": (final_state.get("planner_raw") or "") + "\n---\n" + (final_state.get("supervisor_raw") or ""),
        "environment_assessment": env_assembly,
        "staging_options": warehouses,
        "navigation_options": nav_opts,
        "agent_decision": ad.model_dump(),
    }


async def _run_deterministic_and_merge(
    session: AsyncSession,
    shipment: Shipment,
    *,
    current_lat: float,
    current_lng: float,
    internal_temp_f: float,
    external_temp_f: float,
    weather_state: str,
    risk_level: float,
    perc: dict[str, Any],
) -> tuple[dict[str, Any], AgentDecision, dict[str, Any]]:
    from app.services.agent_deterministic_runner import run_deterministic_langgraph

    legacy = await run_deterministic_langgraph(
        session=session,
        shipment=shipment,
        current_lat=current_lat,
        current_lng=current_lng,
        internal_temp_f=internal_temp_f,
        external_temp_f=external_temp_f,
        weather_state=weather_state,
        risk_level=risk_level,
    )
    wh = legacy.get("warehouse_candidate")
    wid = int(wh["id"]) if isinstance(wh, dict) and wh.get("id") is not None else None
    evaluated: list[EvaluatedCandidate] = []
    ad = AgentDecision(
        reroute_suggested=bool(legacy.get("reroute_suggested")),
        target="warehouse" if wid is not None else "final",
        warehouse_id=wid,
        confidence=legacy.get("confidence_score"),
        reasoning=str(legacy.get("reasoning_trace") or ""),
        constraints_checked={"source": "deterministic_langgraph"},
        candidate_actions=evaluated,
        agentic_path="deterministic_fallback",
    )
    legacy["agent_decision"] = ad.model_dump()
    obs = {"steps": [{"name": "perception", "tool_traces": perc}, {"name": "deterministic_graph"}]}
    return legacy, ad, obs
