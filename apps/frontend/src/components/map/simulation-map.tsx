import * as React from "react";
import maplibregl from "maplibre-gl";

type LatLng = { lat: number; lng: number };

type Warehouse = {
  id: number;
  name: string;
  lat: number;
  lng: number;
};

type Telemetry = {
  lat: number;
  lng: number;
  heading: number;
  speed?: number;
  weather_state?: string;
  risk_level?: number;
  timestamp?: string;
};

type Props = {
  origin: LatLng;
  destination: LatLng;
  defaultRoutePolyline?: number[][];
  currentRoutePolyline?: number[][];
  remainingPolyline?: number[][];
  proposedReroutePolyline?: number[][];
  warehouses?: Warehouse[];
  telemetry?: Telemetry | null;
};

// Keep in sync with backend `CONNECTICUT_BLIZZARD_ZONE` rectangle (approx).
const CONNECTICUT_BLIZZARD_ZONE: [number, number][] = [
  [41.0, -73.7],
  [41.0, -71.8],
  [42.1, -71.8],
  [42.1, -73.7],
  [41.0, -73.7],
];

function closestPointIndex(polyline: number[][], lat: number, lng: number) {
  let bestIdx = 0;
  let bestDist = Number.POSITIVE_INFINITY;
  for (let i = 0; i < polyline.length; i += 1) {
    const [pLat, pLng] = polyline[i];
    const dLat = pLat - lat;
    const dLng = pLng - lng;
    const dist = dLat * dLat + dLng * dLng;
    if (dist < bestDist) {
      bestDist = dist;
      bestIdx = i;
    }
  }
  return bestIdx;
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function lerpHeading(a: number, b: number, t: number) {
  // Shortest angular path.
  const delta = ((b - a + 540) % 360) - 180;
  return (a + delta * t + 360) % 360;
}

export default function SimulationMap({
  origin,
  destination,
  defaultRoutePolyline,
  currentRoutePolyline,
  remainingPolyline,
  proposedReroutePolyline,
  warehouses = [],
  telemetry,
}: Props) {
  const mapEl = React.useRef<HTMLDivElement | null>(null);
  const mapRef = React.useRef<maplibregl.Map | null>(null);
  const [styleReady, setStyleReady] = React.useState(false);

  const originMarkerRef = React.useRef<maplibregl.Marker | null>(null);
  const destinationMarkerRef = React.useRef<maplibregl.Marker | null>(null);
  const warehouseLayerAddedRef = React.useRef(false);

  const truckMarkerRef = React.useRef<maplibregl.Marker | null>(null);
  const truckElRef = React.useRef<HTMLDivElement | null>(null);
  const renderedRef = React.useRef<{ lat: number; lng: number; heading: number } | null>(null);
  const animRafRef = React.useRef<number | null>(null);

  function setRouteSource(sourceId: string, layerId: string, polyline: number[][] | undefined, color: string) {
    const map = mapRef.current;
    if (!map) return;
    if (!map.isStyleLoaded()) return;
    if (!polyline || polyline.length < 2) return;

    const coordsLngLat = polyline.map(([lat, lng]) => [lng, lat]);
    const geojson = {
      type: "Feature",
      geometry: { type: "LineString", coordinates: coordsLngLat },
      properties: {},
    } as const;

    if (map.getSource(sourceId)) {
      (map.getSource(sourceId) as maplibregl.GeoJSONSource).setData(geojson);
      return;
    }

    map.addSource(sourceId, { type: "geojson", data: geojson });
    map.addLayer({
      id: layerId,
      type: "line",
      source: sourceId,
      paint: {
        "line-color": color,
        "line-width": layerId === "current-route-line" ? 3 : 4,
        "line-opacity": layerId === "current-route-line" ? 0.75 : layerId === "proposed-reroute-line" ? 0.85 : 0.9,
        "line-dasharray":
          layerId === "current-route-line" ? [2, 2] : layerId === "proposed-reroute-line" ? [1, 1] : [1, 0],
      },
    });
  }

  function removeLayerIfExists(layerId: string) {
    const map = mapRef.current;
    if (!map) return;
    if (map.getLayer(layerId)) map.removeLayer(layerId);
  }

  function removeSourceIfExists(sourceId: string) {
    const map = mapRef.current;
    if (!map) return;
    if (map.getSource(sourceId)) map.removeSource(sourceId);
  }

  React.useEffect(() => {
    if (!mapEl.current) return;

    const map = new maplibregl.Map({
      container: mapEl.current,
      // Street-map basemap with roads + labels (not terrain/green demo styling).
      style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
      center: [origin.lng, origin.lat],
      zoom: 7,
    });

    mapRef.current = map;

    // Create truck marker element.
    const truckEl = document.createElement("div");
    truckEl.style.width = "22px";
    truckEl.style.height = "22px";
    truckEl.style.background = "#1d4ed8";
    truckEl.style.clipPath = "polygon(50% 0%, 0% 100%, 100% 100%)";
    truckEl.style.transformOrigin = "50% 60%";
    truckEl.style.boxShadow = "0 8px 20px rgba(0,0,0,0.25)";
    truckEl.className = "truck-marker";
    truckElRef.current = truckEl;

    const truckMarker = new maplibregl.Marker({ element: truckEl, draggable: false })
      .setLngLat([origin.lng, origin.lat])
      .addTo(map);
    truckMarkerRef.current = truckMarker;
    renderedRef.current = { lat: origin.lat, lng: origin.lng, heading: telemetry?.heading ?? 0 };

    // Markers
    originMarkerRef.current = new maplibregl.Marker({ color: "#22c55e" })
      .setLngLat([origin.lng, origin.lat])
      .addTo(map);
    destinationMarkerRef.current = new maplibregl.Marker({ color: "#ef4444" })
      .setLngLat([destination.lng, destination.lat])
      .addTo(map);

    map.on("load", () => {
      // Storm zone polygon overlay (toggle based on telemetry in a later effect).
      const polygon: any = {
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [
            CONNECTICUT_BLIZZARD_ZONE.map(([lat, lng]) => [lng, lat]),
          ],
        },
      };

      if (!map.getSource("blizzard-zone")) {
        map.addSource("blizzard-zone", { type: "geojson", data: polygon });
      }
      if (!map.getLayer("blizzard-zone-fill")) {
        map.addLayer({
          id: "blizzard-zone-fill",
          type: "fill",
          source: "blizzard-zone",
          paint: {
            "fill-color": "rgba(147, 197, 253, 0.25)",
            "fill-outline-color": "rgba(59, 130, 246, 0.6)",
          },
        });
      }

      setStyleReady(true);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      if (animRafRef.current) cancelAnimationFrame(animRafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    // Update marker positions when origin/destination changes.
    originMarkerRef.current?.setLngLat([origin.lng, origin.lat]);
    destinationMarkerRef.current?.setLngLat([destination.lng, destination.lat]);
  }, [origin, destination]);

  React.useEffect(() => {
    // Update routes.
    if (!mapRef.current) return;
    if (!styleReady) return;
    setRouteSource("default-route-source", "default-route-line", defaultRoutePolyline, "#2563eb");
    setRouteSource("current-route-source", "current-route-line", currentRoutePolyline, "#7c3aed");
    setRouteSource("remaining-route-source", "remaining-route-line", remainingPolyline, "#f97316");
    setRouteSource("proposed-reroute-source", "proposed-reroute-line", proposedReroutePolyline, "#e11d48");
  }, [styleReady, defaultRoutePolyline, currentRoutePolyline, remainingPolyline, proposedReroutePolyline]);

  React.useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    // Toggle storm polygon visibility based on telemetry weather state.
    if (map.getLayer("blizzard-zone-fill")) {
      const inStorm = telemetry?.weather_state === "blizzard";
      map.setLayoutProperty("blizzard-zone-fill", "visibility", inStorm ? "visible" : "none");
    }
  }, [telemetry?.weather_state]);

  React.useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!styleReady) return;
    if (warehouseLayerAddedRef.current) return;
    if (!warehouses.length) return;

    const features = warehouses.map((w) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [w.lng, w.lat] },
      properties: { id: w.id, name: w.name },
    }));

    const geojson = { type: "FeatureCollection", features } as const;
    map.addSource("warehouses", { type: "geojson", data: geojson });
    map.addLayer({
      id: "warehouses-layer",
      type: "circle",
      source: "warehouses",
      paint: {
        "circle-radius": 5,
        "circle-color": "#16a34a",
        "circle-opacity": 0.75,
        "circle-stroke-color": "#0f766e",
        "circle-stroke-width": 2,
      },
    });
    warehouseLayerAddedRef.current = true;
  }, [styleReady, warehouses]);

  React.useEffect(() => {
    if (!telemetry || !truckMarkerRef.current || !truckElRef.current) return;
    const targetLat = telemetry.lat;
    const targetLng = telemetry.lng;
    // Prevent "random jumps" if websocket payload is temporarily incomplete.
    if (!Number.isFinite(targetLat) || !Number.isFinite(targetLng)) return;
    const targetHeading = Number.isFinite(telemetry.heading) ? telemetry.heading : 0;
    const from = renderedRef.current ?? { lat: targetLat, lng: targetLng, heading: targetHeading };
    if (!Number.isFinite(from.lat) || !Number.isFinite(from.lng)) return;
    const fromHeading = Number.isFinite(from.heading) ? from.heading : targetHeading;

    const durationMs = 1200; // Smooth, short tween between telemetry ticks.
    const start = performance.now();

    if (animRafRef.current) cancelAnimationFrame(animRafRef.current);

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const lat = lerp(from.lat, targetLat, t);
      const lng = lerp(from.lng, targetLng, t);
      const heading = lerpHeading(fromHeading, targetHeading, t);

      truckMarkerRef.current?.setLngLat([lng, lat]);
      truckElRef.current!.style.transform = `rotate(${heading}deg)`;
      renderedRef.current = { lat, lng, heading };

      if (t < 1) {
        animRafRef.current = requestAnimationFrame(tick);
      }
    };

    animRafRef.current = requestAnimationFrame(tick);
  }, [telemetry?.lat, telemetry?.lng, telemetry?.heading]);

  // Keep the "remaining route" highlight aligned with current telemetry position.
  React.useEffect(() => {
    if (!styleReady) return;
    if (!telemetry) return;
    if (!mapRef.current) return;
    const routeForRemaining = remainingPolyline ?? defaultRoutePolyline;
    if (!routeForRemaining || routeForRemaining.length < 2) return;

    const idx = closestPointIndex(routeForRemaining, telemetry.lat, telemetry.lng);
    const sliced = routeForRemaining.slice(idx);
    if (sliced.length < 2) return;
    sliced[0] = [telemetry.lat, telemetry.lng];
    setRouteSource("remaining-route-source", "remaining-route-line", sliced, "#f97316");
  }, [telemetry?.lat, telemetry?.lng, remainingPolyline, defaultRoutePolyline, styleReady]);

  return <div ref={mapEl} className="w-full h-[560px]" />;
}

