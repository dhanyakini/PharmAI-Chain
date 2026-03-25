import * as React from "react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Shipment = { id: number; shipment_code: string; truck_name: string };

type TelemetryLog = {
  id: number;
  timestamp: string | null;
  lat: number;
  lng: number;
  internal_temp: number;
  external_temp: number;
  weather_state: string;
  route_segment: string;
  risk_score: number | null;
};

export default function LogsPage() {
  const [shipments, setShipments] = React.useState<Shipment[]>([]);
  const [shipmentId, setShipmentId] = React.useState<number | null>(null);
  const [logs, setLogs] = React.useState<TelemetryLog[]>([]);
  const [loading, setLoading] = React.useState(true);

  async function loadShipments() {
    const res = await api.get<Shipment[]>("/shipments");
    setShipments(res.data);
    if (!shipmentId && res.data.length) setShipmentId(res.data[0].id);
  }

  async function loadLogs(id: number) {
    setLoading(true);
    try {
      const res = await api.get<TelemetryLog[]>(`/shipments/${id}/telemetry`);
      setLogs(res.data);
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    void loadShipments().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    if (!shipmentId) return;
    void loadLogs(shipmentId).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shipmentId]);

  const selectedShipment = shipments.find((s) => s.id === shipmentId) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold">Logs</h1>
          <p className="text-sm text-muted-foreground">Telemetry logs sampled during simulation.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={shipmentId ?? ""}
            onChange={(e) => setShipmentId(Number(e.target.value))}
          >
            {shipments.map((s) => (
              <option key={s.id} value={s.id}>
                {s.shipment_code} ({s.truck_name})
              </option>
            ))}
          </select>
          <Button variant="outline" onClick={() => shipmentId && void loadLogs(shipmentId)}>
            Refresh
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            Telemetry Logs {selectedShipment ? `— ${selectedShipment.shipment_code}` : ""}
          </CardTitle>
          {selectedShipment ? (
            <div className="text-sm text-muted-foreground">Truck: {selectedShipment.truck_name}</div>
          ) : null}
        </CardHeader>
        <CardContent className="text-sm">
          {loading ? (
            <div className="text-muted-foreground">Loading...</div>
          ) : logs.length === 0 ? (
            <div className="text-muted-foreground">No telemetry logs yet.</div>
          ) : (
            <div className="overflow-auto">
              <table className="w-full">
                <thead className="bg-muted/30 text-muted-foreground">
                  <tr className="text-left text-xs">
                    <th className="p-2">Time</th>
                    <th className="p-2">Internal</th>
                    <th className="p-2">External</th>
                    <th className="p-2">Weather</th>
                    <th className="p-2">Lat/Lng</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id} className="border-t">
                      <td className="p-2 whitespace-nowrap text-muted-foreground">{l.timestamp?.slice(0, 19)}</td>
                      <td className="p-2">{l.internal_temp.toFixed(1)}F</td>
                      <td className="p-2 text-muted-foreground">{l.external_temp.toFixed(1)}F</td>
                      <td className="p-2">{l.weather_state}</td>
                      <td className="p-2 text-muted-foreground whitespace-nowrap">
                        {l.lat.toFixed(4)}, {l.lng.toFixed(4)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

