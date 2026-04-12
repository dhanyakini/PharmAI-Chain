# Sentinel — Backend

FastAPI service for **Project Sentinel**: cold-chain **simulation**, **PostgreSQL**, **Redis** pub/sub, **LangGraph** reroute workflow, and **optional Groq** LLM (OpenAI-compatible API). Reroutes are **suggestions only** until an operator confirms via the simulation API.

**Monorepo:** [../../README.md](../../README.md) · **Frontend:** [../frontend/README.md](../frontend/README.md)

## What lives here

| Area | Location |
|------|----------|
| HTTP API & WebSocket | `app/main.py`, `app/api/` |
| Config & JWT | `app/core/` |
| ORM models & DB session | `app/database/` |
| Pydantic schemas | `app/schemas/` (incl. `agent_schemas.py`) |
| Simulation engine & thermal/weather/routing | `app/services/simulation_engine.py`, `thermal_model.py`, `routing_service.py`, `weather_service.py`, `warehouse_service.py` |
| Agentic reroute (tools, graph, memory, logs) | `app/services/agent_*.py`, `agent_memory_service.py` |
| Redis / lifecycle | `app/services/pubsub_service.py`, `lifecycle_service.py` |

See **[docs/AGENTIC_REROUTE.md](../../docs/AGENTIC_REROUTE.md)** for the planner → critic → supervisor loop, tool allowlists, and admin observability endpoint `GET /shipments/{id}/agent-decisions`.

**Architecture diagrams:** **[docs/FLOWCHARTS.md](../../docs/FLOWCHARTS.md)** (Mermaid) — same flows as PNGs via `cd docs && npm run diagrams:png` (see monorepo **README**).

## Dependencies

Declared in **`requirements.txt`**. Use a virtual environment:

```bash
cd apps/backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

From the **monorepo root** (shared `.venv`): `pip install -r requirements.txt` pulls in backend deps, including **`psycopg2-binary`** for **Alembic**.

## Configuration

1. Copy `.env.example` → `.env`.
2. Required: **`SECRET_KEY`** (≥16 chars), **`DATABASE_URL`** (e.g. `postgresql+asyncpg://...`), **`REDIS_URL`**.
3. **`GROQ_API_KEY`**: optional. Empty → deterministic reroute policy only; set for LLM planner/supervisor JSON path.

Never commit `.env`.

## Default admin (local, first startup)

If **`users`** is empty and `ENV=local` with `seed_admin_defaults_in_local` enabled (default), **`seed_admin_user()`** creates:

| Field    | Default (local)   |
|----------|-------------------|
| Username | `admin`           |
| Password | `admin123456`     |
| Email    | `admin@example.com` |

Override with **`SEED_ADMIN_USERNAME`**, **`SEED_ADMIN_EMAIL`**, **`SEED_ADMIN_PASSWORD`** in `.env` (see `app/core/config.py`), or register via `POST /auth/register`.

## Run (local)

Postgres and Redis running (e.g. `docker compose up -d postgres redis` from repo root).

```bash
cd apps/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **OpenAPI:** http://localhost:8000/docs  
- **Health:** http://localhost:8000/health  

## Alembic migrations

```bash
cd apps/backend
alembic upgrade head
```

`alembic/env.py` merges **`apps/backend/.env`** into the environment and picks a sync Postgres driver (`psycopg2` or `psycopg`). For `postgresql+asyncpg://`, the `+asyncpg` suffix is stripped for migrations.

## Tests

```bash
cd apps/backend
pytest tests/ -q
```

`pytest.ini` sets `asyncio_mode = auto`. `tests/conftest.py` uses SQLite + OSRM stubs; no Groq key required.

## Docker

`Dockerfile` in this directory. See repository root **README.md** and **docker-compose.yml** for full-stack runs.

## Troubleshooting

### `ix_shipments_status` / duplicate index

If an old DB left duplicates, reset the volume: `docker compose down -v`, then bring Postgres back up.

### Postgres connection refused

Start Postgres from repo root: `docker compose up -d postgres redis`, then match **`DATABASE_URL`** in `.env`.

### `No module named 'psycopg2'` when running Alembic

Install sync driver: `pip install psycopg2-binary` (included in `requirements.txt`) or `pip install 'psycopg[binary]'`.
