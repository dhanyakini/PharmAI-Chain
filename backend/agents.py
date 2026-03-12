"""
Project Sentinel — Agent Definitions
LangGraph supervisor + 3 worker agents powered by Llama 3 via Groq

Fixes applied:
  - Consistent insulin temperature constants (INSULIN_TEMP_MIN/MAX_C)
  - Supervisor decision written back to recommended_action in state
  - analyst_agent picks lowest-ETA route for risk scoring
  - predict_spoilage_risk: freezing penalty gated on ETA, corrected thresholds
  - llm_call: retry logic with exponential backoff
  - Point-of-No-Return (PONR) calculation in sentinel_agent
  - find_staging_warehouses tool stub added
  - DEFAULT_STATE risk_score sentinel value (-1.0)
"""

import os
import json
import time
import requests
from groq import Groq
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise EnvironmentError(
        "GROQ_API_KEY is not set. Add it to your .env file before starting."
    )

client = Groq(api_key=GROQ_API_KEY)
MODEL  = "llama-3.3-70b-versatile"

# ── Insulin temperature constants (single source of truth) ────────────────────
INSULIN_TEMP_MIN_C  = 2.0    # below this → freezing risk
INSULIN_TEMP_MAX_C  = 8.0    # above this → degradation risk (conservative; full range ~25 °C)
SPOILAGE_WINDOW_HRS = 4.0    # max safe time outside range before spoilage

# ── Shared State Schema ───────────────────────────────────────────────────────
class ChainState(TypedDict):
    truck_id:           str
    location:           list[float]      # [lat, lon]
    destination:        list[float]
    cargo_temp:         float            # °C
    external_temp:      float            # °C
    road_status:        str              # "CLEAR" | "BLOCKED"
    fuel:               float            # percentage
    alert_triggered:    bool
    risk_score:         float            # 0.0–1.0  (-1.0 = not yet calculated)
    recommended_action: str
    alternate_routes:   list[dict]
    staging_areas:      list[dict]       # nearby cold-chain warehouses
    ponr_hrs:           float            # hours until Point of No Return (-1 = safe)
    logs:               Annotated[list[str], operator.add]

# ── Tool: NOAA Weather ────────────────────────────────────────────────────────
def get_weather(lat: float, lon: float) -> dict:
    """Fetches current weather from NOAA. Falls back to simulated blizzard data."""
    try:
        point_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
        r = requests.get(point_url, timeout=5)
        r.raise_for_status()
        grid = r.json()["properties"]
        forecast = requests.get(grid["forecast"], timeout=5).json()
        period   = forecast["properties"]["periods"][0]
        return {
            "temperature_f":  period["temperature"],
            "wind_speed":     period["windSpeed"],
            "short_forecast": period["shortForecast"],
        }
    except Exception:
        return {
            "temperature_f":  5,
            "wind_speed":     "45 mph",
            "short_forecast": "Blizzard conditions",
        }

# ── Tool: Point-of-No-Return Calculator ───────────────────────────────────────
def calculate_ponr(cargo_temp: float, external_temp: float, road_status: str) -> float:
    """
    Estimates hours remaining before insulin is irreversibly damaged.

    Uses a simplified thermal drift model:
      - Base drift rate: cargo moves ~1 °C per hour toward external temp
      - Road blockage doubles the effective drift (no rerouting buffer)
    Returns hours until PONR, or -1.0 if cargo is currently within safe range
    and won't breach within the spoilage window.
    """
    drift_rate = 1.0  # °C per hour
    if road_status == "BLOCKED":
        drift_rate = 2.0

    # Already outside safe range?
    if cargo_temp < INSULIN_TEMP_MIN_C:
        # Hours until cargo drops to a hard freeze threshold (0 °C)
        gap = cargo_temp - 0.0
        return round(gap / drift_rate, 2) if drift_rate > 0 else SPOILAGE_WINDOW_HRS

    if cargo_temp > INSULIN_TEMP_MAX_C:
        # Hours until cargo hits heat-denaturation threshold (25 °C)
        gap = 25.0 - cargo_temp
        return round(gap / drift_rate, 2) if drift_rate > 0 else SPOILAGE_WINDOW_HRS

    # Within safe range — compute hours to nearest boundary
    if external_temp < INSULIN_TEMP_MIN_C:
        gap = cargo_temp - INSULIN_TEMP_MIN_C
        hrs = round(gap / drift_rate, 2)
        return hrs if hrs < SPOILAGE_WINDOW_HRS else -1.0

    if external_temp > INSULIN_TEMP_MAX_C:
        gap = INSULIN_TEMP_MAX_C - cargo_temp
        hrs = round(gap / drift_rate, 2)
        return hrs if hrs < SPOILAGE_WINDOW_HRS else -1.0

    return -1.0   # external temp is also safe — no PONR within window

