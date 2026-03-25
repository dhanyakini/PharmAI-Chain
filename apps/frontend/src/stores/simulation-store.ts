import * as React from "react";
import { create } from "zustand";

import { connectDashboardWs, type DashboardWsEnvelope, type WsStatus } from "@/lib/ws";

type Telemetry = {
  lat: number;
  lng: number;
  heading: number;
  speed?: number;
  weather_state?: string;
  risk_level?: number;
  route_segment?: string;
  segment_idx?: number;
  segment_progress_km?: number;
  remaining_distance_km?: number;
  route_total_km?: number;
  progress_pct?: number;
  internal_temp?: number;
  external_temp?: number;
  timestamp?: string;
};

export type LifecycleEntry = {
  timestamp: string | null;
  event_name: string;
  agent_role: string | null;
  description: string | null;
  payload?: any;
};

export type ActivityEntry =
  | ({
      kind: "telemetry";
      timestamp: string | null;
      event_name: "telemetry_tick";
      route_segment?: string;
      lat: number;
      lng: number;
      internal_temp?: number;
      external_temp?: number;
      weather_state?: string;
      risk_level?: number;
      heading?: number;
      speed?: number;
      payload?: any;
    })
  | ({
      kind: "lifecycle";
      timestamp: string | null;
      event_name: string;
      agent_role: string | null;
      description: string | null;
      payload?: any;
    });

type SimulationStoreState = {
  shipmentId: number | null;
  wsStatus: WsStatus;

  telemetry: Telemetry | null;
  lifecycleEvents: LifecycleEntry[];
  activitySteps: ActivityEntry[];
  rerouteSuggestion: any | null;

  connect: (shipmentId: number) => void;
  disconnect: () => void;
  setInitialTimeline: (events: LifecycleEntry[]) => void;
  setInitialTelemetry: (telemetry: Telemetry | null) => void;
  setRerouteSuggestion: (suggestion: any | null) => void;
  dismissRerouteSuggestion: () => void;
};

let disconnectWs: null | (() => void) = null;

function eventToTimelineEntry(envelope: DashboardWsEnvelope): LifecycleEntry | null {
  if (envelope.type !== "lifecycle_event") return null;
  const rawPayload = envelope.payload ?? {};
  const payload =
    typeof rawPayload === "object" && rawPayload !== null ? rawPayload : {};
  const eventName = payload.event_name;
  if (!eventName) return null;

  const agent_role =
    eventName === "environment_agent_called"
      ? "environment_agent"
      : eventName === "dispatcher_agent_called"
        ? "dispatcher_agent"
        : eventName === "supervisor_decision_selected"
          ? "supervisor_agent"
          : eventName === "reroute_suggested" || eventName === "reroute_confirmed" || eventName === "reroute_applied"
            ? "supervisor_agent"
          : null;

  let description: string | null = null;

  if (eventName === "simulation_started") {
    description = "Simulation started from origin; truck begins moving.";
  } else if (eventName === "entered_blizzard_zone") {
    description = typeof payload.weather_state === "string" ? `Entered blizzard zone.` : "Entered blizzard zone.";
  } else if (eventName === "environment_agent_called") {
    const internal = typeof payload.internal_temp_f === "number" ? `Internal temp: ${payload.internal_temp_f}F` : null;
    const weather = typeof payload.weather_state === "string" ? `Weather: ${payload.weather_state}` : null;
    description = [internal, weather].filter(Boolean).join(" · ");
  } else if (eventName === "temperature_threshold_crossed") {
    description =
      typeof payload.internal_temp_f === "number"
        ? `Temperature threshold crossed. Internal temp: ${payload.internal_temp_f}F`
        : "Temperature threshold crossed.";
  } else if (eventName === "temperature_recovered") {
    description =
      typeof payload.internal_temp_f === "number"
        ? `Temperature recovered. Internal temp: ${payload.internal_temp_f}F`
        : "Temperature recovered.";
  } else if (eventName === "dispatcher_agent_called") {
    description = "Dispatcher agent searching cold-storage warehouse candidates.";
  } else if (eventName === "supervisor_decision_selected") {
    const confidence =
      typeof payload.confidence_score === "number" ? `Confidence ${(payload.confidence_score * 100).toFixed(0)}%` : null;
    const suggested = payload.reroute_suggested ? "Reroute suggested." : "Reroute not recommended.";
    description = [suggested, confidence].filter(Boolean).join(" · ");
  } else if (eventName === "reroute_suggested") {
    const warehouseName = payload?.warehouse_candidate?.name ? String(payload.warehouse_candidate.name) : null;
    const confidence =
      typeof payload.confidence_score === "number" ? `Confidence ${(payload.confidence_score * 100).toFixed(0)}%` : null;
    description = [warehouseName ? `Suggested warehouse: ${warehouseName}` : null, confidence].filter(Boolean).join(" · ");
    if (typeof payload.reasoning_trace === "string" && payload.reasoning_trace) {
      description = `${description}${description ? " · " : ""}${payload.reasoning_trace}`;
    }
  } else if (eventName === "reroute_confirmed") {
    const warehouseName = payload?.warehouse_candidate?.name ? String(payload.warehouse_candidate.name) : null;
    description = warehouseName ? `Reroute confirmed by user. Warehouse: ${warehouseName}` : "Reroute confirmed by user.";
  } else if (eventName === "reroute_applied") {
    description = "Reroute applied. Truck will continue on the updated remaining path.";
  } else if (eventName === "simulation_paused_for_reroute") {
    description = "Simulation paused. Blizzard detected — waiting for user reroute decision.";
  } else if (eventName === "reroute_rejected") {
    description = "Reroute rejected by user.";
  } else if (eventName === "simulation_resumed") {
    description = "Simulation resumed after user decision.";
  } else if (eventName === "shipment_delivered") {
    description = "Shipment delivered successfully (temperature never violated).";
  } else if (eventName === "shipment_compromised") {
    description = "Shipment compromised (temperature violated before arrival).";
  } else if (eventName === "shipment_deleted") {
    description = "Shipment deleted from system.";
  } else {
    // Generic fallback for agent calls and remaining payloads.
    if (typeof payload.reasoning_trace === "string") description = payload.reasoning_trace;
    else if (typeof payload.internal_temp_f === "number") description = `Internal temperature: ${payload.internal_temp_f}F`;
    else if (typeof payload.weather_state === "string") description = `Weather state: ${payload.weather_state}`;
  }

  return {
    timestamp: envelope.timestamp ?? null,
    event_name: eventName,
    agent_role,
    description,
    payload,
  };
}

