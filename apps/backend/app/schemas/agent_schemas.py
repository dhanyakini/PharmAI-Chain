"""Pydantic models for agentic reroute decisions and tool I/O."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WarehouseLegSummary(BaseModel):
    """One warehouse option from tools (no hallucinated coordinates)."""

    warehouse_id: int
    name: str
    distance_km: float
    eta_minutes: float
    routing_source: str = ""


class FinalLegSummary(BaseModel):
    distance_km: float
    eta_minutes: float
    routing_source: str = ""


class RouteLegsToolResult(BaseModel):
    """Structured output of tool_route_legs."""

    truck_lat: float
    truck_lng: float
    final: FinalLegSummary
    warehouses: list[WarehouseLegSummary] = Field(default_factory=list)
    raw_packages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Full OSRM leg dicts for evaluation (no hallucination).",
    )


class ThermalRiskToolResult(BaseModel):
    temperature_threshold_f: float
    internal_temp_f: float
    external_temp_f: float
    estimated_minutes_to_cold_threshold: float | None = None
    thermal_stress: str = "unknown"
    cold_violation: bool = False


class WeatherToolResult(BaseModel):
    weather_state: str
    external_temp_f: float
    risk_level: float
    source: str = ""


class MemoryToolResult(BaseModel):
    """Per-shipment memory from DB (feedback loop)."""

    rejected_warehouse_ids: list[int] = Field(default_factory=list)
    last_suggestion: dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class WarehousesToolResult(BaseModel):
    warehouses: list[dict[str, Any]] = Field(default_factory=list)


class PlannerCandidate(BaseModel):
    """Single proposed action — must reference tool-allowed IDs only."""

    candidate_id: str = Field(..., description="Stable id e.g. c1, c2")
    target: Literal["final", "warehouse"]
    warehouse_id: int | None = None
    rationale: str = ""


class PlannerOutput(BaseModel):
    candidates: list[PlannerCandidate] = Field(min_length=1, max_length=5)


class EvaluatedCandidate(BaseModel):
    candidate_id: str
    target: Literal["final", "warehouse"]
    warehouse_id: int | None
    distance_km: float | None = None
    eta_minutes: float | None = None
    routing_source: str | None = None
    rationale: str = ""


class SupervisorPick(BaseModel):
    chosen_candidate_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class AgentDecision(BaseModel):
    reroute_suggested: bool
    target: Literal["final", "warehouse"] | None = None
    warehouse_id: int | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning: str = ""
    constraints_checked: dict[str, Any] = Field(default_factory=dict)
    candidate_actions: list[EvaluatedCandidate] = Field(default_factory=list)
    agentic_path: Literal["llm", "deterministic_fallback", "spam_guard"] = "deterministic_fallback"
