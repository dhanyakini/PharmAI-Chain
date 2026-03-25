Project Proposal - Multi-Agent Intelligence for Pharmaceutical Logistics
1. Project Overview
This an autonomous multi-agent system designed to manage disruptions in a pharmaceutical cold chain, with a
focus on insulin transportation. Insulin is temperature-sensitive and must be kept between 35°F and 77°F. The
goal of this project is to demonstrate how agentic AI can monitor real-time conditions, reason about risk, and
autonomously take corrective actions without direct human intervention.
2. Problem Statement
Traditional supply chain systems rely on static, rule-based logic and often fail during unexpected or compound
disruptions. In high-stakes medical logistics, such failures can result in significant financial loss and risks to
patient health. This project addresses the challenge of building a system that can adapt intelligently during
extreme events.
3. Simulated Operational Scenario
• Cargo: 5,000 units of insulin (approximate value: $1.5 million)
• Route: Manufacturing facility in New Jersey to a distribution center in Boston
• Disruption: Severe winter blizzard blocking major highways
• Risk: Insulin freezing if exposed to sub-zero temperatures for more than four hours
4. Technical Architecture & Methodology
A multi-agent architecture using LangGraph for iterative reasoning and cyclic planning workflows.
• Environment Agent: Monitors NOAA environmental feeds and predicts thermal exposure thresholds and
“Point of No Return.”
• Logic Agent: Integrates OpenStreetMap and Google APIs to calculate rerouting options, traffic latency, and
temperature-controlled staging areas.
• Supervisor Agent: Acts as the central orchestrator performing multi-objective optimization across safety,
cost, and delivery time.
The Inference Engine will be Llama 3 via Groq API, selected for high tokens-per-second throughput enabling
near real-time reasoning within simulated logistics environments.
The System Implementation includes FastAPI backend for agent orchestration and API services and React
frontend dashboard for visualization and human-in-the-loop oversight.
5. Data Source
• Geospatial Data: OpenStreetMap for road topology; Google Distance Matrix API for real-time travel
estimates
• Environmental Data: NOAA historical winter storm datasets for realistic weather simulations
• Cold-Chain Constraints: Pharmaceutical stability guidelines specifying acceptable temperature ranges
• Infrastructure Data: Scraped datasets on cold-chain warehouses, storage capacities, and staging locations
6. Expected Outcomes
By the end of the project, The Sentinel will be able to autonomously detect a cold-chain disruption, evaluate
multiple response strategies, and execute the optimal solution in real time. The final deliverable will include a live
dashboard demonstrating agent reasoning, decision-making, and successful prevention of insulin spoilage under
simulated crisis conditions.