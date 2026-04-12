"""Test defaults: in-memory SQLite, no Groq, stubbed OSRM routing."""

from __future__ import annotations

import os

# Apply before any `app` import (pydantic-settings: process env wins over .env file).
os.environ.setdefault("SECRET_KEY", "12345678901234567890123456789012")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ.setdefault("GROQ_API_KEY", "")

import pytest


@pytest.fixture(autouse=True)
def _clear_settings_each_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    from app.core.config import clear_settings_cache

    clear_settings_cache()


@pytest.fixture(autouse=True)
async def _fresh_db() -> None:
    from app.core.config import clear_settings_cache
    from app.database.session import reset_db, reset_engine

    clear_settings_cache()
    reset_engine()
    await reset_db()


async def _fake_route_legs_parallel_from_truck(
    *,
    truck_lat: float,
    truck_lng: float,
    legs: list[tuple[str, str, dict | None, float, float]],
) -> list[dict]:
    """Deterministic legs so tests never hit OSRM."""
    out: list[dict] = []
    for leg_key, target, wh, _dlat, _dlng in legs:
        if target == "final":
            dist_km, eta_min = 120.0, 160.0
        else:
            dist_km, eta_min = 35.0, 47.0
        out.append(
            {
                "leg_key": leg_key,
                "target": target,
                "warehouse": wh,
                "distance_km": dist_km,
                "eta_minutes": eta_min,
                "routing_source": "test_stub",
            }
        )
    return out


@pytest.fixture
def stub_osrm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch every module that bound `route_legs_parallel_from_truck` at import time."""
    import app.services.agent_deterministic_runner as det
    import app.services.agent_tools as agent_tools

    monkeypatch.setattr(
        agent_tools,
        "route_legs_parallel_from_truck",
        _fake_route_legs_parallel_from_truck,
    )
    monkeypatch.setattr(
        det,
        "route_legs_parallel_from_truck",
        _fake_route_legs_parallel_from_truck,
    )


@pytest.fixture
async def db_session():
    from app.database.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest.fixture
async def seeded_simulation(db_session, stub_osrm):
    """Minimal warehouses, three BlizzardScenario rows, and one in-transit shipment."""
    from app.database.models import (
        BlizzardScenario,
        Shipment,
        ShipmentStatus,
        WarehouseCandidate,
    )

    wh_specs = [
        ("Near Hub A", 41.7658, -72.6734, "CT", 500),
        ("Near Hub B", 42.6526, -73.7562, "NY", 400),
    ]
    for name, lat, lng, state, cap in wh_specs:
        db_session.add(
            WarehouseCandidate(
                name=name,
                lat=lat,
                lng=lng,
                state=state,
                has_cold_storage=True,
                capacity_units=cap,
            )
        )

    scenarios = [
        BlizzardScenario(
            slug="test_great_lakes_whiteout",
            name="Test Great Lakes whiteout",
            external_temp_f=-8.0,
            wind_speed_mph=48.0,
            visibility_miles=0.08,
            precip_type="snow",
            weather_state="blizzard",
            risk_level=0.95,
            synopsis="Test scenario",
        ),
        BlizzardScenario(
            slug="test_polar_vortex",
            name="Test polar vortex",
            external_temp_f=-18.0,
            wind_speed_mph=28.0,
            visibility_miles=2.0,
            precip_type="none",
            weather_state="extreme_cold",
            risk_level=0.78,
            synopsis="Test scenario",
        ),
        BlizzardScenario(
            slug="test_mild_snow",
            name="Test mild snow",
            external_temp_f=30.0,
            wind_speed_mph=14.0,
            visibility_miles=0.75,
            precip_type="snow",
            weather_state="snow",
            risk_level=0.55,
            synopsis="Test scenario",
        ),
    ]
    for s in scenarios:
        db_session.add(s)

    ship = Shipment(
        shipment_code="TEST-SHIP-001",
        cargo_type="insulin",
        origin_lat=41.0,
        origin_lng=-73.0,
        destination_lat=42.5,
        destination_lng=-71.0,
        truck_name="Test Truck",
        status=ShipmentStatus.in_transit,
        current_lat=41.55,
        current_lng=-72.4,
    )
    db_session.add(ship)
    await db_session.commit()
    await db_session.refresh(ship)

    from sqlalchemy import select

    rows = (await db_session.execute(select(BlizzardScenario))).scalars().all()
    by_slug = {r.slug: r.id for r in rows}
    return {"session": db_session, "shipment": ship, "scenario_ids": by_slug}
