# Project Sentinel (monorepo)

Pharmaceutical cold-chain logistics simulator: **FastAPI** backend (PostgreSQL, Redis, LangGraph, Groq), **React + Vite + Tailwind + shadcn-style UI** frontend.

**Per-app guides:** [apps/backend/README.md](apps/backend/README.md) · [apps/frontend/README.md](apps/frontend/README.md)

**Secrets:** Put **`GROQ_API_KEY`** only in **`apps/backend/.env`** (never in the frontend). Groq calls follow the [Groq quickstart](https://console.groq.com/docs/quickstart) (Bearer token + chat completions). If a key is ever pasted into chat or committed by mistake, **rotate it** at [console.groq.com/keys](https://console.groq.com/keys).

## Prerequisites

- Python 3.11+
- Node 22+ (npm) or pnpm
- Docker Desktop (optional, recommended for Postgres + Redis)

## Quick start (Docker)

1. **Infra only (Postgres + Redis):** you can run `docker compose up -d postgres redis` with no root `.env`. Compose no longer requires `GROQ_API_KEY` just to parse the file.

2. **Full stack (backend + frontend):** copy root `cp .env.example .env` and set **`GROQ_API_KEY`** (and ideally **`SECRET_KEY`**) so the backend container can call Groq.

3. Other env files:

   - Backend (local uvicorn without Docker): `cp apps/backend/.env.example apps/backend/.env` and fill values.

4. From repo root, full stack:

```bash
docker compose up --build
```

- API: http://localhost:8000 — Swagger: http://localhost:8000/docs  
- UI: http://localhost:5173 (nginx serves the built SPA on port **5173** mapped to container port 80)

The browser calls `http://localhost:8000` for REST/WebSocket (see `apps/frontend` build args in `docker-compose.yml`).

## Local development (without Docker for apps)

### Postgres & Redis

```bash
docker compose up -d postgres redis
```

### Backend

```bash
cd apps/backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: DATABASE_URL, REDIS_URL, GROQ_API_KEY, SECRET_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd apps/frontend
cp .env.example .env.local
npm install
npm run dev
```

Vite proxies `/auth`, `/shipments`, `/dashboard`, `/ws` to the backend (see `vite.config.ts`). With the proxy, you can leave `VITE_API_BASE_URL` empty in dev.

### First user & demo data

1. `POST /auth/register` (or use Swagger) to create a user (default role: viewer).
2. Promote to admin in DB if you need `POST /shipments`, or insert role via SQL.
3. On first backend start, **warehouses** and a **demo shipment** (`SNT-DEMO-001`) are seeded if tables are empty.

## Tests (backend)

```bash
cd apps/backend
pytest
```

## Project layout

- `apps/backend` — FastAPI app (`app/`), Docker image, `pytest`
- `apps/frontend` — Vite React app, Tailwind, Radix/shadcn-style components
- `docs/API_CONTRACT.md` — REST + WebSocket summary for frontend handoff

## Environment & Git

- Never commit `.env` files. Only `.env.example` templates are tracked.
- `GROQ_API_KEY` is required for full agent (Groq) behavior.
