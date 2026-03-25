# Sentinel — Frontend

React **Vite** client for **Project Sentinel**: dashboard, shipments, JWT auth, and **WebSocket** live events. UI uses **Tailwind CSS** and **shadcn-style** primitives (Radix + `class-variance-authority`).

## What lives here

| Area | Location |
|------|----------|
| Routes & shell | `src/App.tsx`, `src/components/layout/` |
| Pages | `src/pages/` |
| API helpers | `src/lib/api.ts` |
| Auth state | `src/store/auth.ts` (Zustand + persist) |
| UI primitives | `src/components/ui/` |

## Dependencies

Declared in **`package.json`**. Install locally (no global installs required):

```bash
cd apps/frontend
npm install
```

Use **Node 20+** (22 LTS recommended). Lockfile is `package-lock.json` for reproducible installs (`npm ci` in Docker).

## Configuration

1. Copy `apps/frontend/.env.example` to `apps/frontend/.env` (or `.env.local`).
2. Set **`VITE_API_BASE_URL`** (REST, e.g. `http://localhost:8000`) and **`VITE_WS_URL`** (WebSocket, e.g. `ws://localhost:8000/ws/dashboard`).
3. Only variables prefixed with **`VITE_`** are exposed to the browser. **Never** put Groq or other secrets in the frontend; the API key stays on the backend only.

## Demo login

On the **first** backend start with an empty `users` table, the API seeds **`demo` / `SentinelDemo2026!`** (admin). The landing page shows this hint; the sign-in form is pre-filled in development.

## Run (local)

Requires the **backend** running (default http://localhost:8000).

```bash
npm run dev
```

Vite dev server defaults to **http://localhost:5173** and proxies `/auth`, `/shipments`, `/dashboard`, and `/ws` to the backend (see `vite.config.ts`).

## Build

```bash
npm run build
```

Output: `dist/`. Production image uses **nginx** (`Dockerfile` + `nginx.conf`); see repo root **README** and **docker-compose** for full stack.
