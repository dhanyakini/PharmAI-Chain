import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_BASE_URL || "http://localhost:8000";
  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "src") },
    },
    server: {
      port: 5173,
      proxy: {
        // Only proxy backend API paths that do NOT clash with SPA routes.
        // Important: do NOT proxy "/dashboard", "/shipments", "/simulation" because
        // those are also frontend routes and break refresh with "Not Found".
        "/auth": target,
        "/routes": target,
        "/health": target,
        // WebSocket URL is configured via VITE_WS_URL; keeping /ws proxy is harmless
        // and helps if the app ever uses relative ws paths.
        "/ws": { target: target.replace(/^http/, "ws"), ws: true },
      },
    },
  };
});