# ── Tool: Route Calculator (stub — swap in Google Distance Matrix API) ────────
def calculate_alternate_routes(origin: list, destination: list) -> list[dict]:
    """
    Returns mock alternate routes sorted by ascending risk level.

    To use Google Distance Matrix API, replace the body with:

        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": f"{origin[0]},{origin[1]}",
            "destinations": f"{destination[0]},{destination[1]}",
            "key": os.getenv("GOOGLE_API_KEY"),
            "alternatives": "true",
        }
        r = requests.get(url, params=params, timeout=10)
        # parse r.json() into the dict format below
    """
    return [
        {"name": "Route A — I-95 via Hartford", "distance_mi": 245, "eta_hrs": 4.5, "risk": "HIGH"},
        {"name": "Route B — I-84 via Albany",   "distance_mi": 290, "eta_hrs": 5.2, "risk": "MEDIUM"},
        {"name": "Route C — Air Freight BOS",   "distance_mi": 0,   "eta_hrs": 1.5, "risk": "LOW"},
    ]

# ── Tool: Staging Area Finder (stub) ─────────────────────────────────────────
def find_staging_warehouses(lat: float, lon: float) -> list[dict]:
    """
    Returns nearby cold-chain-capable warehouses for emergency staging.

    Replace with a real API call (e.g. Google Places, internal warehouse DB)
    or a scraped dataset of certified cold-chain facilities.
    """
    return [
        {
            "name":        "Hartford Cold Logistics Hub",
            "lat":          41.7658,
            "lon":         -72.6851,
            "distance_mi":  85,
            "temp_range":  "2–8°C",
            "capacity_units": 10_000,
        },
        {
            "name":        "Springfield PharmaCold Depot",
            "lat":          42.1015,
            "lon":         -72.5898,
            "distance_mi": 120,
            "temp_range":  "2–8°C",
            "capacity_units": 5_000,
        },
    ]

# ── Tool: Spoilage Risk Scorer ────────────────────────────────────────────────
def predict_spoilage_risk(
    cargo_temp:    float,
    external_temp: float,
    eta_hrs:       float,
    road_status:   str,
) -> float:
    """
    Linear risk model (0.0–1.0).
    Replace with a trained ANN per Rezki & Mansouri (2023) for production use.

    Scoring rationale:
      0.4 — cargo already outside insulin safe range (most critical factor)
      0.3 — freezing external temp AND prolonged exposure (> 2 hrs)
      0.2 — road is blocked (delays compounding thermal risk)
      0.1 — ETA > 4 hrs (approaching spoilage window limit)
    """
    score = 0.0

    if cargo_temp < INSULIN_TEMP_MIN_C or cargo_temp > INSULIN_TEMP_MAX_C:
        score += 0.4

    # Freezing external temp only penalised when exposure is prolonged
    if external_temp < INSULIN_TEMP_MIN_C and eta_hrs > 2.0:
        score += 0.3

    if road_status == "BLOCKED":
        score += 0.2

    if eta_hrs > SPOILAGE_WINDOW_HRS:
        score += 0.1

    return round(min(score, 1.0), 3)

# ── LLM Helper (with retry + exponential backoff) ────────────────────────────
def llm_call(system: str, user: str, retries: int = 3) -> str:
    last_err = ""
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                max_tokens=512,
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = str(e)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)   # 1s, 2s, 4s
    return f"[LLM UNAVAILABLE — {last_err}]"

# ── Agent 1: Sentinel (Monitor / Environment Agent) ──────────────────────────
def sentinel_agent(state: ChainState) -> ChainState:
    weather    = get_weather(state["location"][0], state["location"][1])
    ext_temp_c = round((weather["temperature_f"] - 32) * 5 / 9, 2)

    ponr = calculate_ponr(state["cargo_temp"], ext_temp_c, state["road_status"])

    alert = (
        state["road_status"] == "BLOCKED"
        or ext_temp_c < INSULIN_TEMP_MIN_C
        or state["cargo_temp"] < INSULIN_TEMP_MIN_C
        or state["cargo_temp"] > INSULIN_TEMP_MAX_C
        or (ponr != -1.0 and ponr < 2.0)   # PONR within 2 hrs is always an alert
    )

    ponr_str = f"{ponr:.1f} hrs" if ponr != -1.0 else "Safe (> 4 hrs)"

    reasoning = llm_call(
        system=(
            "You are the Sentinel monitoring agent for a pharmaceutical cold chain. "
            f"Insulin must stay between {INSULIN_TEMP_MIN_C}°C and {INSULIN_TEMP_MAX_C}°C. "
            "Report concisely: current conditions, alert status, PONR, and why."
        ),
        user=(
            f"Truck status: {json.dumps({k: v for k, v in state.items() if k != 'logs'})}\n"
            f"Weather: {json.dumps(weather)}\n"
            f"Point of No Return: {ponr_str}"
        ),
    )

    return {
        **state,
        "external_temp":   ext_temp_c,
        "alert_triggered": alert,
        "ponr_hrs":        ponr,
        "logs":            [f"[SENTINEL] {reasoning}"],
    }

