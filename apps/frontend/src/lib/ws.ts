export type DashboardWsEnvelope = {
  type: "telemetry" | "agent_action" | "status" | "error" | "ping" | "lifecycle_event";
  shipment_id: number;
  timestamp: string;
  payload: any;
};

export type WsStatus = "connecting" | "connected" | "disconnected";

export function connectDashboardWs({
  url,
  onMessage,
  onStatus,
}: {
  url: string;
  onMessage: (msg: DashboardWsEnvelope) => void;
  onStatus?: (s: WsStatus) => void;
}) {
  let ws: WebSocket | null = null;
  let closed = false;
  let retry = 0;

  const connectOnce = () => {
    if (closed) return;
    onStatus?.("connecting");

    ws = new WebSocket(url);

    ws.onopen = () => {
      retry = 0;
      onStatus?.("connected");
    };

    ws.onmessage = (ev) => {
      const raw = ev.data;
      if (typeof raw !== "string") return;
      try {
        const parsed = JSON.parse(raw);
        onMessage(parsed as DashboardWsEnvelope);
      } catch {
        // Ignore parse errors.
      }
    };

    ws.onclose = () => {
      onStatus?.("disconnected");
      if (closed) return;
      retry += 1;
      const delay = Math.min(30000, 1000 * Math.pow(2, retry));
      window.setTimeout(connectOnce, delay);
    };

    ws.onerror = () => {
      // Let onclose drive reconnection.
    };
  };

  connectOnce();

  return () => {
    closed = true;
    ws?.close();
  };
}

