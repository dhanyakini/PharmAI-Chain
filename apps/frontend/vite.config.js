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
                "/auth": target,
                "/shipments": target,
                "/dashboard": target,
                "/health": target,
                "/ws": { target: target.replace(/^http/, "ws"), ws: true },
            },
        },
    };
});
