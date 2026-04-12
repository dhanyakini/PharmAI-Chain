# Sentinel — architecture & behavior flowcharts

These diagrams use [Mermaid](https://mermaid.js.org/). They render on GitHub, in many IDEs, and in VS Code with a Mermaid preview extension.

**Palette (consistent across all charts):** light backgrounds (**white** `#ffffff`, **cluster** `#e8eef4`, **subtle** `#f1f5f9`) with **dark slate text** `#0f172a` for maximum contrast. **Teal** `#0d9488` is used for accents and borders only—not for large text areas. Edge and message lines use **#334155**. PNG export uses the same tokens in [`mermaid-config.json`](./mermaid-config.json).

**Export to PNG:** see [Exporting diagrams to PNG](#exporting-diagrams-to-png) at the bottom.

---

## 1. System context (who talks to whom)

High-level data flow between major components.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif, system-ui, sans-serif','fontSize':'15px','primaryColor':'#ffffff','primaryTextColor':'#0f172a','primaryBorderColor':'#0d9488','secondaryColor':'#ffffff','secondaryTextColor':'#0f172a','secondaryBorderColor':'#64748b','tertiaryColor':'#f1f5f9','tertiaryTextColor':'#0f172a','tertiaryBorderColor':'#475569','lineColor':'#334155','textColor':'#0f172a','mainBkg':'#ffffff','nodeBorder':'#475569','clusterBkg':'#e8eef4','clusterBorder':'#64748b','edgeLabelBackground':'#ffffff','titleColor':'#0f172a'},'flowchart':{'curve':'basis','padding':20,'nodeSpacing':56,'rankSpacing':64,'useMaxWidth':true}}}%%
flowchart LR
  subgraph clients[" 🖥 Client tier "]
    UI["React SPA · Vite<br/>Dashboard & simulation UI"]
  end

  subgraph backend[" ⚙ Backend tier "]
    API["FastAPI · REST + JWT"]
    WS["WebSocket · /ws/dashboard"]
    Worker["Async simulation worker"]
  end

  subgraph data[" 💾 Data & messaging "]
    PG[("PostgreSQL · ORM state")]
    RD[("Redis · pub/sub fan-out")]
  end

  subgraph external[" 🌐 External services "]
    OSRM["OSRM · road routing"]
    OW["OpenWeather · optional"]
    GROQ["Groq · optional LLM"]
  end

  UI -->|"HTTPS JSON"| API
  UI <-->|"WS events"| WS
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
%%{init: {'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif, system-ui, sans-serif','fontSize':'15px','actorBkg':'#e8eef4','actorBorder':'#0d9488','actorTextColor':'#0f172a','actorLineColor':'#0d9488','signalColor':'#334155','signalTextColor':'#0f172a','labelBoxBkgColor':'#e8eef4','labelBoxBorderColor':'#0d9488','labelTextColor':'#0f172a','loopTextColor':'#0f172a','noteBkgColor':'#fef3c7','noteTextColor':'#78350f','noteBorderColor':'#ca8a04','textColor':'#0f172a','lineColor':'#334155'},'sequence':{'actorFontSize':15,'messageFontSize':14,'boxMargin':10}}}%%
sequenceDiagram
  autonumber
  participant U as User / Browser
  participant SPA as React app
  participant API as FastAPI /auth
  participant DB as PostgreSQL

  U->>SPA: Submit username + password
  SPA->>API: POST /auth/login
  API->>DB: Load user by username
  alt Valid credentials & active user
    API-->>SPA: access_token JWT
    SPA->>SPA: Persist token localStorage
    SPA->>API: GET /auth/me Bearer …
    API-->>SPA: Profile role email
    SPA->>U: Redirect e.g. dashboard
  else Invalid
    API-->>SPA: 401 Invalid credentials
    SPA->>U: Generic error no user hint
  end

  Note over SPA,API: Later Bearer on requests · 401 403 clears token
```

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif, system-ui, sans-serif','fontSize':'15px','primaryColor':'#ffffff','primaryTextColor':'#0f172a','primaryBorderColor':'#0d9488','secondaryColor':'#ffffff','secondaryTextColor':'#0f172a','secondaryBorderColor':'#64748b','tertiaryColor':'#f1f5f9','tertiaryTextColor':'#0f172a','lineColor':'#334155','textColor':'#0f172a','clusterBkg':'#e8eef4','clusterBorder':'#64748b','edgeLabelBackground':'#ffffff','titleColor':'#0f172a'},'flowchart':{'curve':'basis','padding':16,'useMaxWidth':true}}}%%
flowchart TD
  classDef ok fill:#dcfce7,stroke:#15803d,stroke-width:2px,color:#14532d
  classDef err fill:#fee2e2,stroke:#b91c1c,stroke-width:2px,color:#7f1d1d
  classDef neutral fill:#ffffff,stroke:#64748b,stroke-width:2px,color:#0f172a

  A[Open protected route] --> B{Token in storage?}
  B -->|No| C[Redirect /login]
  B -->|Yes| D[GET /auth/me]
  D --> E{Response?}
  E -->|200| F[Render page]
  E -->|401 / 403| G[Clear token → /login]
  E -->|Network error| H[Optional offline UX]

  class F ok
  class C,G err
  class A,B,D,E,H neutral
```

---

## 3. Simulation lifecycle (start → run → stop)

Logical flow from operator action to background processing and live UI updates.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif, system-ui, sans-serif','fontSize':'15px','primaryColor':'#ffffff','primaryTextColor':'#0f172a','primaryBorderColor':'#0d9488','secondaryColor':'#ffffff','secondaryTextColor':'#0f172a','secondaryBorderColor':'#64748b','tertiaryColor':'#f1f5f9','tertiaryTextColor':'#0f172a','tertiaryBorderColor':'#475569','lineColor':'#334155','textColor':'#0f172a','mainBkg':'#ffffff','nodeBorder':'#475569','clusterBkg':'#e8eef4','clusterBorder':'#64748b','edgeLabelBackground':'#ffffff','titleColor':'#0f172a'},'flowchart':{'curve':'basis','padding':18,'nodeSpacing':50,'rankSpacing':58,'useMaxWidth':true}}}%%
flowchart TD
  subgraph operator[" Operator "]
    O1[Optional blizzard scenario]
    O2[POST /simulation/start/:id]
    O3[POST /simulation/stop/:id]
  end

  subgraph api[" API "]
    S[Start endpoint]
    W[spawn simulation worker]
  end

  subgraph worker[" Worker loop "]
    L[Load shipment + route]
    T[Tick truck thermal weather]
    P[Publish telemetry + lifecycle → Redis]
    R{Reroute risk?}
    RS[Agent suggest_reroute]
    H[Pause / pending_reroute]
  end

  subgraph realtime[" Live UI "]
    WS[WS subscribers]
    FE[Map + activity log]
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
  R -->|human gate| H
  O3 -.->|cancel| W
```

**Telemetry vs lifecycle:** the worker publishes **telemetry** (position, temps, weather) on a schedule and **lifecycle** events (agents called, reroute suggested, blizzard entered, etc.). The dashboard WebSocket fans those out to connected clients.

---

## 4. Reroute decision (agent pipeline)

Two modes: **no Groq key** (deterministic graph) vs **Groq key set** (LLM planner + critic + supervisor). Both respect **human-in-the-loop** (no auto-apply).

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif, system-ui, sans-serif','fontSize':'15px','primaryColor':'#ffffff','primaryTextColor':'#0f172a','primaryBorderColor':'#0d9488','secondaryColor':'#ffffff','secondaryTextColor':'#0f172a','secondaryBorderColor':'#64748b','tertiaryColor':'#f1f5f9','tertiaryTextColor':'#0f172a','tertiaryBorderColor':'#475569','lineColor':'#334155','textColor':'#0f172a','mainBkg':'#ffffff','nodeBorder':'#475569','clusterBkg':'#e8eef4','clusterBorder':'#64748b','edgeLabelBackground':'#ffffff','titleColor':'#0f172a'},'flowchart':{'curve':'basis','padding':16,'useMaxWidth':true}}}%%
flowchart TD
  classDef base fill:#ffffff,stroke:#475569,stroke-width:2px,color:#0f172a
  classDef gate fill:#fef9c3,stroke:#ca8a04,stroke-width:2px,color:#713f12
  classDef llm fill:#e0e7ff,stroke:#4338ca,stroke-width:2px,color:#1e1b4b
  classDef out fill:#dcfce7,stroke:#15803d,stroke-width:2px,color:#14532d

  START([suggest_reroute]) --> PERC["Perception tools<br/>warehouses · legs · thermal · weather · memory"]
  PERC --> KEY{GROQ_API_KEY set?}

  KEY -->|No| DET["Deterministic LangGraph<br/>env → staging → nav → supervisor"]
  DET --> OUT1([Suggestion + AgentDecision])

  KEY -->|Yes| PLAN["Planner LLM · JSON candidates"]
  PLAN --> EVAL["Evaluate ETAs per candidate"]
  EVAL --> CRIT["Critic · allowlist + rejects"]
  CRIT --> SUP["Supervisor LLM · pick one"]
  SUP --> OUT2([Suggestion + AgentDecision])

  OUT1 --> PERSIST[Persist logs + memory]
  OUT2 --> PERSIST
  PERSIST --> EVT[API / WS reroute_suggested]
  EVT --> OP{Operator}
  OP -->|confirm| APPLY[Apply route]
  OP -->|reject| MEM[Memory reject id]

  class KEY,OP gate
  class PLAN,SUP llm
  class OUT1,OUT2,APPLY,PERSIST,EVT out
  class START,PERC,DET,EVAL,CRIT,MEM base
```

---

## 5. Human-in-the-loop reroute (UI + API)

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif, system-ui, sans-serif','fontSize':'15px','actorBkg':'#e8eef4','actorBorder':'#0d9488','actorTextColor':'#0f172a','actorLineColor':'#0d9488','signalColor':'#334155','signalTextColor':'#0f172a','labelBoxBkgColor':'#e8eef4','labelBoxBorderColor':'#0d9488','labelTextColor':'#0f172a','loopTextColor':'#0f172a','noteBkgColor':'#fef3c7','noteTextColor':'#78350f','noteBorderColor':'#ca8a04','textColor':'#0f172a','lineColor':'#334155'},'sequence':{'actorFontSize':15,'messageFontSize':14,'boxMargin':10}}}%%
sequenceDiagram
  autonumber
  participant Op as Operator
  participant UI as Simulation UI
  participant API as FastAPI
  participant DB as PostgreSQL

  Note over UI: pending_reroute or paused
  UI->>Op: Modal · warehouse · reasoning · mi ETA
  alt Confirm reroute
    Op->>UI: Confirm
    UI->>API: POST …/confirm-reroute/:id
    API->>DB: Commit route + status
    API-->>UI: OK
    UI->>UI: Refresh map + resume
  else Reject
    Op->>UI: Reject
    UI->>API: POST …/reject-reroute/:id
    API->>DB: Append rejected warehouse
    API-->>UI: OK
  end
```

---

## 6. Shipment & routing data (simplified)

How a shipment moves from creation to simulation-ready state.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif, system-ui, sans-serif','fontSize':'15px','primaryColor':'#ffffff','primaryTextColor':'#0f172a','primaryBorderColor':'#0d9488','secondaryColor':'#ffffff','secondaryTextColor':'#0f172a','secondaryBorderColor':'#64748b','tertiaryColor':'#f1f5f9','tertiaryTextColor':'#0f172a','tertiaryBorderColor':'#475569','lineColor':'#334155','textColor':'#0f172a','mainBkg':'#ffffff','nodeBorder':'#475569','clusterBkg':'#e8eef4','clusterBorder':'#64748b','edgeLabelBackground':'#ffffff','titleColor':'#0f172a'},'flowchart':{'curve':'basis','padding':24,'useMaxWidth':true}}}%%
flowchart LR
  classDef api fill:#ffffff,stroke:#0d9488,stroke-width:2.5px,color:#0f172a
  classDef data fill:#f1f5f9,stroke:#475569,stroke-width:2px,color:#0f172a
  classDef ext fill:#fff7ed,stroke:#c2410c,stroke-width:2px,color:#7c2d12

  A["POST /shipments"] --> B[("Shipment row")]
  B --> C["OSRM default polyline"]
  C --> D["Warehouse markers map"]
  D --> E["Simulation ticks + remaining path"]

  class A api
  class B,D,E data
  class C ext
```

---

## Related docs

- [AGENTIC_REROUTE.md](./AGENTIC_REROUTE.md) — agent tools, constraints, observability
- [API_CONTRACT.md](./API_CONTRACT.md) — REST + WebSocket summary
- [sentinel_backend_manual_simulation.md](./sentinel_backend_manual_simulation.md) — hands-on simulation steps

---

## Exporting diagrams to PNG

### Option A — npm script (recommended)

From the **`docs/`** folder:

```bash
cd docs
npm install
npm run diagrams:png
```

`npm install` runs **`postinstall`**, which tries to download **Chrome Headless Shell** for Puppeteer (~150MB). `@mermaid-js/mermaid-cli` uses **`puppeteer-core`**, which does not bundle a browser—so that step is required for PNG export.

If **`Could not find Chrome`** appears, install the browser explicitly:

```bash
cd docs
npm run diagrams:install-browser
npm run diagrams:png
```

Or in one line: **`npm run diagrams:png:all`**

PNG files are named from the **nearest `##` section title** (URL-style slug). Examples for the current doc:

| File | Section |
|------|---------|
| `system-context.png` | §1 System context |
| `authentication-flow.png` | §2 Authentication (sequence diagram) |
| `authentication-flow-2.png` | §2 Authentication (protected-route flowchart) |
| `simulation-lifecycle.png` | §3 Simulation lifecycle |
| `reroute-decision.png` | §4 Reroute decision |
| `human-in-the-loop-reroute.png` | §5 Human-in-the-loop reroute |
| `shipment-and-routing-data.png` | §6 Shipment & routing data |

Intermediate **`.mmd`** sources live in **`docs/diagrams/build/`** with the same base name.

**CI / headless servers:** set `PUPPETEER_SKIP_BROWSER_DOWNLOAD=1` before `npm install` to skip the postinstall download; install Chrome separately or use [mermaid.live](https://mermaid.live) for one-off exports.

**Optional environment variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `MERMAID_WIDTH` | `2400` | Canvas width |
| `MERMAID_HEIGHT` | `1800` | Canvas height |
| `MERMAID_BG` | `white` | Background (`transparent` also works) |

Example:

```bash
MERMAID_WIDTH=3200 MERMAID_HEIGHT=2400 npm run diagrams:png
```

Styling for CLI output is controlled by **`docs/mermaid-config.json`**, using the same light fills, dark text (`#0f172a`), teal borders (`#0d9488`), and slate lines (`#334155`) as the inline `%%{init: …}%%` blocks above.

### Option B — one-off `npx` (no `docs/package.json` install)

```bash
cd docs
npx --yes @mermaid-js/mermaid-cli@latest -i diagrams/build/manual.mmd -o diagrams/png/out.png -c mermaid-config.json -w 2400 -H 1800 -b white
```

Create **`diagrams/build/manual.mmd`** containing a single Mermaid diagram (no markdown fence).

### Option C — Python wrapper

If you prefer Python to invoke the same CLI:

```python
import subprocess
from pathlib import Path

DOCS = Path(__file__).resolve().parent
subprocess.run(
    [
        "npx", "--yes", "@mermaid-js/mermaid-cli@latest",
        "-i", str(DOCS / "diagrams/build/manual.mmd"),
        "-o", str(DOCS / "diagrams/png/out.png"),
        "-c", str(DOCS / "mermaid-config.json"),
        "-w", "2400", "-H", "1800", "-b", "white",
    ],
    cwd=DOCS,
    check=True,
)
```

Requires **Node + npx** on `PATH`.

### Git ignore for generated assets

**`docs/.gitignore`** ignores `diagrams/build/` and `diagrams/png/` by default. Remove those lines if you want PNGs committed for coursework or slides.
