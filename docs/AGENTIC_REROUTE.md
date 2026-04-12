# Agentic reroute decision system

The backend suggests cold-chain reroutes **only** (human-in-the-loop). Nothing is auto-applied; operators still use `POST /simulation/confirm-reroute/{shipment_id}` to commit a suggestion.

## Modes

| `GROQ_API_KEY` | Behavior |
|----------------|----------|
| Empty / unset | **Deterministic** LangGraph pipeline (environment → staging → navigation → supervisor) runs. Output is wrapped in `AgentDecision` and persisted like the LLM path. |
| Set | **Planner → evaluate → critic → supervisor** graph runs: Groq emits JSON for planner and supervisor; routes and warehouse IDs are constrained to **tool outputs** only. |

## Safety constraints

1. **Warehouse allowlist** — Planner and final `warehouse_id` must be one of the IDs returned by `tool_list_warehouses` (database-backed cold-storage candidates near the truck).
2. **Routing** — ETAs and distances for candidates come from `tool_route_legs` (OSRM with haversine fallback), packaged once as `raw_packages` so the LLM cannot invent legs.
3. **Rejected hubs** — `POST /simulation/reject-reroute/{shipment_id}` appends `warehouse_id` to per-shipment memory. The **LLM planner** is instructed not to repeat those IDs; the rule-based **critic** drops any candidate that references a rejected id.
4. **No auto-apply** — `AgentDecision` is advisory; simulation state changes only after explicit confirm.

## Tools (`app/services/agent_tools.py`)

| Tool | Role |
|------|------|
| `tool_list_warehouses` | Ranked cold-storage rows near `(lat, lng)`. |
| `tool_route_legs` | Parallel truck→warehouse / truck→final legs via `routing_service`. |
| `tool_estimate_thermal_risk` | Threshold, stress label, minutes-to-risk estimate. |
| `tool_get_weather` | OpenWeather when configured; else static fallback; **blizzard scenario** rows when `blizzard_scenario_id` is set. |
| Memory (`agent_memory_service`) | `tool_get_memory` / merge writes for last suggestion and rejections. |

## Observability

Each `suggest_reroute` run inserts **`agent_decision_logs`** (`decision_json`, optional `planner_json`, `critic_json`, `tool_traces_json`, `supervisor_json`, `operator_feedback`). Admins can list history:

`GET /shipments/{shipment_id}/agent-decisions`

Confirm / reject update `operator_feedback` on the latest pending row (`confirmed` / `rejected`).

## Schema

Pydantic models live in `app/schemas/agent_schemas.py` (`AgentDecision`, `PlannerOutput`, `EvaluatedCandidate`, tool result types).

## Database migrations

- Local/dev: `init_db()` / `reset_db()` create all tables (see `app/database/session.py`).
- Production: prefer Alembic — run `alembic upgrade head` from `apps/backend` (Alembic loads `apps/backend/.env` for `DATABASE_URL`). `postgresql+asyncpg://` is rewritten for migrations; you still need a **sync** DBAPI: `pip install psycopg2-binary` (in `apps/backend/requirements.txt`) or `pip install 'psycopg[binary]'` — the env script uses whichever is installed. From the repo root venv: `pip install -r requirements.txt`. Revision `20260412_0001` adds `agent_shipment_memory` and `agent_decision_logs` if you are upgrading an older database that already has core tables.

## Tests

From `apps/backend` (SQLite in-memory, stubbed OSRM, no Groq):

```bash
pytest tests/ -q
```

Scenarios use seeded `BlizzardScenario`-style rows (`test_*` slugs) plus cold-storage `WarehouseCandidate` rows.
