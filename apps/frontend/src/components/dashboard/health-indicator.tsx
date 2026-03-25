import * as React from "react";
import { Activity, Database, PlugZap } from "lucide-react";

import { cn } from "@/lib/utils";

function StatusLine({
  label,
  ok,
  extra,
}: {
  label: string;
  ok: boolean;
  extra?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border bg-card px-3 py-2">
      <div className="space-y-0.5">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className={cn("text-sm font-medium", ok ? "text-emerald-600" : "text-destructive")}>
          {ok ? "Connected" : "Down"}
        </div>
      </div>
      {extra ? <div className="text-xs text-muted-foreground">{extra}</div> : null}
    </div>
  );
}

export default function HealthIndicator({
  liveState,
}: {
  liveState: {
    api_connected: boolean;
    websocket_connected: number;
    redis_connected: boolean;
    simulation_running: boolean;
  };
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <StatusLine label="API" ok={liveState.api_connected} extra={<PlugZap className="inline h-4 w-4 ml-1" />} />
      <StatusLine label="WebSocket" ok={liveState.websocket_connected > 0} extra={liveState.websocket_connected} />
      <StatusLine label="Redis" ok={liveState.redis_connected} extra={<Database className="inline h-4 w-4 ml-1" />} />
      <StatusLine label="Simulation" ok={liveState.simulation_running} extra={<Activity className="inline h-4 w-4 ml-1" />} />
    </div>
  );
}

