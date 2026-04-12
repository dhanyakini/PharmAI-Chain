# Sentinel — architecture & behavior flowcharts

These diagrams use [Mermaid](https://mermaid.js.org/). They render on GitHub, in many IDEs, and in VS Code with a Mermaid preview extension.

---

## 1. System context (who talks to whom)

High-level data flow between major components.

```mermaid
flowchart LR
  subgraph clients["Clients"]
    UI["React SPA\n(Vite)"]
  end

  subgraph backend["Backend"]
    API["FastAPI\nREST + JWT"]
    WS["WebSocket\n/dashboard"]
    Worker["Simulation\nasync worker"]
  end

  subgraph data["Data & messaging"]
    PG[("PostgreSQL")]
    RD[("Redis\npub/sub")]
  end

  subgraph external["External services"]
    OSRM["OSRM routing\n(demo server)"]
    OW["OpenWeather\n(optional)"]
    GROQ["Groq API\n(optional LLM)"]
  end

  UI -->|HTTPS JSON| API
  UI <-->|WS events| WS
  API --> PG
  API --> RD
  Worker --> PG
  Worker --> RD
  WS --> RD
  API --> OSRM
  API --> OW
  API --> GROQ
```

---

## 2. Authentication flow

From sign-in through protected API usage.

```mermaid
sequenceDiagram
  participant U as User / Browser
  participant SPA as React app
  participant API as FastAPI /auth
  participant DB as PostgreSQL

  U->>SPA: Submit username + password
  SPA->>API: POST /auth/login
  API->>DB: Load user by username
  alt valid credentials & active user
    API-->>SPA: access_token (JWT)
    SPA->>SPA: Store token (localStorage)
    SPA->>API: GET /auth/me (Authorization: Bearer …)
    API-->>SPA: user profile (role, email)
    SPA->>U: Redirect to app (e.g. dashboard)
  else invalid
    API-->>SPA: 401 Invalid credentials
    SPA->>U: Show error (generic message)
  end

  Note over SPA,API: Later requests send Bearer token; 401/403 clears token
```

```mermaid
flowchart TD
  A[User opens protected route] --> B{Token in storage?}
  B -->|No| C[Redirect to /login]
  B -->|Yes| D[GET /auth/me]
  D --> E{200 OK?}
  E -->|Yes| F[Render page]
  E -->|401/403| G[Clear token → /login]
  E -->|Network error| H[Optional: keep token, show offline]
```

---

## 3. Simulation lifecycle (start → run → stop)

Logical flow from operator action to background processing and live UI updates.

```mermaid
flowchart TD
  subgraph operator["Operator"]
    O1[Select optional BlizzardScenario]
    O2[POST /simulation/start/:id]
    O3[POST /simulation/stop/:id]
  end

  subgraph api["API"]
    S[start_simulation endpoint]
    W[start_simulation_worker async task]
  end

  subgraph worker["Simulation worker loop"]
    L[Load shipment + route state]
    T[Advance truck / thermal / weather tick]
    P[Publish telemetry + lifecycle to Redis]
    R{Reroute needed?}
    RS[suggest_reroute agent pipeline]
    H[Pause for operator if suggested]
  end

  subgraph realtime["Real-time UI"]
    WS[WebSocket subscribers]
    FE[Simulation page + map + activity log]
  end

  O1 --> O2
  O2 --> S
  S --> W
  W --> L
  L --> T
  T --> P
  P --> WS
  WS --> FE
  T --> R
  R -->|yes| RS
  RS --> P
  R -->|pause| H
  O3 -->|cancels| W
```

**Telemetry vs lifecycle:** the worker publishes **telemetry** (position, temps, weather) on a schedule and **lifecycle** events (agents called, reroute suggested, blizzard entered, etc.). The dashboard WebSocket fans those out to connected clients.

---

## 4. Reroute decision (agent pipeline)

Two modes: **no Groq key** (deterministic graph) vs **Groq key set** (LLM planner + critic + supervisor). Both respect **human-in-the-loop** (no auto-apply).

```mermaid
flowchart TD
  START([suggest_reroute called]) --> PERC[Perception: tools — warehouses, route legs, thermal, weather, memory]
  PERC --> KEY{GROQ_API_KEY set?}

  KEY -->|No| DET[Deterministic LangGraph:<br/>environment → staging → navigation → supervisor utility]
  DET --> OUT1([Legacy suggestion + AgentDecision])

  KEY -->|Yes| PLAN[Planner LLM: JSON candidates<br/>allowed warehouse IDs only]
  PLAN --> EVAL[Evaluate: attach OSRM/fallback ETAs per candidate]
  EVAL --> CRIT[Critic: rules — allowlist, rejected IDs, valid legs]
  CRIT --> SUP[Supervisor LLM: pick one passing candidate]
  SUP --> OUT2([Legacy suggestion + AgentDecision])

  OUT1 --> PERSIST[Persist agent_decision_logs + shipment memory]
  OUT2 --> PERSIST
  PERSIST --> UI[API / WS: reroute_suggested event]
  UI --> OP{Operator}
  OP -->|POST confirm-reroute| APPLY[Apply new route segment]
  OP -->|POST reject-reroute| MEM[Record rejection in memory]
```

---

## 5. Human-in-the-loop reroute (UI + API)

```mermaid
sequenceDiagram
  participant Op as Operator
  participant UI as Simulation UI
  participant API as FastAPI /simulation
  participant DB as PostgreSQL

  Note over UI: Worker pauses or flags pending_reroute
  UI->>Op: Modal: warehouse + reasoning + miles/ETA
  alt Confirm
    Op->>UI: Confirm
    UI->>API: POST /simulation/confirm-reroute/:id
    API->>DB: Commit route + status
    API-->>UI: OK
    UI->>UI: Resume / refresh map
  else Reject
    Op->>UI: Reject
    UI->>API: POST /simulation/reject-reroute/:id
    API->>DB: Append rejected warehouse to agent memory
    API-->>UI: OK
  end
```

---

## 6. Shipment & routing data (simplified)

How a shipment moves from creation to simulation-ready state.

```mermaid
flowchart LR
  A[POST /shipments\norigin, destination, truck] --> B[(shipments row)]
  B --> C[OSRM: default route polyline]
  C --> D[Optional: warehouse markers\nfor map]
  D --> E[Simulation uses\nremaining polyline + ticks]
```

---

## Related docs

- [AGENTIC_REROUTE.md](./AGENTIC_REROUTE.md) — agent tools, constraints, observability
- [API_CONTRACT.md](./API_CONTRACT.md) — REST + WebSocket summary
- [sentinel_backend_manual_simulation.md](./sentinel_backend_manual_simulation.md) — hands-on simulation steps

To **export as PNG/SVG**, paste the Mermaid blocks into [mermaid.live](https://mermaid.live) or use the Mermaid CLI (`mmdc`).
