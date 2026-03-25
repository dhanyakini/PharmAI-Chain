import * as React from "react";
import { Truck } from "lucide-react";

import { cn } from "@/lib/utils";

export default function StatsCards({
  shipmentCount,
  simulationRunningShipments,
}: {
  shipmentCount: number;
  simulationRunningShipments: number;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className={cn("rounded-lg border bg-card p-5 shadow-sm")}>
        <div className="text-xs text-muted-foreground">Shipments</div>
        <div className="mt-1 text-3xl font-semibold">{shipmentCount}</div>
      </div>
      <div className={cn("rounded-lg border bg-card p-5 shadow-sm")}>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Truck className="h-4 w-4" />
          Simulation Running
        </div>
        <div className="mt-1 text-3xl font-semibold">{simulationRunningShipments}</div>
      </div>
    </div>
  );
}

