import * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Telemetry = {
  lat: number;
  lng: number;
  heading: number;
  speed?: number;
  weather_state?: string;
  risk_level?: number;
  internal_temp?: number;
  external_temp?: number;
  timestamp?: string;
};

export default function TelemetryCard({ telemetry }: { telemetry: Telemetry | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Telemetry</CardTitle>
      </CardHeader>
      <CardContent className="text-sm space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="text-muted-foreground">Weather</div>
            <div className="font-medium">{telemetry?.weather_state ?? "—"}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Risk</div>
            <div className="font-medium">{telemetry?.risk_level ?? "—"}</div>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="text-muted-foreground">Internal Temp</div>
            <div className="font-medium">
              {typeof telemetry?.internal_temp === "number" ? `${telemetry.internal_temp.toFixed(2)}F` : "—"}
            </div>
          </div>
          <div>
            <div className="text-muted-foreground">External Temp</div>
            <div className="font-medium">
              {typeof telemetry?.external_temp === "number" ? `${telemetry.external_temp.toFixed(2)}F` : "—"}
            </div>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="text-muted-foreground">Heading</div>
            <div className="font-medium">{telemetry ? `${telemetry.heading.toFixed(0)}°` : "—"}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Speed</div>
            <div className="font-medium">{telemetry?.speed ? `${telemetry.speed.toFixed(0)} km/h` : "—"}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

