import * as React from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useNavigate } from "react-router-dom";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type LatLng = { lat: number; lng: number };
type Polyline = number[][];

export default function ShipmentCreatePage() {
  const navigate = useNavigate();
  const mapEl = React.useRef<HTMLDivElement | null>(null);
  const mapRef = React.useRef<maplibregl.Map | null>(null);
  const originMarkerRef = React.useRef<maplibregl.Marker | null>(null);
  const destinationMarkerRef = React.useRef<maplibregl.Marker | null>(null);
  const originRef = React.useRef<LatLng | null>(null);
  const destinationRef = React.useRef<LatLng | null>(null);
  const routePreviewRequestIdRef = React.useRef(0);
  const routeLinePendingRef = React.useRef<Polyline | null>(null);

  const [origin, setOrigin] = React.useState<LatLng | null>(null);
  const [destination, setDestination] = React.useState<LatLng | null>(null);
  const [truckName, setTruckName] = React.useState("Truck-1");
  const [styleReady, setStyleReady] = React.useState(false);

  const [routePreview, setRoutePreview] = React.useState<null | {
    polyline: Polyline;
    distance_km: number;
    eta_minutes: number;
  }>(null);
  const [loadingPreview, setLoadingPreview] = React.useState(false);
  const [loadingSave, setLoadingSave] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  function updateRouteLine(polyline: Polyline) {
    const map = mapRef.current;
    if (!map) return;
    if (!map.isStyleLoaded()) {
      // Map style loads async; ensure we draw after it is ready.
      routeLinePendingRef.current = polyline;
      map.once("load", () => {
        const pending = routeLinePendingRef.current;
        routeLinePendingRef.current = null;
        if (pending) updateRouteLine(pending);
      });
      return;
    }

    const coordsLngLat = polyline.map(([lat, lng]: [number, number]) => [lng, lat]);
    const geojson = {
      type: "Feature",
      geometry: { type: "LineString", coordinates: coordsLngLat },
      properties: {},
    } as const;

    const sourceId = "route-source";
    const layerId = "route-line";

    const existing = map.getSource(sourceId);
    if (existing) {
      (existing as maplibregl.GeoJSONSource).setData(geojson);
      return;
    }

    map.addSource(sourceId, { type: "geojson", data: geojson });
    map.addLayer({
      id: layerId,
      type: "line",
      source: sourceId,
      paint: {
        "line-color": "#2563eb",
        "line-width": 4,
        "line-opacity": 0.85,
      },
    });
  }

  function clearRouteLine() {
    const map = mapRef.current;
    if (!map) return;
    const sourceId = "route-source";
    const layerId = "route-line";
    if (map.getLayer(layerId)) map.removeLayer(layerId);
    if (map.getSource(sourceId)) map.removeSource(sourceId);
  }

  React.useEffect(() => {
    originRef.current = origin;
    destinationRef.current = destination;
  }, [origin, destination]);

  React.useEffect(() => {
    if (!mapEl.current) return;
    const map = new maplibregl.Map({
      container: mapEl.current,
      // Street-map basemap with roads + labels (not terrain/green demo styling).
      style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
      center: [-73.0, 41.0],
      zoom: 7,
    });
    mapRef.current = map;

    map.on("load", () => {
      setStyleReady(true);
      // If a route polyline finished loading while style wasn't ready, draw it now.
      const pending = routeLinePendingRef.current;
      if (pending) {
        routeLinePendingRef.current = null;
        updateRouteLine(pending);
      }
    });

    map.on("click", (e) => {
      const clicked = { lat: e.lngLat.lat, lng: e.lngLat.lng };
      setError(null);

      const currentOrigin = originRef.current;
      const currentDestination = destinationRef.current;

      // Click flow:
      // - First click: set origin
      // - Second click: set destination
      // - Third click+: reset origin (so user can redo the pair)
      if (!currentOrigin || (currentOrigin && currentDestination)) {
        setOrigin(clicked);
        originRef.current = clicked;
        setDestination(null);
        destinationRef.current = null;
        setRoutePreview(null);
        clearRouteLine();

        originMarkerRef.current?.remove();
        originMarkerRef.current = new maplibregl.Marker({ color: "#22c55e" })
          .setLngLat([clicked.lng, clicked.lat])
          .addTo(map);

        destinationMarkerRef.current?.remove();
        destinationMarkerRef.current = null;
        return;
      }

      if (currentOrigin && !currentDestination) {
        setDestination(clicked);
        destinationRef.current = clicked;
        destinationMarkerRef.current?.remove();
        destinationMarkerRef.current = new maplibregl.Marker({ color: "#ef4444" })
          .setLngLat([clicked.lng, clicked.lat])
          .addTo(map);
      }
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    async function run() {
      if (!origin || !destination) return;
      // Ignore stale responses if user changes origin/destination mid-flight.
      const requestId = ++routePreviewRequestIdRef.current;
      setLoadingPreview(true);
      setError(null);
      try {
        const res = await api.post("/routes/generate", {
          origin_lat: origin.lat,
          origin_lng: origin.lng,
          destination_lat: destination.lat,
          destination_lng: destination.lng,
        });
        if (requestId !== routePreviewRequestIdRef.current) return;
        setRoutePreview(res.data);
        if (res.data?.polyline) updateRouteLine(res.data.polyline);
      } catch (e: any) {
        if (requestId !== routePreviewRequestIdRef.current) return;
        const detail = e?.response?.data?.detail;
        const message = typeof detail === "string" ? detail : e?.message;
        setError(message ?? "Route generation failed");
      } finally {
        if (requestId !== routePreviewRequestIdRef.current) return;
        setLoadingPreview(false);
      }
    }
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [origin, destination]);

  async function onSave() {
    if (!origin || !destination) return;
    setLoadingSave(true);
    setError(null);
    try {
      const res = await api.post("/routes/save", {
        origin_lat: origin.lat,
        origin_lng: origin.lng,
        destination_lat: destination.lat,
        destination_lng: destination.lng,
        truck_name: truckName,
      });
      const shipmentId: number = res.data.shipment_id;
      navigate(`/shipments/${shipmentId}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to save shipment");
    } finally {
      setLoadingSave(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr,360px]">
      <div className="rounded-lg border bg-card overflow-hidden">
        <div ref={mapEl} className="h-[520px] w-full" />
      </div>

      <div className="space-y-4">
        <div className="rounded-lg border bg-card p-4">
          <h2 className="text-lg font-semibold">Create Shipment</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Click the map to set origin (green) and destination (red), then preview and confirm the route.
          </p>

          <div className="mt-4 space-y-3">
            <div className="space-y-1">
              <label className="text-sm font-medium">Truck Name</label>
              <Input value={truckName} onChange={(e) => setTruckName(e.target.value)} />
            </div>

            <div className="space-y-1">
              <div className="text-sm font-medium">Route Preview</div>
              {loadingPreview ? (
                <div className="text-sm text-muted-foreground">Generating route...</div>
              ) : routePreview ? (
                <div className="text-sm text-muted-foreground">
                  Distance: {routePreview.distance_km.toFixed(1)} km
                  <br />
                  ETA: {routePreview.eta_minutes.toFixed(0)} minutes
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">Set origin and destination to preview.</div>
              )}
            </div>

            {error ? <div className="text-sm text-destructive">{error}</div> : null}

            <Button
              className="w-full"
              onClick={() => void onSave()}
              disabled={!origin || !destination || loadingSave || !routePreview}
            >
              {loadingSave ? "Saving..." : "Save Shipment"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

