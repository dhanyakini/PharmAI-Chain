"""
Project Sentinel — Agent Definitions
LangGraph supervisor + 3 worker agents powered by Llama 3 via Groq
"""

import os
import json
import requests
from groq import Groq
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator
from dotenv import load_dotenv


# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
MODEL = "llama3-70b-8192"

# ── Shared State Schema ───────────────────────────────────────────────────────
class ChainState(TypedDict):
    truck_id: str
    location: list[float]         # [lat, lon]
    destination: list[float]
    cargo_temp: float             # Celsius
    external_temp: float
    road_status: str              # "CLEAR" | "BLOCKED"
    fuel: float
    alert_triggered: bool
    risk_score: float             # 0.0 – 1.0
    recommended_action: str
    alternate_routes: list[dict]
    logs: Annotated[list[str], operator.add]   # append-only log

# ── Tool: NOAA Weather ────────────────────────────────────────────────────────
def get_weather(lat: float, lon: float) -> dict:
    """
    Fetches current weather from NOAA for a lat/lon.
    Falls back to simulated data if the API is unreachable.
    """
    try:
        # Step 1: get grid point
        point_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
        r = requests.get(point_url, timeout=5)
        grid = r.json()["properties"]
        # Step 2: get forecast
        forecast_url = grid["forecast"]
        forecast = requests.get(forecast_url, timeout=5).json()
        period = forecast["properties"]["periods"][0]
        return {
            "temperature_f": period["temperature"],
            "wind_speed": period["windSpeed"],
            "short_forecast": period["shortForecast"],
        }
    except Exception:
        # Simulated blizzard fallback
        return {
            "temperature_f": 5,
            "wind_speed": "45 mph",
            "short_forecast": "Blizzard conditions",
        }

# ── Tool: Route Calculator (stub — swap in Google API key) ────────────────────
def calculate_alternate_routes(origin: list, destination: list) -> list[dict]:
    """
    Returns mock alternate routes. Replace with Google Distance Matrix API call:

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": f"{origin[0]},{origin[1]}",
        "destinations": f"{destination[0]},{destination[1]}",
        "key": GOOGLE_API_KEY,
        "alternatives": "true"
    }
    """
    return [
        {"name": "Route A — I-95 via Hartford",  "distance_mi": 245, "eta_hrs": 4.5, "risk": "HIGH"},
        {"name": "Route B — I-84 via Albany",    "distance_mi": 290, "eta_hrs": 5.2, "risk": "MEDIUM"},
        {"name": "Route C — Air Freight BOS",    "distance_mi": 0,   "eta_hrs": 1.5, "risk": "LOW"},
    ]

# ── Tool: Spoilage Risk Scorer ────────────────────────────────────────────────
def predict_spoilage_risk(cargo_temp: float, external_temp: float,
                           eta_hrs: float, road_status: str) -> float:
    """
    Simple linear risk model. Replace with trained ANN per Rezki & Mansouri (2023).
    Returns a 0.0–1.0 risk score.
    """
    score = 0.0
    if external_temp < 2:
        score += 0.4                         # freezing danger
    if cargo_temp < 4 or cargo_temp > 24:
        score += 0.3                         # out of safe range
    if road_status == "BLOCKED":
        score += 0.2
    if eta_hrs > 4:
        score += 0.1                         # approaching 4-hr spoilage window
    return min(score, 1.0)

# ── LLM Helper ───────────────────────────────────────────────────────────────
def llm_call(system: str, user: str) -> str:
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

# ── Agent 1: Sentinel (Monitor / Environment Agent) ──────────────────────────
def sentinel_agent(state: ChainState) -> ChainState:
    weather = get_weather(state["location"][0], state["location"][1])
    ext_temp_c = (weather["temperature_f"] - 32) * 5 / 9

    alert = (
        state["road_status"] == "BLOCKED"
        or ext_temp_c < 2
        or state["cargo_temp"] < 2
        or state["cargo_temp"] > 25
    )

    reasoning = llm_call(
        system="You are the Sentinel monitoring agent for a pharmaceutical cold chain. "
               "Report concisely: current conditions, alert status, and why.",
        user=f"Truck status: {json.dumps(state)}\nWeather: {json.dumps(weather)}"
    )

    return {
        **state,
        "external_temp": ext_temp_c,
        "alert_triggered": alert,
        "logs": [f"[SENTINEL] {reasoning}"],
    }

