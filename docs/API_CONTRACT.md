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
