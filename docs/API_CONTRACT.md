# Sentinel API contract (handoff)

Base URL: `http://localhost:8000` (or your deployed host). OpenAPI: `GET /docs` (Swagger UI).

## Authentication

- `POST /auth/register` — body `{ username, email, password }`
- `POST /auth/login` — body `{ username, password }` → `{ access_token, token_type }`
- `GET /auth/me` — header `Authorization: Bearer <token>`

Admin-only: `POST /shipments`, `PATCH /shipments/{id}`.

## Shipments & history

- `GET /shipments`
- `GET /shipments/{id}`
- `GET /shipments/{id}/telemetry`
- `GET /shipments/{id}/interventions`

## Dashboard

- `GET /dashboard/summary`
- `GET /dashboard/live-state`
- `GET /dashboard/events?shipment_id=&hours=`

## Simulation & weather

- `GET /simulation/blizzard-scenarios` — list DB-backed synthetic blizzard profiles (admin).
- `POST /simulation/start/{shipment_id}?blizzard_scenario_id=` — start worker; optional `blizzard_scenario_id` injects a scenario row instead of live API for that run.
- `POST /simulation/stop/{shipment_id}`
- `GET /simulation/state/{shipment_id}` — includes `blizzard_scenario_id` when set.

Live ambient temperature uses **OpenWeather** when `OPENWEATHER_API_KEY` is set; otherwise a local fallback. Telemetry `raw_payload` may include `weather_source` (`openweather`, `openweather_cache`, `blizzard_scenario`, `fallback`).

## WebSocket

- `WS /ws/dashboard` — unified envelope:

```json
{
  "type": "telemetry" | "agent_action" | "status" | "error" | "ping",
  "shipment_id": 1,
  "timestamp": "2026-03-24T12:34:56Z",
  "payload": {}
}
```

Telemetry `payload` includes `lat`, `lng`, `internal_temp`, `external_temp`, `weather_state`.  
Agent actions include `agent_role`, `action_taken`, `reasoning_trace`, `suggested_route`.

## Health

- `GET /health` — `{ status, redis, simulation }`