# ── Agent 2: Logistics (Fixer / Routing Agent) ───────────────────────────────
def logistics_agent(state: ChainState) -> ChainState:
    routes = calculate_alternate_routes(state["location"], state["destination"])

    reasoning = llm_call(
        system="You are the Logistics agent. Rank these routes for a cold-chain insulin shipment. "
               "Prioritise cargo safety over cost. Be brief.",
        user=f"Routes available: {json.dumps(routes)}\n"
             f"Current risk score: {state['risk_score']}\n"
             f"External temp (C): {state['external_temp']}"
    )

    return {
        **state,
        "alternate_routes": routes,
        "logs": [f"[LOGISTICS] {reasoning}"],
    }

# ── Agent 3: Analyst (Risk / Cost-Benefit Agent) ─────────────────────────────
def analyst_agent(state: ChainState) -> ChainState:
    best_route = state["alternate_routes"][0] if state["alternate_routes"] else {}
    risk = predict_spoilage_risk(
        state["cargo_temp"],
        state["external_temp"],
        best_route.get("eta_hrs", 6),
        state["road_status"],
    )

    reasoning = llm_call(
        system="You are the Risk Analyst. Given spoilage risk score and routes, "
               "recommend the single best action. Cargo value: $1.5M. Be decisive.",
        user=f"Risk score: {risk}\nRoutes: {json.dumps(state['alternate_routes'])}\n"
             f"Cargo temp: {state['cargo_temp']}°C  External: {state['external_temp']}°C"
    )

    return {
        **state,
        "risk_score": risk,
        "recommended_action": reasoning,
        "logs": [f"[ANALYST] {reasoning}"],
    }

# ── Agent 4: Supervisor (Orchestrator) ───────────────────────────────────────
def supervisor_agent(state: ChainState) -> ChainState:
    decision = llm_call(
        system="You are the Supervisor of a pharmaceutical cold-chain crisis system. "
               "Review all agent findings and issue a final, concrete action order. "
               "Options: REROUTE_GROUND, SWITCH_AIR_FREIGHT, HOLD_AT_WAREHOUSE, CONTINUE. "
               "State your choice and one sentence of justification.",
        user=f"Analyst recommendation: {state['recommended_action']}\n"
             f"Risk score: {state['risk_score']}\n"
             f"Alert triggered: {state['alert_triggered']}\n"
             f"Agent logs:\n" + "\n".join(state["logs"][-3:])
    )

    return {
        **state,
        "logs": [f"[SUPERVISOR] FINAL DECISION → {decision}"],
    }

# ── Routing Logic ─────────────────────────────────────────────────────────────
def should_activate_logistics(state: ChainState) -> str:
    """Only run logistics + analyst if an alert was triggered."""
    return "logistics" if state["alert_triggered"] else "supervisor"

# ── Build the LangGraph ───────────────────────────────────────────────────────
def build_graph() -> StateGraph:
    g = StateGraph(ChainState)

    g.add_node("sentinel",   sentinel_agent)
    g.add_node("logistics",  logistics_agent)
    g.add_node("analyst",    analyst_agent)
    g.add_node("supervisor", supervisor_agent)

    g.set_entry_point("sentinel")

    # Conditional edge: skip logistics/analyst when all is normal
    g.add_conditional_edges(
        "sentinel",
        should_activate_logistics,
        {"logistics": "logistics", "supervisor": "supervisor"},
    )
    g.add_edge("logistics", "analyst")
    g.add_edge("analyst",   "supervisor")
    g.add_edge("supervisor", END)

    return g.compile()

# ── Run helper ────────────────────────────────────────────────────────────────
def run_sentinel(state: ChainState) -> ChainState:
    graph = build_graph()
    return graph.invoke(state)
