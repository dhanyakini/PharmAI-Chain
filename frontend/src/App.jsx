/**
 * Project Sentinel — Command Center Dashboard
 * Fixes:
 *  - Polls /run/{job_id} after POST /run (async job pattern)
 *  - Polls /run/{job_id} after POST /simulate-blizzard
 *  - Fixes Leaflet default marker icon 404 (common React-Leaflet issue)
 *  - Guards against null state during initial load
 */

import { useState, useEffect, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline } from "react-leaflet";
import L from "leaflet";
import axios from "axios";
import "leaflet/dist/leaflet.css";

// ── Fix Leaflet's broken default icon paths in Vite/webpack builds ────────────
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl:       "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl:     "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const API     = "http://localhost:8000";
const NJ_POS  = [40.7128, -74.006];
const BOS_POS = [42.3601, -71.0589];
const POLL_MS = 1500; // how often to check job status

// ── Helpers ───────────────────────────────────────────────────────────────────
/**
 * Fires POST to `endpoint`, gets back a job_id, then polls /run/{job_id}
 * until status is "complete" or "error". Calls onLogs with the final logs.
 */
async function runJob(endpoint, onLogs, setLoading) {
  setLoading(true);
  try {
    const { data: job } = await axios.post(`${API}${endpoint}`);
    if (!job.job_id) {
      // Fallback: old-style synchronous response (original main.py)
      if (job.logs) onLogs(job.logs);
      return;
    }

    // Poll until done
    while (true) {
      await new Promise(r => setTimeout(r, POLL_MS));
      const { data: result } = await axios.get(`${API}/run/${job.job_id}`);
      if (result.status === "complete") {
        onLogs(result.logs ?? []);
        break;
      }
      if (result.status === "error") {
        onLogs([`[ERROR] ${result.detail ?? "Agent pipeline failed"}`]);
        break;
      }
      // still "pending" — keep polling
    }
  } catch (err) {
    onLogs([`[ERROR] ${err.message}`]);
  } finally {
    setLoading(false);
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────
function StatusBadge({ value, label }) {
  const isOk =
    typeof value === "number" ? value < 0.5 : value === "CLEAR";
  return (
    <div className="flex flex-col items-center bg-gray-800 rounded-lg p-3 min-w-[90px]">
      <span className={`text-xl font-bold ${isOk ? "text-green-400" : "text-red-400"}`}>
        {typeof value === "number" ? value.toFixed(2) : value}
      </span>
      <span className="text-xs text-gray-400 mt-1">{label}</span>
    </div>
  );
}

function LogEntry({ text }) {
  const color =
    text.startsWith("[SUPERVISOR]") ? "text-yellow-300 font-bold" :
    text.startsWith("[ANALYST]")    ? "text-blue-300"  :
    text.startsWith("[LOGISTICS]")  ? "text-purple-300":
    text.startsWith("[ERROR]")      ? "text-red-400 font-bold" :
                                      "text-green-300";
  return (
    <p className={`text-sm font-mono ${color} border-b border-gray-700 py-1`}>
      {text}
    </p>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [state,   setState]   = useState(null);
  const [logs,    setLogs]    = useState([]);
  const [loading, setLoading] = useState(false);
  const logRef = useRef(null);

  const appendLogs = (newLogs) =>
    setLogs(prev => [...prev, ...newLogs]);

  // Poll /state every 2 s
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const { data } = await axios.get(`${API}/state`);
        setState(data);
      } catch { /* backend not up yet */ }
    }, 2000);
    return () => clearInterval(id);
  }, []);

  // Auto-scroll log window
  useEffect(() => {
    if (logRef.current)
      logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  const runAgents = () =>
    runJob("/run", appendLogs, setLoading);

  const triggerBlizzard = () =>
    runJob("/simulate-blizzard", (ls) => appendLogs(["🚨 BLIZZARD TRIGGERED", ...ls]), setLoading);

  const resetSim = async () => {
    await axios.post(`${API}/reset`);
    setLogs([]);
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white flex flex-col">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-3 flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-widest text-cyan-400">
          🛡 PROJECT SENTINEL
        </h1>
        <div className="flex items-center gap-3">
          {loading && (
            <span className="text-xs text-yellow-400 animate-pulse">
              ⏳ Agents running…
            </span>
          )}
          <span className="text-xs text-gray-400">Insulin Cold Chain — NJ → Boston</span>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* LEFT: Map */}
        <div className="w-1/2 relative">
          <MapContainer center={[41.5, -72.5]} zoom={7} className="h-full w-full">
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution="© OpenStreetMap contributors"
            />
            <Marker position={NJ_POS}>
              <Popup>📦 Origin: New Jersey (Manufacturing)</Popup>
            </Marker>
            <Marker position={BOS_POS}>
              <Popup>🏥 Destination: Boston (Distribution)</Popup>
            </Marker>
            {state?.location && (
              <Marker position={state.location}>
                <Popup>🚚 Truck T-101 | Cargo: {state.cargo_temp}°C</Popup>
              </Marker>
            )}
            <Polyline positions={[NJ_POS, BOS_POS]} color="cyan" dashArray="6" />
          </MapContainer>
        </div>

        {/* RIGHT: Dashboard */}
        <div className="w-1/2 flex flex-col bg-gray-900 border-l border-gray-700">
          {/* Status row */}
          <div className="flex gap-3 p-4 flex-wrap">
            {state ? (
              <>
                <StatusBadge value={state.cargo_temp}    label="Cargo °C" />
                <StatusBadge value={state.external_temp} label="Ext °C" />
                <StatusBadge value={Math.max(0, state.risk_score)} label="Risk Score" />
                <StatusBadge value={state.road_status}   label="Road" />
                <StatusBadge value={state.fuel}          label="Fuel %" />
              </>
            ) : (
              <p className="text-gray-500 text-sm">Connecting to backend…</p>
            )}
          </div>

          {/* Controls */}
          <div className="flex gap-2 px-4 pb-3">
            <button
              onClick={runAgents}
              disabled={loading}
              className="bg-cyan-600 hover:bg-cyan-500 px-4 py-2 rounded font-semibold text-sm disabled:opacity-50"
            >
              {loading ? "⏳ Running…" : "▶ Run Agents"}
            </button>
            <button
              onClick={triggerBlizzard}
              disabled={loading}
              className="bg-red-700 hover:bg-red-600 px-4 py-2 rounded font-semibold text-sm disabled:opacity-50"
            >
              ❄ Simulate Blizzard
            </button>
            <button
              onClick={resetSim}
              disabled={loading}
              className="bg-gray-600 hover:bg-gray-500 px-4 py-2 rounded font-semibold text-sm disabled:opacity-50"
            >
              ↺ Reset
            </button>
          </div>

          {/* Agent Log */}
          <div
            ref={logRef}
            className="flex-1 overflow-y-auto bg-gray-950 mx-4 mb-4 rounded-lg p-3 border border-gray-700"
          >
            <p className="text-xs text-gray-500 mb-2">— AGENT ACTIVITY LOG —</p>
            {logs.length === 0
              ? <p className="text-gray-600 text-sm">No activity yet. Press "Run Agents" to start.</p>
              : logs.map((l, i) => <LogEntry key={i} text={l} />)
            }
          </div>
        </div>
      </div>
    </div>
  );
}