"""Minimal backend entrypoint.

This rebuild intentionally keeps only:
- PostgreSQL table init (and local rebuild reset)
- Redis connectivity check for `/health`
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.state import app_state
from app.api.auth import router as auth_router
from app.api.shipments import router as shipments_router
from app.api.routes import router as routes_router
from app.api.simulation import router as simulation_router
from app.api.websocket import router as websocket_router
from app.api.dashboard import router as dashboard_router
from app.database.session import get_engine, get_session_factory, init_db, reset_db
from app.services.pubsub_service import get_redis_client
from app.database.seed import seed_admin_user, seed_blizzard_scenarios, seed_warehouse_candidates

log = logging.getLogger(__name__)


def _db_connection_failed(exc: BaseException) -> bool:
    if isinstance(exc, ConnectionRefusedError):
        return True
    msg = str(exc).lower()
    if (
        "connection refused" in msg
        or "connect call failed" in msg
        or "errno 61" in msg
        or "could not connect" in msg
    ):
        return True
    if exc.__cause__ is not None:
        return _db_connection_failed(exc.__cause__)
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()

    # Data-destructive reset on local env so you can truly rebuild.
    # `apps/backend/.env` uses ENV=local; docker-compose sets ENV=docker.
    reset_for_rebuild = settings.env == "local"

    try:
        if reset_for_rebuild:
            await reset_db()
        else:
            await init_db()
    except Exception as e:
        if _db_connection_failed(e):
            log.critical(
                "PostgreSQL is not reachable (check DATABASE_URL). "
                "Host uvicorn needs DATABASE_URL with host localhost (not postgres). "
                "If Docker shows only '5432/tcp' under PORTS (no 0.0.0.0:5432->5432), "
                "recreate DB: from repo root run: docker compose up -d --force-recreate postgres redis"
            )
        raise
    app_state.db_ready = True

    # Seed admin user for local/dev so protected routes work.
    try:
        await seed_admin_user()
    except Exception as e:
        log.warning("admin seeding failed: %s", e)
    try:
        await seed_blizzard_scenarios()
    except Exception as e:
        log.warning("blizzard scenario seeding failed: %s", e)
    try:
        await seed_warehouse_candidates()
    except Exception as e:
        log.warning("warehouse candidate seeding failed: %s", e)

    redis_client = None
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        app_state.redis_connected = True
    except Exception as e:
        log.warning("redis unavailable: %s", e)
        app_state.redis_connected = False

    yield

    if redis_client is not None:
        try:
            await redis_client.close()
        except Exception:
            pass
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(shipments_router)
    app.include_router(routes_router)
    app.include_router(simulation_router)
    app.include_router(websocket_router)
    app.include_router(dashboard_router)
    return app


app = create_app()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "db": app_state.db_ready,
        "redis": app_state.redis_connected,
    }