# ── Agent 2: Logistics (Fixer / Routing Agent) ───────────────────────────────
def logistics_agent(state: ChainState) -> ChainState:
    routes   = calculate_alternate_routes(state["location"], state["destination"])
    staging  = find_staging_warehouses(state["location"][0], state["location"][1])

    ponr_str = (
        f"{state['ponr_hrs']:.1f} hrs remaining"
        if state["ponr_hrs"] != -1.0
        else "No imminent PONR"
    )

    reasoning = llm_call(
        system=(
            "You are the Logistics agent for a pharmaceutical cold-chain crisis. "
            "Rank these routes for an insulin shipment. "
            "Prioritise cargo safety over cost or distance. Be brief and decisive."
        ),
        user=(
            f"Routes available: {json.dumps(routes)}\n"
            f"Staging warehouses: {json.dumps(staging)}\n"
            f"Current risk score: {state['risk_score']}\n"
            f"External temp: {state['external_temp']}°C\n"
            f"Point of No Return: {ponr_str}"
        ),
    )

    return {
        **state,
        "alternate_routes": routes,
        "staging_areas":    staging,
        "logs":             [f"[LOGISTICS] {reasoning}"],
    }

# ── Agent 3: Analyst (Risk / Cost-Benefit Agent) ─────────────────────────────
def analyst_agent(state: ChainState) -> ChainState:
    routes = state["alternate_routes"]

    # Pick the route with the shortest ETA (safest from an exposure standpoint)
    best_route = (
        min(routes, key=lambda r: r.get("eta_hrs", 99))
        if routes else {}
    )

    risk = predict_spoilage_risk(
        state["cargo_temp"],
        state["external_temp"],
        best_route.get("eta_hrs", SPOILAGE_WINDOW_HRS + 1),
        state["road_status"],
    )

    ponr_str = (
        f"CRITICAL — {state['ponr_hrs']:.1f} hrs remaining"
        if state["ponr_hrs"] != -1.0
        else "No immediate PONR threat"
    )

    reasoning = llm_call(
        system=(
            "You are the Risk Analyst for a pharmaceutical cold-chain crisis. "
            "Given the spoilage risk score, routes, and staging options, "
            "recommend the single best action. Cargo value: $1.5M. Be decisive."
        ),
        user=(
            f"Risk score: {risk}\n"
            f"Best route (lowest ETA): {json.dumps(best_route)}\n"
            f"All routes: {json.dumps(routes)}\n"
            f"Staging warehouses: {json.dumps(state.get('staging_areas', []))}\n"
            f"Cargo temp: {state['cargo_temp']}°C  |  External: {state['external_temp']}°C\n"
            f"Point of No Return: {ponr_str}"
        ),
    )

    return {
        **state,
        "risk_score":         risk,
        "recommended_action": reasoning,
        "logs":               [f"[ANALYST] {reasoning}"],
    }

# ── Agent 4: Supervisor (Orchestrator) ───────────────────────────────────────
def supervisor_agent(state: ChainState) -> ChainState:
    decision = llm_call(
        system=(
            "You are the Supervisor of a pharmaceutical cold-chain crisis system. "
            "Review all agent findings and issue a final, concrete action order. "
            "Your response MUST begin with exactly one of these tokens: "
            "REROUTE_GROUND | SWITCH_AIR_FREIGHT | HOLD_AT_WAREHOUSE | CONTINUE. "
            "Follow it with one sentence of justification."
        ),
        user=(
            f"Analyst recommendation: {state['recommended_action']}\n"
            f"Risk score: {state['risk_score']}\n"
            f"Alert triggered: {state['alert_triggered']}\n"
            f"PONR: {state['ponr_hrs']} hrs\n"
            f"Agent logs:\n" + "\n".join(state["logs"][-4:])
        ),
    )

    return {
        **state,
        "recommended_action": decision,   # ← supervisor verdict overwrites analyst draft
        "logs":               [f"[SUPERVISOR] FINAL DECISION → {decision}"],
    }

# ── Routing Logic ─────────────────────────────────────────────────────────────
def should_activate_logistics(state: ChainState) -> str:
    """Skip logistics/analyst when conditions are fully normal."""
    return "logistics" if state["alert_triggered"] else "supervisor"

# ── Build the LangGraph ───────────────────────────────────────────────────────
def build_graph() -> StateGraph:
    g = StateGraph(ChainState)

    g.add_node("sentinel",   sentinel_agent)
    g.add_node("logistics",  logistics_agent)
    g.add_node("analyst",    analyst_agent)
    g.add_node("supervisor", supervisor_agent)

    g.set_entry_point("sentinel")

    g.add_conditional_edges(
        "sentinel",
        should_activate_logistics,
        {"logistics": "logistics", "supervisor": "supervisor"},
    )
    g.add_edge("logistics", "analyst")
    g.add_edge("analyst",   "supervisor")
    g.add_edge("supervisor", END)

    return g.compile()

# ── Public run helper ─────────────────────────────────────────────────────────
def run_sentinel(state: ChainState) -> ChainState:
    graph = build_graph()
    return graph.invoke(state)