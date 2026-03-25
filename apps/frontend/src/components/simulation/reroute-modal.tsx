import * as React from "react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export default function RerouteModal({
  open,
  shipmentId,
  suggestion,
  onClose,
  onApplied,
  onRejected,
}: {
  open: boolean;
  shipmentId: number;
  suggestion: any | null;
  onClose: () => void;
  onApplied: () => void;
  onRejected: () => void;
}) {
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function onConfirm() {
    if (!suggestion) return;
    setError(null);
    setSubmitting(true);
    try {
      await api.post(`/simulation/confirm-reroute/${shipmentId}`);
      onApplied();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to apply reroute");
    } finally {
      setSubmitting(false);
    }
  }

  async function onReject() {
    setError(null);
    setSubmitting(true);
    try {
      await api.post(`/simulation/reject-reroute/${shipmentId}`);
      onRejected();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to reject reroute");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => (v ? null : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reroute Suggested</DialogTitle>
          <DialogDescription>
            A logistics supervisor detected cold-chain risk and proposes a mid-route reroute. Confirm to apply; reject to
            wait for recovery.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 text-sm">
          {suggestion?.warehouse_candidate ? (
            <div>
              <div className="text-muted-foreground">Cold-Storage Warehouse</div>
              <div className="font-medium">{suggestion.warehouse_candidate.name}</div>
              <div className="text-xs text-muted-foreground">
                {suggestion.warehouse_candidate.lat.toFixed(3)}, {suggestion.warehouse_candidate.lng.toFixed(3)}
              </div>
            </div>
          ) : (
            <div className="text-muted-foreground">No specific warehouse candidate was selected.</div>
          )}

          {typeof suggestion?.confidence_score === "number" ? (
            <div className="text-muted-foreground">Confidence: {(suggestion.confidence_score * 100).toFixed(0)}%</div>
          ) : null}
          {typeof suggestion?.proposed_distance_km === "number" ? (
            <div className="text-muted-foreground">Proposed distance: {suggestion.proposed_distance_km.toFixed(2)} km</div>
          ) : null}
          {typeof suggestion?.proposed_eta_minutes === "number" ? (
            <div className="text-muted-foreground">Proposed ETA: {suggestion.proposed_eta_minutes.toFixed(1)} min</div>
          ) : null}

          {typeof suggestion?.reasoning_trace === "string" ? (
            <div>
              <div className="text-muted-foreground">Reasoning</div>
              <div className="whitespace-pre-wrap text-foreground/90">{suggestion.reasoning_trace}</div>
            </div>
          ) : null}
          {error ? <div className="text-sm text-destructive">{error}</div> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => void onReject()} disabled={submitting}>
            Reject
          </Button>
          <Button onClick={() => void onConfirm()} disabled={submitting || !suggestion}>
            {submitting ? "Applying..." : "Confirm"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

