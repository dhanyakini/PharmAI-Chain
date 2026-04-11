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

/** Project (lat,lng) onto the polyline for stable on-road marker placement. */
function closestPointOnPolyline(polyline: number[][], lat: number, lng: number): [number, number] {
  if (polyline.length === 0) return [lat, lng];
  if (polyline.length === 1) return [polyline[0][0], polyline[0][1]];

  let bestLat = polyline[0][0];
  let bestLng = polyline[0][1];
  let best = Number.POSITIVE_INFINITY;

  for (let i = 0; i < polyline.length - 1; i += 1) {
    const la0 = polyline[i][0];
    const ln0 = polyline[i][1];
    const la1 = polyline[i + 1][0];
    const ln1 = polyline[i + 1][1];
    const dLat = la1 - la0;
    const dLng = ln1 - ln0;
    const len2 = dLat * dLat + dLng * dLng;
    if (len2 < 1e-18) continue;
    let t = ((lat - la0) * dLat + (lng - ln0) * dLng) / len2;
    t = Math.max(0, Math.min(1, t));
    const pl = la0 + t * dLat;
    const pLng = ln0 + t * dLng;
    const dist = (pl - lat) * (pl - lat) + (pLng - lng) * (pLng - lng);
    if (dist < best) {
      best = dist;
      bestLat = pl;
      bestLng = pLng;
    }
  }
  return [bestLat, bestLng];
}

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
  const truckMarkerRef = React.useRef<maplibregl.Marker | null>(null);
  /** Inner triangle only — MapLibre must own `transform` on the marker root for pan/zoom. */
  const truckRotateElRef = React.useRef<HTMLDivElement | null>(null);
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

    // Root: MapLibre sets translate/scale on this for geographic anchoring — do not set transform on it.
    const truckRoot = document.createElement("div");
    truckRoot.style.width = "28px";
    truckRoot.style.height = "28px";
    truckRoot.style.display = "flex";
    truckRoot.style.alignItems = "center";
    truckRoot.style.justifyContent = "center";
    truckRoot.style.pointerEvents = "none";

    const truckInner = document.createElement("div");
    truckInner.style.width = "22px";
    truckInner.style.height = "22px";
    truckInner.style.background = "#1d4ed8";
    truckInner.style.clipPath = "polygon(50% 0%, 0% 100%, 100% 100%)";
    truckInner.style.transformOrigin = "50% 60%";
    truckInner.style.boxShadow = "0 8px 20px rgba(0,0,0,0.25)";
    truckInner.className = "truck-marker-inner";
    truckRoot.appendChild(truckInner);
    truckRotateElRef.current = truckInner;

    const truckMarker = new maplibregl.Marker({ element: truckRoot, anchor: "center", draggable: false })
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
    if (!styleReady) return;
    if (!warehouses.length) return;

    const features = warehouses.map((w) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [w.lng, w.lat] },
      properties: { id: w.id, name: w.name },
    }));

    const geojson = { type: "FeatureCollection", features } as const;

    const existing = map.getSource("warehouses") as maplibregl.GeoJSONSource | undefined;
    if (existing) {
      existing.setData(geojson);
      return;
    }

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
  }, [styleReady, warehouses]);

  React.useEffect(() => {
    if (!telemetry || !truckMarkerRef.current || !truckRotateElRef.current) return;
    let targetLat = telemetry.lat;
    let targetLng = telemetry.lng;
    // Prevent "random jumps" if websocket payload is temporarily incomplete.
    if (!Number.isFinite(targetLat) || !Number.isFinite(targetLng)) return;

    const routeForSnap =
      remainingPolyline && remainingPolyline.length >= 2
        ? remainingPolyline
        : currentRoutePolyline && currentRoutePolyline.length >= 2
          ? currentRoutePolyline
          : defaultRoutePolyline && defaultRoutePolyline.length >= 2
            ? defaultRoutePolyline
            : null;
    if (routeForSnap) {
      const [sl, sg] = closestPointOnPolyline(routeForSnap, targetLat, targetLng);
      targetLat = sl;
      targetLng = sg;
    }
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
      truckRotateElRef.current!.style.transform = `rotate(${heading}deg)`;
      renderedRef.current = { lat, lng, heading };

      if (t < 1) {
        animRafRef.current = requestAnimationFrame(tick);
      }
    };

    animRafRef.current = requestAnimationFrame(tick);
  }, [
    telemetry?.lat,
    telemetry?.lng,
    telemetry?.heading,
    remainingPolyline,
    currentRoutePolyline,
    defaultRoutePolyline,
  ]);

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

