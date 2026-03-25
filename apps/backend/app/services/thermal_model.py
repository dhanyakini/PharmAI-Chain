"""Cold-chain thermal model (internal temperature dynamics)."""

from __future__ import annotations

from app.core.config import get_settings


def update_internal_temp_f(
    *,
    internal_temp_f: float,
    external_temp_f: float,
    dt_hours: float,
) -> float:
    """Update internal temperature using a simple coupled thermal model.

    dT/dt = coupling*(external - internal) + hvac_strength*(setpoint - internal)
    """
    settings = get_settings()

    coupling_term = settings.thermal_coupling_per_hour * (external_temp_f - internal_temp_f)
    hvac_term = settings.hvac_strength_per_hour * (settings.hvac_setpoint_f - internal_temp_f)
    d_temp = dt_hours * (coupling_term + hvac_term)
    return internal_temp_f + d_temp

