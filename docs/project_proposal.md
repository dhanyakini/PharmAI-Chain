Project Proposal - Multi-Agent Intelligence for Pharmaceutical Logistics

1. Project Overview
Sentinel is a multi-agent cold-chain logistics simulator designed to manage disruptions in insulin transportation.
Insulin is temperature-sensitive and must remain within safe ranges during transit. The goal is to show how agentic
reasoning can detect risk early, evaluate reroute options, and provide operator-ready decisions in near real time.

2. Problem Statement
Traditional supply-chain workflows often rely on static rules and are brittle under compound disruptions (weather,
traffic, and timing pressure). In pharmaceutical logistics, delayed intervention can lead to spoilage and patient risk.
This project addresses the need for adaptive, explainable decision support in high-stakes transport conditions.

3. Simulated Operational Scenario
- Cargo: 5,000 units of insulin (approximate value: $1.5 million)
- Route: New Jersey manufacturing region to Boston distribution region
- Disruption: Severe blizzard conditions and route congestion
- Risk: Internal cargo temperature approaching cold-chain safety threshold

4. Implemented Architecture & Methodology
Sentinel uses a FastAPI backend, React dashboard frontend, PostgreSQL for state, Redis for runtime coordination,
and LangGraph for agent orchestration.

The reroute pipeline is implemented as a constrained multi-agent workflow:
- Environment analysis: estimates thermal exposure and urgency
- Candidate staging discovery: finds nearby cold-storage warehouse options
- Route evaluation: computes route legs and ETA/distance candidates
- Supervisor decision: ranks options by safety, delivery impact, and feasibility

Operational modes:
- Deterministic mode (default): runs a rule-based LangGraph pipeline with no LLM dependency
- LLM-assisted mode (optional): uses Groq (Llama-family model) for planner/supervisor reasoning when
  `GROQ_API_KEY` is provided

Safety and governance constraints:
- Warehouse decisions are constrained to tool-returned allowlisted IDs
- Route metrics come from backend tools (OSRM-based routing with fallback), not free-form generation
- Recommendations are advisory only; no automatic reroute is applied without operator confirmation

5. Data and Inputs
- Geospatial/routing: OSRM route leg evaluation (with deterministic fallback behavior)
- Environmental conditions: OpenWeather when configured, plus local fallback and seeded blizzard scenarios
- Operational data: shipment telemetry, cold-storage candidates, and scenario records stored in PostgreSQL
- Domain constraints: cold-chain thresholds and simulation parameters configured in backend settings

6. Current Outcomes
The current system can:
- Detect elevated cold-chain risk during simulation runs
- Generate explainable reroute recommendations with decision traces
- Persist agent decisions and operator feedback for observability
- Support human-in-the-loop confirmation/rejection of reroute actions via API and dashboard workflows

The final demonstration includes live telemetry, agent recommendations, and intervention tracking under realistic
simulated weather disruption scenarios.