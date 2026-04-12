# Project Sentinel (monorepo)

Pharmaceutical **cold-chain logistics simulator**: **FastAPI** backend (PostgreSQL, Redis, LangGraph, optional Groq), **React + Vite + Tailwind** frontend.

**Per-app guides:** [apps/backend/README.md](apps/backend/README.md) · [apps/frontend/README.md](apps/frontend/README.md)

**Docs:** [docs/FLOWCHARTS.md](docs/FLOWCHARTS.md) · [docs/API_CONTRACT.md](docs/API_CONTRACT.md) · [docs/AGENTIC_REROUTE.md](docs/AGENTIC_REROUTE.md) · [docs/sentinel_backend_manual_simulation.md](docs/sentinel_backend_manual_simulation.md)

## Secrets

- Put **`GROQ_API_KEY`** only in **`apps/backend/.env`** (never in the frontend). If a key is leaked, rotate it at [console.groq.com/keys](https://console.groq.com/keys).
- **`GROQ_API_KEY` may be left empty**: the reroute advisor falls back to a **deterministic** LangGraph policy (no LLM). See [docs/AGENTIC_REROUTE.md](docs/AGENTIC_REROUTE.md).

## Prerequisites

- Python 3.11+
- Node 20+ (22 LTS recommended) and npm
- Docker Desktop (optional, recommended for Postgres + Redis)

## Quick start (Docker)

1. **Infra only:** `docker compose up -d postgres redis` (no Groq key required for compose to start).

2. **Full stack:** copy root `cp .env.example .env` and set **`SECRET_KEY`** (and **`GROQ_API_KEY`** only if you want the LLM planner/supervisor path).

3. **Backend env (local uvicorn):** `cp apps/backend/.env.example apps/backend/.env` and set `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, and optionally `GROQ_API_KEY`.

4. From repo root:

```bash
docker compose up --build
```

- API: http://localhost:8000 — Swagger: http://localhost:8000/docs  
- UI: http://localhost:5173 (see `docker-compose.yml` for port mapping)

## Local development (without Docker for apps)

### Postgres & Redis

```bash
docker compose up -d postgres redis
```

### Backend

```bash
cd apps/backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: DATABASE_URL, REDIS_URL, SECRET_KEY; GROQ_API_KEY optional
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Virtualenv at repo root:** install everything (including **`psycopg2-binary`** for Alembic) with:

```bash
pip install -r requirements.txt
```

(`requirements.txt` at the monorepo root includes `apps/backend/requirements.txt`.)

### Database migrations (Alembic)

From **`apps/backend`** (with `.env` present or `DATABASE_URL` exported):

```bash
alembic upgrade head
```

Alembic loads `apps/backend/.env` automatically. Async URLs like `postgresql+asyncpg://` are adjusted for sync migrations; you need **`psycopg2-binary`** (listed in backend `requirements.txt`) or **`psycopg[binary]`**.

Local/dev can also rely on `init_db()` on startup; use Alembic when upgrading existing Postgres deployments.

### Frontend

```bash
cd apps/frontend
cp .env.example .env.local
npm install
npm run dev
```

See [apps/frontend/README.md](apps/frontend/README.md) for `VITE_*` vars, CORS, and the limited Vite proxy (`/auth`, `/routes`, `/health`, `/ws`).

### First user & demo data

1. On first backend start with an empty `users` table, **local** env seeds a default admin **`admin` / `admin123456`** (unless you set `SEED_ADMIN_*` in `apps/backend/.env`). Details: [apps/backend/README.md](apps/backend/README.md). You can also use `POST /auth/register`.
2. Warehouses, blizzard scenarios, and demo shipment **`SNT-DEMO-001`** seed when tables are empty.

## Tests (backend)

```bash
cd apps/backend
pytest tests/ -q
```

Tests use in-memory SQLite and stubbed routing (no live OSRM/Groq required).

## Project layout

| Path | Role |
|------|------|
| `apps/backend` | FastAPI app, Alembic, `pytest` |
| `apps/frontend` | Vite + React |
| `docs/` | API contract, agentic reroute, simulation notes |
| `docker-compose.yml` | Postgres, Redis, optional full stack |

## Environment & Git

- Never commit `.env` files; only `*.env.example` templates are tracked.
- **`GROQ_API_KEY`** is optional: omit or leave blank for deterministic-only reroute suggestions.
