import * as React from "react";

import { useSimulationStore } from "@/stores/simulation-store";

export function useDashboardWebSocket(shipmentId: number | null) {
  const connect = useSimulationStore((s) => s.connect);
  const disconnect = useSimulationStore((s) => s.disconnect);

  React.useEffect(() => {
    if (!shipmentId) return;
    connect(shipmentId);
    return () => {
      disconnect();
    };
  }, [shipmentId, connect, disconnect]);
}

