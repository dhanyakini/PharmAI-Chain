# Sentinel — Frontend

React **Vite** client for **Project Sentinel**: dashboard, shipments, JWT auth, simulation UI, and **WebSocket** live events. Styling uses **Tailwind CSS** and **shadcn-style** primitives (Radix + `class-variance-authority`).

**Monorepo:** [../../README.md](../../README.md) · **Backend API:** [../backend/README.md](../backend/README.md)

**Docs:** [../../docs/API_CONTRACT.md](../../docs/API_CONTRACT.md) · [../../docs/FLOWCHARTS.md](../../docs/FLOWCHARTS.md) (system + auth + simulation UI flows) · [../../docs/sentinel_backend_manual_simulation.md](../../docs/sentinel_backend_manual_simulation.md)

PNG exports of those diagrams: from repo root, `cd docs && npm install && npm run diagrams:png` → **`docs/diagrams/png/`** (files named after each `##` section in FLOWCHARTS.md).

## What lives here

| Area | Location |
|------|----------|
| Routes & shell | `src/App.tsx`, `src/components/layout/` |
| Pages | `src/pages/` (incl. `simulation.tsx`, `login.tsx`) |
| API helpers | `src/lib/api.ts` |
| Auth state | `src/stores/auth-store.ts` (Zustand + persist) |
| UI primitives | `src/components/ui/` |

## Dependencies

Declared in **`package.json`**. Install from this directory:

```bash
cd apps/frontend
npm install
```

Use **Node 20+** (22 LTS recommended). Reproducible CI/Docker installs: **`npm ci`** (uses `package-lock.json`).

## Configuration

1. Copy **`.env.example`** → **`.env`** or **`.env.local`** in `apps/frontend`.
2. **`VITE_API_BASE_URL`** — REST base for Axios (`src/lib/api.ts`). If unset, the client defaults to **`http://localhost:8000`**. The backend should allow CORS from **`http://localhost:5173`** in local dev.
3. **`VITE_WS_URL`** — WebSocket URL for the dashboard stream (default in code: `ws://localhost:8000/ws/dashboard`); see `src/stores/simulation-store.ts`.

The Vite dev server **proxy** (`vite.config.ts`) forwards **`/auth`**, **`/routes`**, **`/health`**, and **`/ws`** only. **`/shipments`**, **`/dashboard`**, and **`/simulation`** are **not** proxied (they are SPA routes), so most API calls use the **`VITE_API_BASE_URL`** host directly.

Only variables prefixed with **`VITE_`** are exposed to the browser. **Never** put `GROQ_API_KEY` or other secrets here; those belong in **`apps/backend/.env`** only.

## Default login (local backend)

The sign-in page does not show these hints; use this section when running locally. Matches the backend’s **`seed_admin_user()`** defaults when `ENV=local` and the `users` table is empty:

| Field    | Value               |
|----------|---------------------|
| Username | `admin`             |
| Password | `admin123456`       |

Override seeding with **`SEED_ADMIN_USERNAME`**, **`SEED_ADMIN_EMAIL`**, **`SEED_ADMIN_PASSWORD`** in **`apps/backend/.env`** (see [../backend/README.md](../backend/README.md)). Register additional users via **`POST /auth/register`** or Swagger.

## Run (local)

Start **Postgres**, **Redis**, and the **backend** first (see [../backend/README.md](../backend/README.md)).

```bash
cd apps/frontend
npm run dev
```

Dev server: **http://localhost:5173**. Ensure the API is on the host/port implied by **`VITE_API_BASE_URL`** (default port **8000**).

## Build

```bash
npm run build
```

Output: **`dist/`**. Typecheck: **`npm run lint`** (`tsc --noEmit`).

## Docker / production

The **`Dockerfile`** here builds the SPA and serves it with **nginx** (`nginx.conf`). Full stack: repository root **`README.md`** and **`docker-compose.yml`**.
