import * as React from "react";
import { Link } from "react-router-dom";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

type Shipment = {
  id: number;
  shipment_code: string;
  status: string;
  truck_name: string;
};

export default function SimulationIndexPage() {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const active = shipments.filter((s) => s.status === "in_transit" || s.status === "rerouted");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Simulations</h1>
          <p className="text-sm text-muted-foreground">Active in-transit shipments with command centers.</p>
        </div>
        <Button variant="outline" onClick={() => void load()}>
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">Loading simulations...</div>
      ) : active.length === 0 ? (
        <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
          No active simulations right now.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/30 text-muted-foreground">
              <tr className="text-left">
                <th className="p-3 font-medium">Code</th>
                <th className="p-3 font-medium">Truck</th>
                <th className="p-3 font-medium">Status</th>
                <th className="p-3 font-medium text-right">Command Center</th>
              </tr>
            </thead>
            <tbody>
              {active.map((s) => (
                <tr key={s.id} className="border-t">
                  <td className="p-3 font-medium">{s.shipment_code.slice(0, 10)}</td>
                  <td className="p-3">{s.truck_name}</td>
                  <td className="p-3 text-muted-foreground">{s.status}</td>
                  <td className="p-3 text-right">
                    <Button variant="outline" asChild>
                      <Link to={`/simulation/${s.id}`}>Open</Link>
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

