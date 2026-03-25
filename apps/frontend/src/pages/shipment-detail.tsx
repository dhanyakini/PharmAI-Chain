import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Shipment = {
  id: number;
  shipment_code: string;
  status: string;
  origin_lat: number;
  origin_lng: number;
  destination_lat: number;
  destination_lng: number;
  truck_name: string;
};

export default function ShipmentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const shipmentId = Number(id);

  const [shipment, setShipment] = React.useState<Shipment | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [statusMsg, setStatusMsg] = React.useState<string | null>(null);

  async function load() {
    if (!shipmentId) return;
    setLoading(true);
    try {
      const res = await api.get<Shipment>(`/shipments/${shipmentId}`);
      setShipment(res.data);
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shipmentId]);

  async function onStart() {
    setStatusMsg(null);
    try {
      await api.post(`/simulation/start/${shipmentId}`);
      setStatusMsg("Simulation started. Watching telemetry in the next phases.");
      await load();
    } catch (e: any) {
      setStatusMsg(e?.response?.data?.detail ?? "Failed to start simulation");
    }
  }

  async function onStop() {
    setStatusMsg(null);
    try {
      await api.post(`/simulation/stop/${shipmentId}`);
      setStatusMsg("Simulation stopping...");
      await load();
    } catch (e: any) {
      setStatusMsg(e?.response?.data?.detail ?? "Failed to stop simulation");
    }
  }

  async function onConfirmReroute() {
    setStatusMsg(null);
    try {
      await api.post(`/simulation/confirm-reroute/${shipmentId}`);
      setStatusMsg("Reroute confirmed and applied.");
      await load();
    } catch (e: any) {
      setStatusMsg(e?.response?.data?.detail ?? "Failed to confirm reroute");
    }
  }

  if (loading) {
    return <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">Loading shipment...</div>;
  }

  if (!shipment) {
    return <div className="rounded-lg border bg-card p-6 text-sm text-destructive">Shipment not found.</div>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Shipment {shipment.shipment_code.slice(0, 10)}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <div className="text-muted-foreground">Truck</div>
              <div className="font-medium">{shipment.truck_name}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Status</div>
              <div className="font-medium">{shipment.status}</div>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <div className="text-muted-foreground">Origin</div>
              <div className="font-medium">
                {shipment.origin_lat.toFixed(4)}, {shipment.origin_lng.toFixed(4)}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">Destination</div>
              <div className="font-medium">
                {shipment.destination_lat.toFixed(4)}, {shipment.destination_lng.toFixed(4)}
              </div>
            </div>
          </div>

          {statusMsg ? <div className="text-sm">{statusMsg}</div> : null}

          <div className="flex flex-wrap gap-2 pt-2">
            <Button onClick={() => void onStart()}>Start Simulation</Button>
            <Button variant="outline" onClick={() => void onStop()}>
              Stop
            </Button>
            <Button variant="secondary" onClick={() => void onConfirmReroute()}>
              Confirm Reroute
            </Button>
            <Button
              variant="ghost"
              onClick={() => navigate(`/simulation/${shipmentId}`)}
            >
              Open Command Center
            </Button>
            <Button variant="ghost" onClick={() => navigate("/shipments")}>
              Back to List
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

