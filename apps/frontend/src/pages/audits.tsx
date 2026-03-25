import * as React from "react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Shipment = { id: number; shipment_code: string };

type InterventionLog = {
  id: number;
  timestamp: string | null;
  agent_role: string;
  trigger_reason: string;
  reasoning_trace: string;
  action_taken: string;
  confidence_score: number | null;
  suggested_route: any;
};

export default function AuditsPage() {
  const [shipments, setShipments] = React.useState<Shipment[]>([]);
  const [shipmentId, setShipmentId] = React.useState<number | null>(null);
  const [logs, setLogs] = React.useState<InterventionLog[]>([]);
  const [loading, setLoading] = React.useState(true);

  async function loadShipments() {
    const res = await api.get<Shipment[]>("/shipments");
    setShipments(res.data);
    if (!shipmentId && res.data.length) setShipmentId(res.data[0].id);
  }

  async function loadLogs(id: number) {
    setLoading(true);
    try {
      const res = await api.get<InterventionLog[]>(`/shipments/${id}/interventions`);
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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold">Audits</h1>
          <p className="text-sm text-muted-foreground">Intervention logs for supervised events.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={shipmentId ?? ""}
            onChange={(e) => setShipmentId(Number(e.target.value))}
          >
            {shipments.map((s) => (
              <option key={s.id} value={s.id}>
                {s.shipment_code}
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
          <CardTitle className="text-lg">Intervention Logs</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          {loading ? (
            <div className="text-muted-foreground">Loading...</div>
          ) : logs.length === 0 ? (
            <div className="text-muted-foreground">No intervention logs yet.</div>
          ) : (
            <div className="overflow-auto">
              <table className="w-full">
                <thead className="bg-muted/30 text-muted-foreground">
                  <tr className="text-left text-xs">
                    <th className="p-2">Time</th>
                    <th className="p-2">Agent</th>
                    <th className="p-2">Action</th>
                    <th className="p-2">Trigger</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id} className="border-t">
                      <td className="p-2 whitespace-nowrap text-muted-foreground">{l.timestamp?.slice(0, 19)}</td>
                      <td className="p-2">{l.agent_role}</td>
                      <td className="p-2">{l.action_taken}</td>
                      <td className="p-2 text-muted-foreground">{l.trigger_reason}</td>
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

