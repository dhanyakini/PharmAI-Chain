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


def estimate_minutes_until_internal_at_or_below(
    *,
    internal_temp_f: float,
    external_temp_f: float,
    threshold_f: float,
    max_sim_hours: float = 48.0,
    dt_hours: float = 0.05,
) -> float | None:
    """Step the thermal model forward until internal temp reaches ``threshold_f`` or horizon ends.

    Returns minutes until crossing, ``0.0`` if already at/below threshold, or ``None`` if the
    trajectory does not cross within ``max_sim_hours`` (stable above threshold in this simple model).
    """
    t = float(internal_temp_f)
    if t <= threshold_f:
        return 0.0
    steps = max(1, int(max_sim_hours / dt_hours))
    for step in range(1, steps + 1):
        t = update_internal_temp_f(
            internal_temp_f=t,
            external_temp_f=external_temp_f,
            dt_hours=dt_hours,
        )
        if t <= threshold_f:
            return float(step * dt_hours * 60.0)
    return None

