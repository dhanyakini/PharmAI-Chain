"""
Project Sentinel — FastAPI Backend

Fixes applied:
  - Thread lock on sim_state (race condition fix)
  - Async /run via BackgroundTasks — no more hanging HTTP requests
  - SQLite context managers (no leaked connections)
  - road_status validation on /update
  - /simulate-blizzard uses INSULIN_TEMP constants
  - /tick endpoint for truck location simulation
  - DEFAULT_STATE risk_score = -1.0 (sentinel value)
  - staging_areas and ponr_hrs added to DEFAULT_STATE
  - Startup check for GROQ_API_KEY
"""

import os
import json
import time
import uuid
import threading
import sqlite3
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv

from agents import run_sentinel, ChainState, INSULIN_TEMP_MIN_C

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()

if not os.getenv("GROQ_API_KEY"):
    raise EnvironmentError(
        "GROQ_API_KEY is not set. Add it to your .env file before starting."
    )

IS_PRODUCTION = os.getenv("ENV", "development") == "production"

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Project Sentinel API")

origins = (
    ["https://your-production-domain.com"]   # lock down in prod
    if IS_PRODUCTION
    else ["http://localhost:5173"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Thread safety ─────────────────────────────────────────────────────────────
state_lock = threading.Lock()

# ── DB helpers ────────────────────────────────────────────────────────────────
DB_PATH = "sentinel.db"

@contextmanager
def get_db():
    """Yields a SQLite connection and guarantees it is closed afterward."""
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init_db():
    with get_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                state     TEXT,
                logs      TEXT
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_runs_id ON runs(id DESC)")

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
    "risk_score":         -1.0,    # -1.0 = not yet calculated
    "recommended_action": "",
    "alternate_routes":   [],
    "staging_areas":      [],
    "ponr_hrs":           -1.0,    # -1.0 = no imminent PONR
    "logs":               [],
}

sim_state: ChainState = DEFAULT_STATE.copy()

# In-memory job results store (swap for Redis in production)
job_results: dict = {}

# ── Pydantic models ───────────────────────────────────────────────────────────
VALID_ROAD_STATUSES = {"CLEAR", "BLOCKED"}

class StateUpdate(BaseModel):
    external_temp: float | None = None
    cargo_temp:    float | None = None
    road_status:   str   | None = None
    fuel:          float | None = None

    @field_validator("road_status")
    @classmethod
    def validate_road_status(cls, v):
        if v is not None and v not in VALID_ROAD_STATUSES:
            raise ValueError(f"road_status must be one of {VALID_ROAD_STATUSES}")
        return v

    @field_validator("fuel")
    @classmethod
    def validate_fuel(cls, v):
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError("fuel must be between 0 and 100")
        return v

# ── Background job runner ─────────────────────────────────────────────────────
def _run_job(job_id: str, initial_state: ChainState):
    """Runs the full agent pipeline in a background thread."""
    global sim_state
    try:
        result = run_sentinel(initial_state)

        with state_lock:
            sim_state = result

        with get_db() as con:
            con.execute(
                "INSERT INTO runs (timestamp, state, logs) VALUES (?, ?, ?)",
                (
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                    json.dumps({k: v for k, v in result.items() if k != "logs"}),
                    json.dumps(result["logs"]),
                ),
            )

        job_results[job_id] = {
            "status":     "complete",
            "logs":       result["logs"],
            "risk_score": result["risk_score"],
            "action":     result["recommended_action"],
            "ponr_hrs":   result["ponr_hrs"],
        }

    except Exception as e:
        job_results[job_id] = {"status": "error", "detail": str(e)}

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/state")
def get_state():
    """Frontend polls this to refresh the dashboard."""
    with state_lock:
        return sim_state.copy()

@app.post("/update")
def update_state(update: StateUpdate):
    """Manually tweak simulation conditions from the frontend."""
    global sim_state
    with state_lock:
        if update.external_temp is not None:
            sim_state["external_temp"] = update.external_temp
        if update.cargo_temp is not None:
            sim_state["cargo_temp"]    = update.cargo_temp
        if update.road_status is not None:
            sim_state["road_status"]   = update.road_status
        if update.fuel is not None:
            sim_state["fuel"]          = update.fuel
        snapshot = sim_state.copy()
    return {"status": "updated", "state": snapshot}

@app.post("/run")
def run_agents(background_tasks: BackgroundTasks):
    """
    Triggers the full agent pipeline asynchronously.
    Returns immediately with a job_id; poll /run/{job_id} for results.
    """
    job_id = str(uuid.uuid4())
    job_results[job_id] = {"status": "pending"}
    with state_lock:
        snapshot = sim_state.copy()
    background_tasks.add_task(_run_job, job_id, snapshot)
    return {"job_id": job_id, "status": "queued"}

@app.get("/run/{job_id}")
def get_job_result(job_id: str):
    """Poll this endpoint after calling POST /run."""
    result = job_results.get(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return result

@app.post("/simulate-blizzard")
def simulate_blizzard(background_tasks: BackgroundTasks):
    """Sets worst-case blizzard conditions and triggers the agent pipeline."""
    global sim_state
    with state_lock:
        sim_state["external_temp"] = -10.0
        sim_state["road_status"]   = "BLOCKED"
        sim_state["cargo_temp"]    = round(INSULIN_TEMP_MIN_C + 0.5, 2)  # 2.5°C — near freeze threshold
        snapshot = sim_state.copy()

    job_id = str(uuid.uuid4())
    job_results[job_id] = {"status": "pending"}
    background_tasks.add_task(_run_job, job_id, snapshot)
    return {"job_id": job_id, "status": "queued", "conditions_set": {
        "external_temp": -10.0,
        "road_status":   "BLOCKED",
        "cargo_temp":    round(INSULIN_TEMP_MIN_C + 0.5, 2),
    }}

@app.post("/tick")
def tick_simulation():
    """
    Advances truck location one step toward destination (linear interpolation).
    Call this on a timer from the frontend to animate truck movement on the map.
    """
    global sim_state
    STEP = 0.05   # degrees per tick (~5 km)

    with state_lock:
        loc  = sim_state["location"]
        dest = sim_state["destination"]

        # Move toward destination; stop when within STEP distance
        new_lat = loc[0] + min(STEP, abs(dest[0] - loc[0])) * (1 if dest[0] > loc[0] else -1)
        new_lon = loc[1] + min(STEP, abs(dest[1] - loc[1])) * (1 if dest[1] > loc[1] else -1)

        arrived = (abs(new_lat - dest[0]) < 0.01 and abs(new_lon - dest[1]) < 0.01)
        sim_state["location"] = [round(new_lat, 4), round(new_lon, 4)]
        sim_state["fuel"]     = round(max(0.0, sim_state["fuel"] - 0.5), 1)
        snapshot = sim_state.copy()

    return {"location": snapshot["location"], "fuel": snapshot["fuel"], "arrived": arrived}

@app.post("/reset")
def reset():
    """Resets simulation to default state."""
    global sim_state
    with state_lock:
        sim_state = DEFAULT_STATE.copy()
    return {"status": "reset"}

@app.get("/logs")
def get_logs():
    """Returns the last 20 agent run logs from the database."""
    with get_db() as con:
        rows = con.execute(
            "SELECT timestamp, logs FROM runs ORDER BY id DESC LIMIT 20"
        ).fetchall()
    return [{"timestamp": r[0], "logs": json.loads(r[1])} for r in rows]