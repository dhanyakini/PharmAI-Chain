"""
Project Sentinel — FastAPI Backend
Exposes the simulation state and agent triggers to the React frontend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents import run_sentinel, ChainState
import sqlite3, json, time

app = FastAPI(title="Project Sentinel API")

# Allow React dev server (localhost:5173) to call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB setup (stores agent run logs) ─────────────────────────────────────────
def init_db():
    con = sqlite3.connect("sentinel.db")
    con.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            state     TEXT,
            logs      TEXT
        )
    """)
    con.commit(); con.close()

init_db()

# ── Default simulation state ──────────────────────────────────────────────────
DEFAULT_STATE: ChainState = {
    "truck_id":           "T-101",
    "location":           [40.7128, -74.0060],   # New Jersey
    "destination":        [42.3601, -71.0589],   # Boston
    "cargo_temp":         4.5,
    "external_temp":      2.0,
    "road_status":        "CLEAR",
    "fuel":               80.0,
    "alert_triggered":    False,
    "risk_score":         0.0,
    "recommended_action": "",
    "alternate_routes":   [],
    "logs":               [],
}

sim_state: ChainState = DEFAULT_STATE.copy()

# ── Pydantic model for /update endpoint ──────────────────────────────────────
class StateUpdate(BaseModel):
    external_temp: float | None = None
    cargo_temp: float | None    = None
    road_status: str | None     = None
    fuel: float | None          = None

# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/state")
def get_state():
    """Frontend polls this every 2 seconds to refresh the dashboard."""
    return sim_state

@app.post("/update")
def update_state(update: StateUpdate):
    """Manually tweak the simulation (e.g., trigger blizzard from frontend)."""
    global sim_state
    if update.external_temp is not None:
        sim_state["external_temp"] = update.external_temp
    if update.cargo_temp is not None:
        sim_state["cargo_temp"] = update.cargo_temp
    if update.road_status is not None:
        sim_state["road_status"] = update.road_status
    if update.fuel is not None:
        sim_state["fuel"] = update.fuel
    return {"status": "updated", "state": sim_state}

@app.post("/run")
def run_agents():
    """Trigger the full agent pipeline and return the result + logs."""
    global sim_state
    result = run_sentinel(sim_state)
    sim_state = result

    # Persist to SQLite
    con = sqlite3.connect("sentinel.db")
    con.execute(
        "INSERT INTO runs (timestamp, state, logs) VALUES (?, ?, ?)",
        (
            time.strftime("%Y-%m-%dT%H:%M:%S"),
            json.dumps({k: v for k, v in result.items() if k != "logs"}),
            json.dumps(result["logs"]),
        ),
    )
    con.commit(); con.close()

    return {"logs": result["logs"], "risk_score": result["risk_score"],
            "action": result["recommended_action"]}

@app.post("/simulate-blizzard")
def simulate_blizzard():
    """The 'Big Red Button' — sets worst-case conditions and runs agents."""
    global sim_state
    sim_state["external_temp"] = -10.0
    sim_state["road_status"]   = "BLOCKED"
    sim_state["cargo_temp"]    = 2.5     # approaching freeze threshold
    return run_agents()

@app.post("/reset")
def reset():
    """Reset simulation to default state."""
    global sim_state
    sim_state = DEFAULT_STATE.copy()
    return {"status": "reset"}

@app.get("/logs")
def get_logs():
    """Return last 20 agent run logs from the DB."""
    con = sqlite3.connect("sentinel.db")
    rows = con.execute(
        "SELECT timestamp, logs FROM runs ORDER BY id DESC LIMIT 20"
    ).fetchall()
    con.close()
    return [{"timestamp": r[0], "logs": json.loads(r[1])} for r in rows]
