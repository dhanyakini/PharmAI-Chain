"""Unit tests for pure agent tools (no DB)."""

from __future__ import annotations

from app.services.agent_tools import tool_estimate_thermal_risk


def test_thermal_risk_cold_violation() -> None:
    r = tool_estimate_thermal_risk(
        internal_temp_f=34.0,
        external_temp_f=20.0,
        threshold_f=36.0,
    )
    assert r.cold_violation is True
    assert r.thermal_stress in {"critical", "high", "moderate", "low"}
