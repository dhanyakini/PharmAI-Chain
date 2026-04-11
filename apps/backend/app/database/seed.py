"""Startup database seeding utilities."""

from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.database.models import BlizzardScenario, User, UserRole, WarehouseCandidate
from app.database.session import get_session_factory


async def seed_admin_user() -> None:
    """Seed an admin user if credentials are available.

    - In docker/prod, provide ADMIN_* env vars.
    - In local, a default admin is seeded unless disabled.
    """
    settings = get_settings()

    username = settings.seed_admin_username
    email = settings.seed_admin_email
    password = settings.seed_admin_password

    if username is None and email is None and password is None:
        if not (settings.env == "local" and settings.seed_admin_defaults_in_local):
            return
        username = "admin"
        email = "admin@example.com"
        password = "admin123456"

    if username is None or email is None or password is None:
        # Partial configuration - don't guess.
        return

    factory = get_session_factory()
    async with factory() as session:
        existing_q = await session.execute(select(User).where(User.username == username))
        existing = existing_q.scalar_one_or_none()
        if existing is not None:
            return

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role=UserRole.admin,
            is_active=True,
        )
        session.add(user)
        await session.commit()


async def seed_blizzard_scenarios() -> None:
    """Curated synthetic severe-winter profiles for simulation (database-backed, not code constants)."""
    factory = get_session_factory()
    async with factory() as session:
        existing = await session.execute(select(BlizzardScenario).limit(1))
        if existing.scalar_one_or_none() is not None:
            return

        scenarios = [
            BlizzardScenario(
                slug="great_lakes_whiteout",
                name="Great Lakes lake-effect whiteout",
                external_temp_f=-8.0,
                wind_speed_mph=48.0,
                visibility_miles=0.08,
                precip_type="snow",
                weather_state="blizzard",
                risk_level=0.95,
                synopsis="Heavy lake-effect snow, gusts 45–50 mph, near-zero visibility.",
            ),
            BlizzardScenario(
                slug="nor_easter_coastal",
                name="Coastal Nor'easter (I-95 corridor)",
                external_temp_f=22.0,
                wind_speed_mph=42.0,
                visibility_miles=0.15,
                precip_type="snow",
                weather_state="blizzard",
                risk_level=0.92,
                synopsis="Rapidly deepening coastal low; blowing snow and coastal surge risk on routes.",
            ),
            BlizzardScenario(
                slug="high_plains_wind_snow",
                name="High Plains wind-driven snow",
                external_temp_f=2.0,
                wind_speed_mph=55.0,
                visibility_miles=0.12,
                precip_type="snow",
                weather_state="blizzard",
                risk_level=0.93,
                synopsis="Ground blizzard conditions: sparse precip but extreme wind and drifting.",
            ),
            BlizzardScenario(
                slug="classic_synoptic_blizzard",
                name="Classic synoptic blizzard",
                external_temp_f=12.0,
                wind_speed_mph=38.0,
                visibility_miles=0.2,
                precip_type="snow",
                weather_state="blizzard",
                risk_level=0.88,
                synopsis="Large-scale winter storm; sustained heavy snow and 35+ mph winds for 12+ hours.",
            ),
            BlizzardScenario(
                slug="polar_vortex_cold",
                name="Polar vortex cold surge (insulin risk)",
                external_temp_f=-18.0,
                wind_speed_mph=28.0,
                visibility_miles=2.0,
                precip_type="none",
                weather_state="extreme_cold",
                risk_level=0.78,
                synopsis="Bitter cold with lighter wind; extreme ambient threatens reefer margins.",
            ),
            BlizzardScenario(
                slug="mild_snow_no_blizzard",
                name="Moderate snow event (sub-blizzard)",
                external_temp_f=30.0,
                wind_speed_mph=14.0,
                visibility_miles=0.75,
                precip_type="snow",
                weather_state="snow",
                risk_level=0.55,
                synopsis="Steady snow but winds below blizzard criteria; elevated slip risk only.",
            ),
        ]
        for s in scenarios:
            session.add(s)
        await session.commit()


