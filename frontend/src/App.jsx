/**
 * Project Sentinel — Command Center Dashboard
 * Stack: React + Vite + Tailwind CSS + React-Leaflet
 *
 * Install deps:
 *   npm install react-leaflet leaflet axios
 *   npm install -D tailwindcss
 */

import { useState, useEffect, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline } from "react-leaflet";
import axios from "axios";
import "leaflet/dist/leaflet.css";

const API = "http://localhost:8000";

const NJ_POS  = [40.7128, -74.006];
const BOS_POS = [42.3601, -71.0589];

// ── Small sub-components ──────────────────────────────────────────────────────
function StatusBadge({ value, label }) {
  const isOk = typeof value === "number"
    ? value < 0.5
    : value === "CLEAR";
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
                                      "text-green-300";
  return <p className={`text-sm font-mono ${color} border-b border-gray-700 py-1`}>{text}</p>;
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [state,   setState]   = useState(null);
  const [logs,    setLogs]    = useState([]);
  const [loading, setLoading] = useState(false);
  const logRef = useRef(null);

  // Poll /state every 2 seconds
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const { data } = await axios.get(`${API}/state`);
        setState(data);
      } catch { /* backend not running yet */ }
    }, 2000);
    return () => clearInterval(id);
  }, []);

  // Auto-scroll log window
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  const runAgents = async () => {
    setLoading(true);
    const { data } = await axios.post(`${API}/run`);
    setLogs(prev => [...prev, ...data.logs]);
    setLoading(false);
  };

  const triggerBlizzard = async () => {
    setLoading(true);
    const { data } = await axios.post(`${API}/simulate-blizzard`);
    setLogs(prev => [...prev, "🚨 BLIZZARD TRIGGERED", ...data.logs]);
    setLoading(false);
  };

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
        <span className="text-xs text-gray-400">Insulin Cold Chain — NJ → Boston</span>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* LEFT: Map */}
        <div className="w-1/2 relative">
          <MapContainer
            center={[41.5, -72.5]}
            zoom={7}
            className="h-full w-full"
          >
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
            {state && (
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
            {state && <>
              <StatusBadge value={state.cargo_temp}    label="Cargo °C" />
              <StatusBadge value={state.external_temp} label="Ext °C" />
              <StatusBadge value={state.risk_score}    label="Risk Score" />
              <StatusBadge value={state.road_status}   label="Road" />
              <StatusBadge value={state.fuel}          label="Fuel %" />
            </>}
          </div>

          {/* Controls */}
          <div className="flex gap-2 px-4 pb-3">
            <button
              onClick={runAgents}
              disabled={loading}
              className="bg-cyan-600 hover:bg-cyan-500 px-4 py-2 rounded font-semibold text-sm disabled:opacity-50"
            >
              ▶ Run Agents
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
              className="bg-gray-600 hover:bg-gray-500 px-4 py-2 rounded font-semibold text-sm"
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