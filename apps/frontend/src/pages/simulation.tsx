import * as React from "react";
import { useParams } from "react-router-dom";

import { api } from "@/lib/api";
import SimulationMap from "@/components/map/simulation-map";
import { Button } from "@/components/ui/button";
import ActivityLogCard from "@/components/simulation/activity-log-card";
import RerouteModal from "@/components/simulation/reroute-modal";
import { useDashboardWebSocket } from "@/hooks/use-websocket";
import { useSimulationStore } from "@/stores/simulation-store";

type RoutePolyline = number[][];

type LiveSimulationState = {
  shipment_id: number;
  running: boolean;
  state: any;
  origin: { lat: number; lng: number };
  destination: { lat: number; lng: number };
  warehouses: { id: number; name: string; lat: number; lng: number }[];
  default_route_polyline?: RoutePolyline | null;
  current_route_polyline?: RoutePolyline | null;
  remaining_polyline?: RoutePolyline | null;
  paused_for_reroute_confirmation?: boolean;
  pending_reroute?: any | null;
};

export default function SimulationPage() {
  const { id } = useParams();
  const shipmentId = Number(id);

  const [sim, setSim] = React.useState<LiveSimulationState | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [wsEnabled, setWsEnabled] = React.useState(false);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [startBusy, setStartBusy] = React.useState(false);
  const [stopBusy, setStopBusy] = React.useState(false);
  const [startRequested, setStartRequested] = React.useState(false);
  const [stopRequested, setStopRequested] = React.useState(false);

  const telemetry = useSimulationStore((s) => s.telemetry);
  const activitySteps = useSimulationStore((s) => s.activitySteps);
  const rerouteSuggestion = useSimulationStore((s) => s.rerouteSuggestion);
  const wsStatus = useSimulationStore((s) => s.wsStatus);
  const setInitialTimeline = useSimulationStore((s) => s.setInitialTimeline);
  const setInitialTelemetry = useSimulationStore((s) => s.setInitialTelemetry);
  const dismissRerouteSuggestion = useSimulationStore((s) => s.dismissRerouteSuggestion);
  const setRerouteSuggestion = useSimulationStore((s) => s.setRerouteSuggestion);

  useDashboardWebSocket(wsEnabled ? shipmentId : null);

  async function refreshState() {
    const res = await api.get<LiveSimulationState>(`/simulation/state/${shipmentId}`);
    setSim(res.data);
    const state = res.data.state;
    if (state?.truck) {
      setInitialTelemetry({
        lat: state.truck.lat,
        lng: state.truck.lng,
        heading: state.truck.heading,
        speed: state.truck.speed_kmh,
        weather_state: state.weather?.weather_state,
        risk_level: state.weather?.risk_level,
      });
    }
    setRerouteSuggestion(res.data.pending_reroute ?? null);
    return res.data;
  }

  async function refreshTimeline() {
    const res = await api.get(lifecycleUrlFor(shipmentId));
    setInitialTimeline(res.data);
  }

  function lifecycleUrlFor(id: number) {
    return `/simulation/lifecycle/${id}`;
  }

  React.useEffect(() => {
    if (!shipmentId) return;
    let cancelled = false;

    async function boot() {
      try {
        setLoading(true);
        const state = await refreshState();
        if (state.running) {
          await refreshTimeline();
        } else {
          setInitialTimeline([]);
        }
        setWsEnabled(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void boot();

    return () => {
      cancelled = true;
    };
  }, [shipmentId]);

  React.useEffect(() => {
    if (!sim?.running) return;
    const t = window.setInterval(() => {
      void refreshState().catch(() => {});
    }, 2500);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sim?.running, shipmentId]);

  React.useEffect(() => {
    if (!sim) return;
    if (sim.running) {
      // Once backend confirms it's running, drop request flags.
      setStartRequested(false);
      setStopRequested(false);
    } else {
      // Only clear stop requested once we observe non-running.
      if (stopRequested) setStopRequested(false);
    }
  }, [sim?.running, stopRequested]);

  React.useEffect(() => {
    const last = activitySteps[activitySteps.length - 1];
    if (!last) return;
    if (last.kind === "lifecycle" && last.event_name === "reroute_applied") {
      void refreshState().catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activitySteps.length]);

  async function onStart() {
    setMsg(null);
    setStartBusy(true);
    setStartRequested(true);
    setStopRequested(false);
    try {
      await api.post(`/simulation/start/${shipmentId}`);
      setMsg("Simulation started.");
      await refreshState().catch(() => {});
    } catch (e: any) {
      setMsg(e?.response?.data?.detail ?? "Failed to start simulation");
      setStartRequested(false);
    } finally {
      setStartBusy(false);
    }
  }

  async function onStop() {
    setMsg(null);
    setStopBusy(true);
    setStopRequested(true);
    setStartRequested(false);
    try {
      await api.post(`/simulation/stop/${shipmentId}`);
      setMsg("Simulation stopping...");
      await refreshState().catch(() => {});
    } catch (e: any) {
      setMsg(e?.response?.data?.detail ?? "Failed to stop simulation");
      setStopRequested(false);
    } finally {
      setStopBusy(false);
    }
  }

  async function onSaveSimulation() {
    setMsg(null);
    try {
      const res = await api.get(`/simulation/export/${shipmentId}`);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `simulation-${shipmentId}-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setMsg("Simulation data saved as JSON.");
    } catch (e: any) {
      setMsg(e?.response?.data?.detail ?? "Failed to save simulation data");
    }
  }

  if (loading || !sim) {
    return <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">Loading simulation...</div>;
  }

  const origin = sim.origin;
  const destination = sim.destination;
  const effectiveRunning = Boolean(sim.running) || startRequested;
  const effectiveStopped = !sim.running && stopRequested;

  return (
    <div className="space-y-4">
      {msg ? <div className="rounded-lg border bg-card p-3 text-sm">{msg}</div> : null}

      <div className="rounded-lg border bg-card overflow-hidden">
        <div className="p-3 flex items-center justify-between gap-3 border-b bg-muted/30">
          <div>
            <div className="text-sm text-muted-foreground">Shipment</div>
            <div className="text-lg font-semibold">#{sim.shipment_id}</div>
          </div>
          <div className="flex gap-2 flex-wrap justify-end">
            <Button onClick={() => void onStart()} disabled={effectiveRunning || startBusy || stopBusy}>
              Start
            </Button>
            <Button
              variant="outline"
              onClick={() => void onStop()}
              disabled={!effectiveRunning || stopBusy || effectiveStopped || stopRequested}
            >
              Stop
            </Button>
            <Button
              variant="secondary"
              onClick={() => null}
              disabled={!effectiveRunning || !rerouteSuggestion || stopBusy || startBusy}
            >
              Awaiting Decision
            </Button>
            <Button variant="outline" onClick={() => void onSaveSimulation()} disabled={startBusy || stopBusy}>
              Save Simulation
            </Button>
          </div>
        </div>

        <SimulationMap
          origin={origin}
          destination={destination}
          defaultRoutePolyline={
            (sim.default_route_polyline ?? sim.current_route_polyline ?? undefined) || undefined
          }
          currentRoutePolyline={(sim.current_route_polyline ?? undefined) || undefined}
          remainingPolyline={(sim.remaining_polyline ?? sim.current_route_polyline ?? undefined) || undefined}
          proposedReroutePolyline={(rerouteSuggestion?.proposed_remaining_polyline as number[][] | undefined) ?? undefined}
          warehouses={sim.warehouses}
          telemetry={telemetry}
        />
      </div>

      <ActivityLogCard steps={activitySteps} />

      <RerouteModal
        open={Boolean(rerouteSuggestion)}
        shipmentId={shipmentId}
        suggestion={rerouteSuggestion}
        onClose={() => {
          dismissRerouteSuggestion();
          void refreshState().catch(() => {});
        }}
        onApplied={() => {
          void refreshState().catch(() => {});
          setMsg("Reroute applied.");
        }}
        onRejected={() => {
          void refreshState().catch(() => {});
          setMsg("Reroute rejected. Simulation resumed on current route.");
        }}
      />
    </div>
  );
}

