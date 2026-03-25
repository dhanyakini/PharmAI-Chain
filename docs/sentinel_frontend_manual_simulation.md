
# Project Sentinel Frontend Spec (Interactive Simulation Control Version)

## Objective

Frontend must behave like a live logistics control cockpit.

User controls:

shipment creation
route selection
simulation start
reroute confirmation

Simulation must NOT auto-run.

---

# Application Flow

Login
→ Dashboard
→ Create Shipment
→ Select Route on Map
→ Save Shipment
→ Open Shipment Simulation Page
→ Start Simulation
→ Watch Truck Move
→ Receive Reroute Suggestion
→ Confirm Reroute
→ Continue Simulation

---

# Landing Page

Minimal UI

Title
Description
Get Started button

Click opens login modal

---

# Sidebar Layout

Dashboard
Shipments
Simulation
Audits
Logs

Bottom:

username
logout

---

# Dashboard Page

Shows:

shipment count
active simulation status
API health status
websocket status

NO dummy analytics

---

# Shipment Creation Page

User selects:

origin (map click)
destination (map click)
truck_name

Frontend calls:

POST /routes/generate

Displays route overlay

User clicks:

Save Shipment

---

# Shipment Simulation Page

Controls:

Start Simulation
Pause Simulation
Confirm Reroute

Map shows:

truck marker
route polyline
weather overlay
reroute overlay
destination marker

---

# Weather Visualization

When backend emits:

entered_blizzard_zone

Map displays storm overlay

---

# Agent Suggestion UI

When backend emits:

reroute_suggested

Show modal:

Suggested alternate route detected

Buttons:

Confirm
Reject

---

# Confirm Reroute Behavior

POST /simulation/confirm-reroute/{shipment_id}

Map redraws route dynamically

---

# Telemetry Panel

Displays:

internal_temp
external_temp
speed
weather_state
risk_level

Live updating

---

# Lifecycle Timeline Panel

Displays ordered events:

simulation_started
entered_blizzard_zone
risk_detected
reroute_suggested
reroute_confirmed
reroute_applied
temperature_recovered
shipment_delivered

---

# WebSocket Integration

/ws/dashboard

Receives:

telemetry
agent_action
lifecycle_event

Updates UI instantly

---

# Required Frontend Pages

/
/dashboard
/shipments
/shipments/{shipment_id}
/audits
/logs