_WAREHOUSE_SEED_SPECS: list[dict] = [
    {
        "name": "Sentinel Cold Hub — Hartford",
        "lat": 41.7658,
        "lng": -72.6734,
        "state": "CT",
        "capacity_units": 500,
        "notes": "Regional pharma cross-dock",
    },
    {
        "name": "Sentinel Cold Hub — Albany",
        "lat": 42.6526,
        "lng": -73.7562,
        "state": "NY",
        "capacity_units": 420,
        "notes": "Upstate staging",
    },
    {
        "name": "Sentinel Cold Hub — Springfield MA",
        "lat": 42.1015,
        "lng": -72.5898,
        "state": "MA",
        "capacity_units": 380,
        "notes": "I-91 corridor",
    },
    {
        "name": "Sentinel Cold Hub — Providence",
        "lat": 41.8240,
        "lng": -71.4128,
        "state": "RI",
        "capacity_units": 290,
        "notes": "Southern New England",
    },
    {
        "name": "Sentinel Cold Hub — Boston",
        "lat": 42.3601,
        "lng": -71.0589,
        "state": "MA",
        "capacity_units": 640,
        "notes": "Hub airport / I-90 corridor",
    },
    {
        "name": "Sentinel Cold Hub — New Haven",
        "lat": 41.3083,
        "lng": -72.9279,
        "state": "CT",
        "capacity_units": 340,
        "notes": "I-95 / Yale corridor",
    },
    {
        "name": "Sentinel Cold Hub — Worcester",
        "lat": 42.2626,
        "lng": -71.8023,
        "state": "MA",
        "capacity_units": 310,
        "notes": "Central MA cross-dock",
    },
    {
        "name": "Sentinel Cold Hub — Manchester NH",
        "lat": 42.9956,
        "lng": -71.4548,
        "state": "NH",
        "capacity_units": 260,
        "notes": "Northern New England",
    },
    {
        "name": "Sentinel Cold Hub — Burlington VT",
        "lat": 44.4759,
        "lng": -73.2121,
        "state": "VT",
        "capacity_units": 180,
        "notes": "Champlain valley staging",
    },
    {
        "name": "Sentinel Cold Hub — Newark Metro",
        "lat": 40.7357,
        "lng": -74.1724,
        "state": "NJ",
        "capacity_units": 720,
        "notes": "Port / NYC metro pharma",
    },
    {
        "name": "Sentinel Cold Hub — Philadelphia",
        "lat": 39.9526,
        "lng": -75.1652,
        "state": "PA",
        "capacity_units": 580,
        "notes": "I-95 mid-Atlantic",
    },
    {
        "name": "Sentinel Cold Hub — Buffalo",
        "lat": 42.8864,
        "lng": -78.8784,
        "state": "NY",
        "capacity_units": 400,
        "notes": "Great Lakes / CAN border",
    },
    {
        "name": "Sentinel Cold Hub — Syracuse",
        "lat": 43.0481,
        "lng": -76.1474,
        "state": "NY",
        "capacity_units": 350,
        "notes": "NYS Thruway",
    },
    {
        "name": "Sentinel Cold Hub — Stamford",
        "lat": 41.0534,
        "lng": -73.5387,
        "state": "CT",
        "capacity_units": 410,
        "notes": "NYC exurbs",
    },
    {
        "name": "Sentinel Cold Hub — Portland ME",
        "lat": 43.6591,
        "lng": -70.2568,
        "state": "ME",
        "capacity_units": 220,
        "notes": "Northern I-95 terminus",
    },
    {
        "name": "Sentinel Cold Hub — Pittsburgh",
        "lat": 40.4406,
        "lng": -79.9959,
        "state": "PA",
        "capacity_units": 520,
        "notes": "Ohio River / Midwest link",
    },
]


async def seed_warehouse_candidates() -> None:
    """Insert any missing cold-capable warehouses by unique display name (safe on every startup)."""
    factory = get_session_factory()
    async with factory() as session:
        added = False
        for spec in _WAREHOUSE_SEED_SPECS:
            name = spec["name"]
            dup = await session.execute(select(WarehouseCandidate).where(WarehouseCandidate.name == name))
            if dup.scalar_one_or_none() is not None:
                continue
            session.add(
                WarehouseCandidate(
                    name=name,
                    lat=float(spec["lat"]),
                    lng=float(spec["lng"]),
                    state=str(spec["state"]),
                    has_cold_storage=True,
                    capacity_units=int(spec["capacity_units"]),
                    notes=str(spec.get("notes") or ""),
                )
            )
            added = True
        if added:
            await session.commit()