export const useSimulationStore = create<SimulationStoreState>((set, get) => ({
  shipmentId: null,
  wsStatus: "disconnected",
  telemetry: null,
  lifecycleEvents: [],
  activitySteps: [],
  rerouteSuggestion: null,

  connect: (shipmentId) => {
    // Avoid reconnect storms for the same shipment.
    if (get().shipmentId === shipmentId && get().wsStatus === "connected") return;

    set({
      shipmentId,
      wsStatus: "connecting",
      rerouteSuggestion: null,
    });

    disconnectWs?.();
    disconnectWs = null;

    const url = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws/dashboard";
    disconnectWs = connectDashboardWs({
      url,
      onStatus: (s) => set({ wsStatus: s }),
      onMessage: (envelope) => {
        const currentShipmentId = get().shipmentId;
        if (!currentShipmentId) return;
        if (envelope.shipment_id !== currentShipmentId) return;

        if (envelope.type === "telemetry") {
          const p = envelope.payload ?? {};
          set({
            telemetry: {
              lat: p.lat,
              lng: p.lng,
              heading: p.heading,
              speed: p.speed,
              weather_state: p.weather_state,
              risk_level: p.risk_level,
              route_segment: p.route_segment,
              segment_idx: p.segment_idx,
              segment_progress_km: p.segment_progress_km,
              remaining_distance_km: p.remaining_distance_km,
              route_total_km: p.route_total_km,
              progress_pct: p.progress_pct,
              internal_temp: p.internal_temp,
              external_temp: p.external_temp,
              timestamp: envelope.timestamp,
            },
          });

          const activity: ActivityEntry = {
            kind: "telemetry",
            timestamp: envelope.timestamp ?? null,
            event_name: "telemetry_tick",
            route_segment: p.route_segment,
            lat: p.lat,
            lng: p.lng,
            internal_temp: p.internal_temp,
            external_temp: p.external_temp,
            weather_state: p.weather_state,
            risk_level: p.risk_level,
            heading: p.heading,
            speed: p.speed,
            payload: p,
          };

          set((state) => ({
            activitySteps: [...state.activitySteps, activity].slice(-400),
          }));
          return;
        }

        if (envelope.type === "lifecycle_event") {
          const entry = eventToTimelineEntry(envelope);
          if (entry) {
            const eventName = entry.event_name;
            if (eventName === "simulation_started") {
              set({
                lifecycleEvents: [entry],
                activitySteps: [
                  {
                    kind: "lifecycle",
                    timestamp: entry.timestamp,
                    event_name: entry.event_name,
                    agent_role: entry.agent_role,
                    description: entry.description,
                    payload: entry.payload,
                  },
                ],
                rerouteSuggestion: null,
              });
            } else {
              set((state) => ({
                lifecycleEvents: [...state.lifecycleEvents, entry].slice(-300),
                activitySteps: [
                  ...state.activitySteps,
                  {
                    kind: "lifecycle",
                    timestamp: entry.timestamp,
                    event_name: entry.event_name,
                    agent_role: entry.agent_role,
                    description: entry.description,
                    payload: entry.payload,
                  },
                ].slice(-400),
              }));
            }
          }

          const eventName = envelope.payload?.event_name;
          if (eventName === "reroute_suggested") {
            set({ rerouteSuggestion: envelope.payload });
          }
          if (eventName === "reroute_applied") {
            set({ rerouteSuggestion: null });
          }
        }
      },
    });
  },

  disconnect: () => {
    disconnectWs?.();
    disconnectWs = null;
    set({ wsStatus: "disconnected" });
  },

  setInitialTimeline: (events) => {
    set({
      lifecycleEvents: events,
      activitySteps: events.map((e) => ({
        kind: "lifecycle",
        timestamp: e.timestamp,
        event_name: e.event_name,
        agent_role: e.agent_role,
        description: e.description,
        payload: e.payload,
      })),
    });
  },

  setInitialTelemetry: (telemetry) => {
    set({ telemetry });
  },

  setRerouteSuggestion: (suggestion) => {
    set({ rerouteSuggestion: suggestion });
  },

  dismissRerouteSuggestion: () => {
    set({ rerouteSuggestion: null });
  },
}));

