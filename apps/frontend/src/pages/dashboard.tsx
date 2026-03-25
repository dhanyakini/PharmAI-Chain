import * as React from "react";
import { motion } from "framer-motion";

import { api } from "@/lib/api";
import HealthIndicator from "@/components/dashboard/health-indicator";
import StatsCards from "@/components/dashboard/stats-cards";

type LiveState = {
  api_connected: boolean;
  websocket_connected: number;
  redis_connected: boolean;
  simulation_running: boolean;
  simulation_running_shipments: number;
  shipment_count: number;
};

export default function DashboardPage() {
  const [liveState, setLiveState] = React.useState<LiveState | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        const res = await api.get<LiveState>("/dashboard/live-state");
        if (!cancelled) setLiveState(res.data);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    const id = window.setInterval(() => void load(), 5000);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="space-y-4">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
        <div className="mb-3">
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Operational status and simulation connectivity.</p>
        </div>
      </motion.div>

      {loading || !liveState ? (
        <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">Loading live state...</div>
      ) : (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
            <StatsCards
              shipmentCount={liveState.shipment_count}
              simulationRunningShipments={liveState.simulation_running_shipments}
            />
          </motion.div>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25, delay: 0.05 }}>
            <HealthIndicator liveState={liveState} />
          </motion.div>
        </>
      )}
    </div>
  );
}

