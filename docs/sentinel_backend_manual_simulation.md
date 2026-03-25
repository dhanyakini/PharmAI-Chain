
# Project Sentinel Backend Spec (Manual-Control, Real-Time Simulation Version)

## Objective

Build a real-time interactive cold-chain logistics simulation backend where:

User creates shipment → selects route → starts simulation → telemetry streams live → weather disruption occurs → AI suggests reroute → user confirms reroute → simulation continues dynamically.

NO dummy automatic simulations.
Everything must be user-triggered and observable.

---

# Authentication Requirements

Admin login required.

Endpoints:

POST /auth/login
GET /auth/me

All simulation endpoints require authentication.

---

# Shipment Creation Flow

Endpoint:

POST /shipments

Input:

origin_lat
origin_lng
destination_lat
destination_lng
truck_name

Backend generates:

shipment_id (UUID)
status = CREATED

Return route suggestion using routing engine.

---

# Route Generation Endpoint

POST /routes/generate

Input:

origin
destination

Output:

polyline coordinates
distance
eta

Frontend displays route overlay.

User confirms default route:

POST /routes/save

---

# Simulation Controller

POST /simulation/start/{shipment_id}

Simulation must:

start from origin
move incrementally
publish telemetry every 3–5 seconds
update DB
broadcast websocket event

---

# Weather Engine

Define polygon:

CONNECTICUT_BLIZZARD_ZONE

When truck enters polygon:

weather_state = blizzard

Emit lifecycle event:

entered_blizzard_zone

---

# Agent Trigger Rule

If:

internal_temp <= 36°F

Run LangGraph workflow:

environment_agent
dispatcher_agent
supervisor_agent

Return reroute suggestion only.

DO NOT auto-apply.

---

# User Confirmation Required

Frontend calls:

POST /simulation/confirm-reroute/{shipment_id}

Backend replaces only remaining route segment.

Emit lifecycle event:

reroute_applied

---

# Lifecycle Events Channel

Redis channel:

simulation_lifecycle

Emit:

simulation_started
entered_blizzard_zone
risk_detected
reroute_suggested
reroute_confirmed
reroute_applied
temperature_recovered
shipment_delivered
shipment_compromised

---

# WebSocket Stream Contract

/ws/dashboard

Streams:

telemetry
agent_action
lifecycle_event

Format:

{
type,
shipment_id,
timestamp,
payload
}

---

# Required Simulation Endpoints

POST /simulation/start/{shipment_id}
POST /simulation/stop/{shipment_id}
POST /simulation/confirm-reroute/{shipment_id}
GET /simulation/state/{shipment_id}
GET /simulation/lifecycle/{shipment_id}

---

# Required Database Tables

users
shipments
routes
telemetry_logs
intervention_logs
lifecycle_events
