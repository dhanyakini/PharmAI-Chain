import * as React from "react";
import { Link } from "react-router-dom";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

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

export default function ShipmentsPage() {
  const [shipments, setShipments] = React.useState<Shipment[]>([]);
  const [loading, setLoading] = React.useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<Shipment[]>("/shipments");
      setShipments(res.data);
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    void load();
  }, []);

  async function onDelete(id: number) {
    const ok = window.confirm("Delete this shipment? This will remove all related simulation data.");
    if (!ok) return;
    await api.delete(`/shipments/${id}`);
    await load();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Shipments</h1>
          <p className="text-sm text-muted-foreground">Create routes, run simulations, and manage logistics events.</p>
        </div>
        <Button asChild>
          <Link to="/shipments/new">New Shipment</Link>
        </Button>
      </div>

      {loading ? (
        <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">Loading shipments...</div>
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/30 text-muted-foreground">
              <tr className="text-left">
                <th className="p-3 font-medium">Code</th>
                <th className="p-3 font-medium">Truck</th>
                <th className="p-3 font-medium">Status</th>
                <th className="p-3 font-medium">Route</th>
                <th className="p-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {shipments.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-4 text-muted-foreground">
                    No shipments yet.
                  </td>
                </tr>
              ) : (
                shipments.map((s) => (
                  <tr key={s.id} className="border-t">
                    <td className="p-3 font-medium">{s.shipment_code.slice(0, 10)}</td>
                    <td className="p-3">{s.truck_name}</td>
                    <td className="p-3">{s.status}</td>
                    <td className="p-3 text-muted-foreground">
                      {s.origin_lat.toFixed(2)},{s.origin_lng.toFixed(2)} → {s.destination_lat.toFixed(2)},{s.destination_lng.toFixed(2)}
                    </td>
                    <td className="p-3 text-right">
                      <div className="inline-flex gap-2">
                        <Button variant="outline" asChild>
                          <Link to={`/shipments/${s.id}`}>Open</Link>
                        </Button>
                        <Button variant="destructive" onClick={() => void onDelete(s.id)}>
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

