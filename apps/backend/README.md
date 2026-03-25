# Sentinel — Backend

FastAPI service for **Project Sentinel**: cold-chain simulation, **PostgreSQL** persistence, **Redis** pub/sub, **LangGraph** agents, and **Groq** LLM inference (OpenAI-compatible API).

## What lives here

| Area | Location |
|------|----------|
| HTTP API & WebSocket | `app/main.py`, `app/api/` |
| Config & JWT | `app/core/` |
| ORM models & DB session | `app/database/` |
| Pydantic schemas | `app/schemas/` |
| Simulation (thermal, route, weather) | `app/simulation/` |
| Agents (LangGraph + prompts) | `app/agents/` |
| Groq client (single HTTP boundary) | `app/services/groq_client.py` |
| Redis + simulation worker | `app/services/` |

## Dependencies

All Python dependencies are declared in **`requirements.txt`**. Install them **only inside a virtual environment** (project `.venv` or your own):

```bash
cd apps/backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Do not install packages globally; keep the environment isolated per project.

## Configuration

1. Copy `apps/backend/.env.example` to `apps/backend/.env`.
2. Set **`GROQ_API_KEY`** (and optionally **`SECRET_KEY`**, database URLs). See [Groq quickstart](https://console.groq.com/docs/quickstart) for API keys.
3. `.env` is gitignored; never commit secrets.

**Groq usage:** The app calls Groq’s **OpenAI-compatible** endpoint `https://api.groq.com/openai/v1/chat/completions` with `Authorization: Bearer <GROQ_API_KEY>`, same as the official [`groq` Python SDK](https://console.groq.com/docs/quickstart) uses under the hood. We use **`httpx`** + JSON parsing in `app/services/groq_client.py` so agents stay async-friendly and structured outputs are validated with Pydantic.

## Demo login (first-time startup)

If the **`users`** table is empty, the API seeds an **admin** account:

| Field    | Value               |
|----------|---------------------|
| Username | `demo`              |
| Password | `SentinelDemo2026!` |
| Email    | `demo@sentinel.local` |

If you already created users, this seed is skipped—use your own credentials or reset the database.

## Run (local)

Requires **PostgreSQL** and **Redis** (e.g. Docker: `docker compose up -d postgres redis` from repo root).

```bash
# from apps/backend with venv activated
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **Swagger / OpenAPI:** http://localhost:8000/docs  
- **Health:** http://localhost:8000/health  

## Tests

```bash
pytest
```

Use `pytest.ini` and `tests/`; set env vars as in `tests/conftest.py` for SQLite-based unit tests.

## Docker

Image is built from this directory (`Dockerfile`). See the **repository root** `README.md` and `docker-compose.yml` for full-stack runs.

## Troubleshooting

### `ix_shipments_status` already exists / duplicate index

The ORM used to define the same index twice (`index=True` plus `Index(...)`). That is fixed in `models.py`. If a previous run left Postgres in a bad state, reset the DB volume: from repo root `docker compose down -v`, then `docker compose up -d postgres redis`, then start uvicorn again.

### `Connect call failed` / `Errno 10061` on port 5432

Nothing is listening on **PostgreSQL** (`localhost:5432`). Start Postgres (and Redis for full features) from the **repository root**:

```bash
docker compose up -d postgres redis
```

Wait until Postgres is healthy, then start uvicorn again. If you use a local Postgres install instead of Docker, create the `sentinel` database and ensure `DATABASE_URL` in `.env` matches your user, password, host, and port.
