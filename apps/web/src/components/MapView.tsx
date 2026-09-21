"use client";

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { Map as MaplibreMap, LngLatBoundsLike, GeoJSONSource, Marker, MapMouseEvent, NavigationControl, setWorkerUrl } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { ScatterplotLayer, ArcLayer, ColumnLayer, PathLayer, IconLayer, TextLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { useStore, type BasemapId } from "@/store/useStore";
import { getMassingManifest, getMassingCell, getPois, type MassingManifest, type PoiFeature } from "@/lib/api-client";
import { MASSING_TILE_URL } from "@/lib/api-client";
import { filterAndSortRestrictions, resolveMapSelection, isUsableGeoJson } from "@/lib/domain";
import type { GeoJSONGeometry, WalkEvent } from "@/lib/types";

if (typeof window !== "undefined") {
  // Turbopack rewrites import.meta.url so MapLibre's default worker URL
  // resolves to an empty string and the worker loads the HTML page instead
  // of its script, leaving vector tile requests pending forever. Serve the
  // worker + shared chunk from /public and point MapLibre at them.
  setWorkerUrl("/maplibre-gl-worker.mjs");
}

const EVIDENCE_RGB: Record<string, [number, number, number]> = {
  HIGH: [8, 127, 140],
  MEDIUM: [181, 71, 8],
  LOW: [127, 86, 217],
  INSUFFICIENT_EVIDENCE: [102, 112, 133],
  NOT_EVALUATED: [152, 162, 179],
};

const TORONTO_CENTER: [number, number] = [-79.3832, 43.6532];
const TORONTO_ZOOM = 11;

const VECTOR_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";

const AERIAL_STYLE = {
  version: 8 as const,
  sources: {
    "esri-imagery": {
      type: "raster" as const,
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Esri, Maxar, Earthstar Geographics",
    },
    "esri-labels": {
      type: "raster" as const,
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Esri",
    },
  },
  layers: [
    { id: "esri-imagery-layer", type: "raster" as const, source: "esri-imagery" },
    { id: "esri-labels-layer", type: "raster" as const, source: "esri-labels" },
  ],
};

const BASE_STYLES: Record<BasemapId, string | object> = {
  streets: VECTOR_STYLE_URL,
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
  aerial: AERIAL_STYLE,
};

const MASSING_LAYER_MINZOOM = 13.5;

const RASTER_FALLBACK_STYLE = {
  version: 8 as const,
  sources: {
    "osm-raster": {
      type: "raster" as const,
      tiles: [
        "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution:
        "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors",
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: "osm-layer",
      type: "raster" as const,
      source: "osm-raster",
      minzoom: 0,
      maxzoom: 19,
    },
  ],
};

interface PointItem {
  restriction_id: string;
  coordinates: [number, number];
  evidence_confidence: string;
  impact_severity: string;
  candidate_edge_count: number;
  duration_hours?: number | null;
  match_type?: string | null;
  location?: {
    road: string | null;
    name: string | null;
    from_road: string | null;
    to_road: string | null;
  } | null;
}

// Icon shape encodes how long the restriction lasts: teardrop pin with a
// unique interior glyph — clock = short-term, wrench = long-term (>= 30 days),
// question mark = unknown duration. The pin body is dark so the white interior
// icon is legible at every zoom level.
type DurationClass = "short" | "long" | "unknown";

function durationClass(hours: number | null | undefined): DurationClass {
  if (hours == null) return "unknown";
  return hours >= 720 ? "long" : "short";
}

function humanizeDuration(hours: number | null | undefined): string {
  if (hours == null) return "duration unknown";
  if (hours < 48) return `~${Math.max(1, Math.round(hours))}h restriction`;
  const days = hours / 24;
  if (days < 45) return `~${Math.round(days)}d restriction`;
  const months = days / 30.44;
  if (months < 18) return `~${Math.round(months)}mo restriction`;
  return `~${(months / 12).toFixed(1)}yr restriction`;
}

const DURATION_ICON_URLS: Record<DurationClass, string> = {
  // Short-term: dark teal pin with clock icon
  short: `data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='80'><path d='M32 0 C14 0 0 14 0 30 C0 46 32 80 32 80 C32 80 64 46 64 30 C64 14 50 0 32 0Z' fill='#0a4a52'/><circle cx='32' cy='28' r='11' fill='none' stroke='#fff' stroke-width='2.5'/><line x1='32' y1='21' x2='32' y2='28' stroke='#fff' stroke-width='2' stroke-linecap='round'/><line x1='32' y1='28' x2='37' y2='32' stroke='#fff' stroke-width='2' stroke-linecap='round'/></svg>`,
  )}`,
  // Long-term: dark red pin with wrench icon
  long: `data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='80'><path d='M32 0 C14 0 0 14 0 30 C0 46 32 80 32 80 C32 80 64 46 64 30 C64 14 50 0 32 0Z' fill='#7a1a1a'/><g transform='translate(32,26) rotate(-45)'><rect x='-10' y='-3' width='14' height='6' rx='1.5' fill='#fff'/><rect x='4' y='-7' width='6' height='14' rx='1.5' fill='#fff'/><circle cx='0' cy='0' r='4.5' fill='none' stroke='#fff' stroke-width='2'/></g></svg>`,
  )}`,
  // Unknown duration: dark gray pin with question-mark icon
  unknown: `data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='80'><path d='M32 0 C14 0 0 14 0 30 C0 46 32 80 32 80 C32 80 64 46 64 30 C64 14 50 0 32 0Z' fill='#3d4555'/><text x='32' y='34' text-anchor='middle' font-family='Georgia,serif' font-size='26' font-weight='bold' fill='#fff'>?</text></svg>`,
  )}`,
};

// Walk-service POI layers: real City of Toronto datasets (see
// scripts/build_poi_layers.py for sources). Icons are white mask SVGs colored
// per kind so one glyph set serves every category.
const POI_KIND_STYLES: Record<string, { color: [number, number, number]; icon: string; label: string }> = {
  bench: {
    color: [180, 83, 9],
    label: "Bench",
    icon: `data:image/svg+xml;utf8,${encodeURIComponent(
      `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect x='8' y='24' width='48' height='9' rx='3' fill='#fff'/><rect x='8' y='39' width='48' height='9' rx='3' fill='#fff'/><rect x='12' y='48' width='7' height='12' fill='#fff'/><rect x='45' y='48' width='7' height='12' fill='#fff'/></svg>`,
    )}`,
  },
  washroom: {
    color: [9, 146, 104],
    label: "Washroom",
    icon: `data:image/svg+xml;utf8,${encodeURIComponent(
      `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><circle cx='32' cy='15' r='9' fill='#fff'/><path d='M20 62 L20 48 Q20 33 32 33 Q44 33 44 48 L44 62 L36 62 L36 45 L28 45 L28 62 Z' fill='#fff'/></svg>`,
    )}`,
  },
  cooling: {
    color: [70, 130, 230],
    label: "Cool space",
    icon: `data:image/svg+xml;utf8,${encodeURIComponent(
      `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><g stroke='#fff' stroke-width='6' stroke-linecap='round'><line x1='32' y1='7' x2='32' y2='57'/><line x1='10' y1='19' x2='54' y2='45'/><line x1='54' y1='19' x2='10' y2='45'/></g></svg>`,
    )}`,
  },
  library: {
    color: [110, 68, 190],
    label: "Library",
    icon: `data:image/svg+xml;utf8,${encodeURIComponent(
      `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><path d='M8 16 Q19 9 30 15 L30 52 Q19 46 8 52 Z' fill='#fff'/><path d='M56 16 Q45 9 34 15 L34 52 Q45 46 56 52 Z' fill='#fff'/></svg>`,
    )}`,
  },
  community: {
    color: [190, 68, 160],
    label: "Community centre",
    icon: `data:image/svg+xml;utf8,${encodeURIComponent(
      `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><circle cx='21' cy='17' r='8' fill='#fff'/><circle cx='44' cy='17' r='8' fill='#fff'/><path d='M11 58 L11 47 Q11 33 21 33 Q31 33 31 47 L31 58 Z' fill='#fff'/><path d='M34 58 L34 47 Q34 33 44 33 Q54 33 54 47 L54 58 Z' fill='#fff'/></svg>`,
    )}`,
  },
  transit: {
    color: [23, 105, 170],
    label: "TTC stop",
    icon: `data:image/svg+xml;utf8,${encodeURIComponent(
      `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect x='13' y='8' width='38' height='42' rx='8' fill='#fff'/><rect x='19' y='15' width='11' height='11' rx='2' fill='#000'/><rect x='34' y='15' width='11' height='11' rx='2' fill='#000'/><circle cx='22' cy='56' r='5' fill='#fff'/><circle cx='42' cy='56' r='5' fill='#fff'/></svg>`,
    )}`,
  },
};

const POI_ROUTE_PROXIMITY_M = 150;

interface EvidenceMatchLike {
  pedestrian_feature_id?: string;
  match_type?: string;
  evidence_confidence?: string;
  geometry?: GeoJSONGeometry | null;
}

function flattenCoords(
  coords: number[] | number[][] | number[][][],
  out: number[][],
) {
  if (typeof coords[0] === "number") {
    out.push(coords as number[]);
  } else if (Array.isArray(coords[0]) && typeof coords[0][0] === "number") {
    for (const c of coords as number[][]) flattenCoords(c, out);
  } else {
    for (const c of coords as number[][][]) flattenCoords(c, out);
  }
}

function geometryCentroid(geometry: GeoJSONGeometry): [number, number] | null {
  const pts: number[][] = [];
  flattenCoords(geometry.coordinates, pts);
  if (!pts.length) return null;
  const sumLng = pts.reduce((acc, p) => acc + p[0], 0);
  const sumLat = pts.reduce((acc, p) => acc + p[1], 0);
  return [sumLng / pts.length, sumLat / pts.length];
}

function geometriesBounds(geometries: (GeoJSONGeometry | null | undefined)[]): LngLatBoundsLike | null {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  for (const g of geometries) {
    if (!g) continue;
    const pts: number[][] = [];
    flattenCoords(g.coordinates, pts);
    for (const [lng, lat] of pts) {
      minLng = Math.min(minLng, lng);
      minLat = Math.min(minLat, lat);
      maxLng = Math.max(maxLng, lng);
      maxLat = Math.max(maxLat, lat);
    }
  }
  if (minLng === Infinity) return null;
  return [minLng, minLat, maxLng, maxLat];
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

interface BoundsFitOptions {
  padding: { top: number; bottom: number; left: number; right: number } | number;
  maxZoom?: number;
  duration?: number;
  pitch?: number;
  bearing?: number;
}

function easeToBounds(map: MaplibreMap, bounds: LngLatBoundsLike, options: BoundsFitOptions) {
  // Single camera animation. Running easeTo + fitBounds in parallel makes the
  // two animations fight each other, which visibly shakes the map.
  const camera = map.cameraForBounds(bounds as never, {
    padding: options.padding as never,
    maxZoom: options.maxZoom,
  });
  if (!camera) return;
  // Cancel any running camera animation so animations never stack, and keep
  // the user's current pitch/bearing unless the caller asks to change them.
  map.stop();
  map.easeTo({
    ...camera,
    ...(options.pitch !== undefined ? { pitch: options.pitch } : {}),
    ...(options.bearing !== undefined ? { bearing: options.bearing } : {}),
    duration: options.duration ?? 1100,
  });
}

function lerpPt(a: [number, number], b: [number, number], t: number): [number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

function slicePath(path: [number, number][], t: number): [number, number][] {
  if (t >= 1 || path.length <= 2) return path;
  const idx = t * (path.length - 1);
  const i = Math.floor(idx);
  const f = idx - i;
  const out = path.slice(0, i + 1);
  if (i + 1 < path.length) out.push(lerpPt(path[i], path[i + 1], f));
  return out.length >= 2 ? out : [path[0], path[1] ?? path[0]];
}

function approxDistanceMeters(a: [number, number], b: [number, number]): number {
  const latRad = ((a[1] + b[1]) / 2) * (Math.PI / 180);
  const dx = (b[0] - a[0]) * 111320 * Math.cos(latRad);
  const dy = (b[1] - a[1]) * 110540;
  return Math.sqrt(dx * dx + dy * dy);
}

function bearingDegrees(a: [number, number], b: [number, number]): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLng = toRad(b[0] - a[0]);
  const lat1 = toRad(a[1]);
  const lat2 = toRad(b[1]);
  const y = Math.sin(dLng) * Math.cos(lat2);
  const x =
    Math.cos(lat1) * Math.sin(lat2) -
    Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
  return (Math.atan2(y, x) * 180) / Math.PI;
}

function moveAlong(p: [number, number], bearingDeg: number, distM: number): [number, number] {
  const rad = (bearingDeg * Math.PI) / 180;
  const dLat = (distM * Math.cos(rad)) / 110540;
  const dLng =
    (distM * Math.sin(rad)) /
    (111320 * Math.cos((p[1] * Math.PI) / 180));
  return [p[0] + dLng, p[1] + dLat];
}

function convexHull(points: [number, number][]): [number, number][] {
  if (points.length <= 3) return points;
  const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (
    o: [number, number],
    a: [number, number],
    b: [number, number],
  ) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: [number, number][] = [];
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
      lower.pop();
    }
    lower.push(p);
  }
  const upper: [number, number][] = [];
  for (let i = sorted.length - 1; i >= 0; i--) {
    const p = sorted[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
      upper.pop();
    }
    upper.push(p);
  }
  upper.pop();
  lower.pop();
  return lower.concat(upper);
}

/** Approximate buffer polygon around a polyline: hull of per-vertex circles. */
function bufferHull(
  coords: [number, number][],
  radiusM: number,
  steps = 16,
): [number, number][] {
  const ring: [number, number][] = [];
  for (const c of coords) {
    for (let i = 0; i < steps; i++) {
      ring.push(moveAlong(c, (360 / steps) * i, radiusM));
    }
  }
  return convexHull(ring);
}

interface RouteSample {
  pos: [number, number];
  bearing: number;
}

function sampleRouteAt(
  coords: [number, number][],
  cumulative: number[],
  distM: number,
): RouteSample | null {
  if (coords.length < 2) return null;
  const total = cumulative[cumulative.length - 1];
  const d = Math.max(0, Math.min(distM, total));
  let i = 1;
  while (i < cumulative.length - 1 && cumulative[i] < d) i++;
  const segStart = cumulative[i - 1];
  const segLen = cumulative[i] - segStart || 1;
  const f = Math.max(0, Math.min(1, (d - segStart) / segLen));
  return {
    pos: lerpPt(coords[i - 1], coords[i], f),
    bearing: bearingDegrees(coords[i - 1], coords[i]),
  };
}

function walkContext(events: WalkEvent[], dist: number) {
  let sidewalk: string | null = null;
  let next: { kind: string; label: string; at_m: number } | null = null;
  for (const ev of events) {
    if (ev.kind === "sidewalk_change" && ev.at_m <= dist) sidewalk = ev.label;
    if (!next && ev.at_m > dist + 1 && ev.kind !== "sidewalk_change") {
      next = { kind: ev.kind, label: ev.label, at_m: ev.at_m };
    }
  }
  return { sidewalk, next };
}

export default function MapView({
  onFeatureSelect,
}: {
  onFeatureSelect: (restrictionId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MaplibreMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const travelerMarkerRef = useRef<Marker | null>(null);
  const basemapRef = useRef<BasemapId>("streets");
  const massingManifestRef = useRef<MassingManifest | null>(null);
  const massingActiveRef = useRef<Set<string>>(new Set());
  const massingModeRef = useRef<"martin" | "grid" | null>(null);
  const massingModeAttemptRef = useRef(0);
  const initializedRef = useRef(false);
  const setupDoneRef = useRef(false);
  const setupLayersFnRef = useRef<(() => void) | null>(null);
  const didInitialFitRef = useRef(false);
  const walkRafRef = useRef<number>(0);
  const walkBearingRef = useRef<number>(0);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapZoom, setMapZoom] = useState(11);
  const [anim, setAnim] = useState({ t: 0, progress: 1 });
  const [poiFeatures, setPoiFeatures] = useState<PoiFeature[]>([]);
  const [walkProgress, setWalkProgress] = useState<{
    distance: number;
    total: number;
    pct: number;
    sidewalk: string | null;
    next: { kind: string; label: string; at_m: number } | null;
  } | null>(null);

  const restrictions = useStore((s) => s.restrictions);
  const filters = useStore((s) => s.filters);
  const activeRestrictionId = useStore((s) => s.activeRestrictionId);
  const timeFilterHours = useStore((s) => s.timeFilterHours);
  const selectedDetail = useStore((s) => s.selectedDetail);
  const selectedMatches = useStore((s) => s.selectedMatches) as unknown as EvidenceMatchLike[];
  const layerToggles = useStore((s) => s.layerToggles);
  const cameraSignals = useStore((s) => s.cameraSignals);
  const walkSignals = useStore((s) => s.walkSignals);
  const groundView = useStore((s) => s.groundView);
  const isWalking = useStore((s) => s.isWalking);
  const setIsWalking = useStore((s) => s.setIsWalking);
  const predictionLocation = useStore((s) => s.predictionLocation);
  const routeOrigin = useStore((s) => s.routeOrigin);
  const routeDestination = useStore((s) => s.routeDestination);
  const route = useStore((s) => s.route);
  const routePicking = useStore((s) => s.routePicking);
  const setRoutePoint = useStore((s) => s.setRoutePoint);
  const walkOverridePath = useStore((s) => s.walkOverridePath);
  const setWalkOverridePath = useStore((s) => s.setWalkOverridePath);
  const startWalk = useStore((s) => s.startWalk);
  const setRouteNearbyCount = useStore((s) => s.setRouteNearbyCount);

  const filtered = useMemo(
    () => filterAndSortRestrictions(restrictions, filters),
    [restrictions, filters],
  );
  const selectedId = resolveMapSelection(activeRestrictionId, filtered);

  const activeRouteCoords = useMemo(() => {
    const geometry = route?.recommended?.geometry ?? route?.baseline?.geometry;
    if (!geometry || geometry.type !== "LineString") return null;
    const coords = geometry.coordinates as [number, number][];
    return coords.length >= 2 ? coords : null;
  }, [route]);

  const routeCumulative = useMemo(() => {
    if (!activeRouteCoords) return null;
    const cumulative: number[] = [0];
    for (let i = 1; i < activeRouteCoords.length; i++) {
      cumulative.push(
        cumulative[i - 1] + approxDistanceMeters(activeRouteCoords[i - 1], activeRouteCoords[i]),
      );
    }
    return cumulative;
  }, [activeRouteCoords]);

  const nearbyRestrictionIds = useMemo(() => {
    const ids = new Set<string>();
    if (!activeRouteCoords) return ids;
    for (const r of restrictions) {
      if (!r.coordinates || r.coordinates.length !== 2) continue;
      const p: [number, number] = [r.coordinates[0], r.coordinates[1]];
      for (const v of activeRouteCoords) {
        if (approxDistanceMeters(p, v) <= 75) {
          ids.add(r.restriction_id);
          break;
        }
      }
    }
    return ids;
  }, [restrictions, activeRouteCoords]);

  const allowed = useMemo(
    () => new Set(filtered.map((item) => item.restriction_id)),
    [filtered],
  );

  const points = useMemo<PointItem[]>(
    () =>
      restrictions
        .filter(
          (r) =>
            r.coordinates &&
            r.coordinates.length === 2 &&
            allowed.has(r.restriction_id) &&
            (timeFilterHours == null ||
              timeFilterHours <= 0 ||
              (r.duration_hours != null && timeFilterHours <= r.duration_hours)),
        )
        .map((r) => ({
          restriction_id: r.restriction_id,
          coordinates: [r.coordinates![0], r.coordinates![1]] as [number, number],
          evidence_confidence: r.evidence_confidence,
          impact_severity: r.impact_severity,
          candidate_edge_count: r.candidate_edge_count,
          duration_hours: r.duration_hours ?? null,
          match_type: r.match_type ?? null,
          location: r.location ?? null,
        })),
    [restrictions, allowed, timeFilterHours],
  );

  const selectedPoint = useMemo<[number, number] | null>(() => {
    if (!selectedDetail) return null;
    const g = selectedDetail.restriction_geometry;
    if (g && isUsableGeoJson(g)) {
      return geometryCentroid(g);
    }
    if (selectedDetail.coordinates && selectedDetail.coordinates.length === 2) {
      return [selectedDetail.coordinates[0], selectedDetail.coordinates[1]];
    }
    return null;
  }, [selectedDetail]);

  const matchGeometries = useMemo(() => {
    return selectedMatches
      .map((m) => (m.geometry && isUsableGeoJson(m.geometry) ? m.geometry : null))
      .filter((g): g is GeoJSONGeometry => g !== null);
  }, [selectedMatches]);

  const arcTargets = useMemo(() => {
    if (!selectedId || !selectedPoint) return [] as [number, number][];
    const centroids = matchGeometries
      .map((g) => geometryCentroid(g))
      .filter((c): c is [number, number] => c !== null);
    if (centroids.length <= 6) return centroids;
    return centroids
      .map((c) => ({ c, d: approxDistanceMeters(selectedPoint, c) }))
      .sort((a, b) => a.d - b.d)
      .slice(0, 5)
      .map((x) => x.c);
  }, [matchGeometries, selectedId, selectedPoint]);

  const ribbonPaths = useMemo(() => {
    return matchGeometries.map((g) => {
      const pts: number[][] = [];
      flattenCoords(g.coordinates, pts);
      return pts as [number, number][];
    });
  }, [matchGeometries]);

  const handleFeatureSelect = useCallback(onFeatureSelect, [onFeatureSelect]);

  useEffect(() => {
    setRouteNearbyCount(nearbyRestrictionIds.size);
  }, [nearbyRestrictionIds, setRouteNearbyCount]);

  useEffect(() => {
    if (!mapLoaded || poiFeatures.length > 0) return;
    let cancelled = false;
    getPois()
      .then((collection) => {
        if (!cancelled) setPoiFeatures(collection.features ?? []);
      })
      .catch(() => {
        // POI layers are optional; the map works without them.
      });
    return () => {
      cancelled = true;
    };
  }, [mapLoaded, poiFeatures.length]);

  // POIs within walking distance of the active route, via a coarse spatial
  // grid so 12k features filter in a single memoized pass.
  const routePois = useMemo(() => {
    if (!activeRouteCoords || activeRouteCoords.length < 2 || poiFeatures.length === 0) {
      return [] as PoiFeature[];
    }
    const cellSize = 0.003;
    const grid = new Map<string, PoiFeature[]>();
    for (const feature of poiFeatures) {
      const [lng, lat] = feature.geometry.coordinates;
      const k = `${Math.floor(lng / cellSize)}:${Math.floor(lat / cellSize)}`;
      const bucket = grid.get(k);
      if (bucket) bucket.push(feature);
      else grid.set(k, [feature]);
    }
    const seen = new Set<PoiFeature>();
    const near: PoiFeature[] = [];
    for (const [lng, lat] of activeRouteCoords) {
      const cx = Math.floor(lng / cellSize);
      const cy = Math.floor(lat / cellSize);
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          const bucket = grid.get(`${cx + dx}:${cy + dy}`);
          if (!bucket) continue;
          for (const feature of bucket) {
            if (seen.has(feature)) continue;
            const [plng, plat] = feature.geometry.coordinates;
            if (approxDistanceMeters([lng, lat], [plng, plat]) <= POI_ROUTE_PROXIMITY_M) {
              seen.add(feature);
              near.push(feature);
            }
          }
        }
      }
    }
    return near;
  }, [poiFeatures, activeRouteCoords]);

  // Per-restriction nearby POI count (within 200 m), used in tooltips to
  // surface how many amenities surround each disruption point.
  const restrictionPoiCounts = useMemo(() => {
    if (poiFeatures.length === 0 || points.length === 0) return new Map<string, number>();
    const cellSize = 0.003;
    const grid = new Map<string, PoiFeature[]>();
    for (const feature of poiFeatures) {
      const [lng, lat] = feature.geometry.coordinates;
      const k = `${Math.floor(lng / cellSize)}:${Math.floor(lat / cellSize)}`;
      const bucket = grid.get(k);
      if (bucket) bucket.push(feature);
      else grid.set(k, [feature]);
    }
    const counts = new Map<string, number>();
    for (const p of points) {
      const [lng, lat] = p.coordinates;
      const cx = Math.floor(lng / cellSize);
      const cy = Math.floor(lat / cellSize);
      let n = 0;
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          const bucket = grid.get(`${cx + dx}:${cy + dy}`);
          if (!bucket) continue;
          for (const feature of bucket) {
            const [plng, plat] = feature.geometry.coordinates;
            if (approxDistanceMeters([lng, lat], [plng, plat]) <= 200) n++;
          }
        }
      }
      counts.set(p.restriction_id, n);
    }
    return counts;
  }, [poiFeatures, points]);

  function removeMassingCell(map: MaplibreMap, cell: string) {
    const layerId = `massing-3d-${cell}`;
    if (map.getLayer(layerId)) map.removeLayer(layerId);
    if (map.getSource(`massing-${cell}`)) map.removeSource(`massing-${cell}`);
  }

  async function loadMassingCell(map: MaplibreMap, cell: string) {
    try {
      const data = (await getMassingCell(cell)) as GeoJSON.FeatureCollection;
      const sourceId = `massing-${cell}`;
      if (!map.getSource(sourceId)) {
        map.addSource(sourceId, { type: "geojson", data: data as never });
        map.addLayer({
          id: `massing-3d-${cell}`,
          type: "fill-extrusion",
          source: sourceId,
          minzoom: MASSING_LAYER_MINZOOM,
          paint: {
            "fill-extrusion-color": [
              "interpolate",
              ["linear"],
              ["coalesce", ["get", "h"], 0],
              3, "#eef2f7",
              8, "#dbe4ef",
              18, "#c2d1e4",
              35, "#9fb8d8",
              70, "#7d9cc6",
              120, "#5c7fb4",
              200, "#3c5e93",
            ],
            "fill-extrusion-height": ["coalesce", ["get", "h"], 5],
            "fill-extrusion-base": 0,
            "fill-extrusion-opacity": 0.9,
            "fill-extrusion-vertical-gradient": true,
          },
        });
      }
    } catch {
      massingActiveRef.current.delete(cell);
    }
  }

  function syncOsmBuildings(map: MaplibreMap, buildingsOn: boolean, massingInView: boolean) {
    if (!map.getLayer("3d-buildings")) return;
    map.setLayoutProperty(
      "3d-buildings",
      "visibility",
      buildingsOn && !massingInView ? "visible" : "none",
    );
  }

  const MASSING_PAINT = {
    "fill-extrusion-color": [
      "interpolate",
      ["linear"],
      ["coalesce", ["get", "h"], 0],
      3, "#eef2f7",
      8, "#dbe4ef",
      18, "#c2d1e4",
      35, "#9fb8d8",
      70, "#7d9cc6",
      120, "#5c7fb4",
      200, "#3c5e93",
    ],
    "fill-extrusion-height": ["coalesce", ["get", "h"], 5],
    "fill-extrusion-base": 0,
    "fill-extrusion-opacity": 0.9,
    "fill-extrusion-vertical-gradient": true,
  };

  function addMartinLayer(map: MaplibreMap) {
    const hasSource = map.getSource("massing-city");
    const hasLayer = map.getLayer("massing-city-3d");
    if (hasSource && hasLayer) return;
    try {
      if (!hasSource) {
        map.addSource("massing-city", { type: "vector", url: MASSING_TILE_URL });
      }
      if (!hasLayer) {
        map.addLayer({
          id: "massing-city-3d",
          type: "fill-extrusion",
          source: "massing-city",
          "source-layer": "massing",
          minzoom: MASSING_LAYER_MINZOOM,
          paint: MASSING_PAINT as never,
        });
      }
      console.log("MapView: added martin massing layer, source:", MASSING_TILE_URL);
    } catch (error) {
      console.warn("MapView: martin layer add failed, will retry", error);
    }
  }

  async function resolveMassingMode(): Promise<"martin" | "grid"> {
    // A failed check (dev-server compile stalls, slow first paint, proxy hiccup)
    // must not lock the app to grid mode forever: retry after 30 seconds.
    if (massingModeRef.current === "martin") return "martin";
    const now = Date.now();
    if (massingModeRef.current === "grid" && now - massingModeAttemptRef.current < 30_000) {
      return "grid";
    }
    massingModeAttemptRef.current = now;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      const response = await fetch(MASSING_TILE_URL, {
        method: "HEAD",
        signal: controller.signal,
      });
      clearTimeout(timeout);
      massingModeRef.current = response.ok ? "martin" : "grid";
      if (massingModeRef.current === "grid") {
        console.warn("MapView: martin tile server check failed, using grid cells (will retry)");
      }
    } catch {
      massingModeRef.current = "grid";
      console.warn("MapView: martin tile server unreachable, using grid cells (will retry)");
    }
    return massingModeRef.current;
  }

  const refreshMassingCells = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    const buildingsOn = useStore.getState().layerToggles.buildings;
    const zoom = map.getZoom();

    if (!buildingsOn || zoom < MASSING_LAYER_MINZOOM) {
      for (const cell of Array.from(massingActiveRef.current)) removeMassingCell(map, cell);
      massingActiveRef.current.clear();
      if (map.getLayer("massing-city-3d")) {
        map.setLayoutProperty("massing-city-3d", "visibility", "none");
      }
      syncOsmBuildings(map, buildingsOn, false);
      return;
    }

    const mode = await resolveMassingMode();
    console.log("MapView: refreshMassingCells mode=", mode, "zoom=", map.getZoom().toFixed(1), "buildingsOn=", buildingsOn);
    if (mode === "martin") {
      for (const cell of Array.from(massingActiveRef.current)) removeMassingCell(map, cell);
      massingActiveRef.current.clear();
      addMartinLayer(map);
      if (map.getLayer("massing-city-3d")) {
        map.setLayoutProperty("massing-city-3d", "visibility", "visible");
      }
      syncOsmBuildings(map, buildingsOn, true);
      return;
    }

    let manifest = massingManifestRef.current;
    if (!manifest) {
      try {
        manifest = await getMassingManifest();
        massingManifestRef.current = manifest;
      } catch {
        return;
      }
    }

    const bounds = map.getBounds();
    const west = bounds.getWest();
    const south = bounds.getSouth();
    const east = bounds.getEast();
    const north = bounds.getNorth();
    const needed = new Set<string>();
    for (const [cell, cellBounds] of Object.entries(manifest.cells)) {
      const [cw, cs, ce, cn] = cellBounds;
      if (cw <= east && ce >= west && cs <= north && cn >= south) needed.add(cell);
    }
    for (const cell of Array.from(massingActiveRef.current)) {
      if (!needed.has(cell)) {
        removeMassingCell(map, cell);
        massingActiveRef.current.delete(cell);
      }
    }
    for (const cell of needed) {
      if (!massingActiveRef.current.has(cell)) {
        massingActiveRef.current.add(cell);
        loadMassingCell(map, cell);
      }
    }
    syncOsmBuildings(map, buildingsOn, needed.size > 0);
  }, []);

  useEffect(() => {
    if (initializedRef.current || !containerRef.current) return;
    initializedRef.current = true;

    const map = new MaplibreMap({
      container: containerRef.current,
      style: VECTOR_STYLE_URL,
      center: TORONTO_CENTER,
      zoom: TORONTO_ZOOM,
      pitch: 0,
      maxBounds: [
        [-79.9, 43.4],
        [-78.9, 44.0],
      ],
    });

    map.addControl(new NavigationControl({ showCompass: true, showZoom: true, visualizePitch: true }), "bottom-right");

    const setupCustomLayers = () => {
      if (setupDoneRef.current) return;
      setupDoneRef.current = true;
      console.log("MapView: setupCustomLayers running");

      map.addSource("evidence-geometries", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "evidence-halo",
        type: "line",
        source: "evidence-geometries",
        paint: {
          "line-color": "#087f8c",
          "line-width": 12,
          "line-opacity": 0.25,
          "line-blur": 4,
        },
        layout: { "line-join": "round", "line-cap": "round" },
      });

      map.addLayer({
        id: "evidence-lines",
        type: "line",
        source: "evidence-geometries",
        paint: {
          "line-color": "#0aa6b8",
          "line-width": 3.5,
          "line-opacity": 0.95,
        },
        layout: { "line-join": "round", "line-cap": "round" },
      });

      const style = map.getStyle();
      const sources = style.sources as Record<string, { type?: string }>;
      console.log("MapView: style sources:", Object.keys(sources).map(k => `${k}:${sources[k]?.type}`));
      const vectorName = Object.keys(sources).find((k) => sources[k]?.type === "vector");

      // Ground-level impact zone around the selected restriction: a warm
      // translucent buffer under the 3D buildings showing which block the
      // disruption affects. Added before any building layer so extrusions
      // rise above it.
      map.addSource("impact-zone", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "impact-zone-fill",
        type: "fill",
        source: "impact-zone",
        paint: {
          "fill-color": "#e07a2f",
          "fill-opacity": 0.16,
        },
      });
      map.addLayer({
        id: "impact-zone-outline",
        type: "line",
        source: "impact-zone",
        paint: {
          "line-color": "#e07a2f",
          "line-width": 2,
          "line-opacity": 0.7,
          "line-dasharray": [3, 2],
        },
      });

      if (vectorName) {
        map.addLayer({
          id: "3d-buildings",
          type: "fill-extrusion",
          source: vectorName,
          "source-layer": "building",
          minzoom: 14,
          paint: {
            "fill-extrusion-color": [
              "interpolate",
              ["linear"],
              ["coalesce", ["get", "render_height"], 0],
              0, "#d9dee6",
              25, "#c3ccd8",
              80, "#a3b1c4",
              180, "#8595ac",
            ],
            "fill-extrusion-height": [
              "interpolate",
              ["linear"],
              ["zoom"],
              14, 0,
              15.5, ["coalesce", ["get", "render_height"], 8],
            ],
            "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
            "fill-extrusion-opacity": 0.88,
          },
        });
        map.setLayoutProperty(
          "3d-buildings",
          "visibility",
          layerToggles.buildings ? "visible" : "none",
        );
        console.log("MapView: added 3d-buildings layer on source:", vectorName);
      } else {
        console.warn("MapView: no vector source found for 3d-buildings");
      }

      const overlay = new MapboxOverlay({
        interleaved: false,
        layers: [],
        getTooltip: (info: { object?: Record<string, unknown> }) => {
          const obj = info?.object as PointItem | PoiFeature | undefined;
          if (obj && (obj as PoiFeature).properties?.kind) {
            const poi = obj as PoiFeature;
            const style = POI_KIND_STYLES[poi.properties.kind];
            const accessible = poi.properties.accessible
              ? `<br/>${poi.properties.accessible}`
              : "";
            return {
              html: `<b>${poi.properties.name}</b><br/>${style?.label ?? poi.properties.kind}${poi.properties.details ? `<br/>${poi.properties.details}` : ""}${accessible}`,
              style: {
                background: "rgba(16, 42, 67, 0.92)",
                color: "#fff",
                borderRadius: "8px",
                padding: "6px 10px",
                fontSize: "12px",
                border: "1px solid #486581",
              },
            };
          }
          if (obj && (obj as PointItem).restriction_id) {
            const item = obj as PointItem;
            const title = item.location?.road || item.restriction_id;
            const cross =
              item.location?.from_road && item.location?.to_road
                ? `${item.location.from_road} → ${item.location.to_road}`
                : item.location?.name || "";
            const poiCount = restrictionPoiCounts.get(item.restriction_id) ?? 0;
            const meta = [
              item.evidence_confidence,
              `impact ${item.impact_severity}`,
              humanizeDuration(item.duration_hours),
              item.match_type ? `${item.match_type} match` : null,
              `${Math.max(1, item.candidate_edge_count ?? 1)} candidate edge${(item.candidate_edge_count ?? 1) === 1 ? "" : "s"}`,
              poiCount > 0 ? `${poiCount} amenit${poiCount === 1 ? "y" : "ies"} within 200 m` : null,
            ]
              .filter(Boolean)
              .join(" · ");
            return {
              html: `<b>${title}</b>${cross ? `<br/>${cross}` : ""}<br/>${meta}`,
              style: {
                background: "rgba(16, 42, 67, 0.92)",
                color: "#fff",
                borderRadius: "8px",
                padding: "6px 10px",
                fontSize: "12px",
                border: "1px solid #486581",
              },
            };
          }
          return null;
        },
      });
      map.addControl(overlay);
      overlayRef.current = overlay;

      setMapLoaded(true);
    };

    map.on("load", () => {
      console.log("MapView: map 'load' event fired");
      setupCustomLayers();
    });
    setupLayersFnRef.current = setupCustomLayers;

    map.on("click", (e: MapMouseEvent) => {
      const picking = useStore.getState().routePicking;
      if (picking) {
        setRoutePoint(picking, [e.lngLat.lng, e.lngLat.lat]);
      }
    });

    map.on("moveend", () => {
      refreshMassingCells();
    });

    map.on("zoomend", () => {
      setMapZoom(map.getZoom());
    });

    // Surface map errors, and if the Martin tile source fails (server down,
    // CORS, etc.) fall back to the grid-cell massing and restore OSM buildings
    // so the map never ends up with no buildings at all.
    map.on("error", (e: { sourceId?: string; error?: unknown }) => {
      const sourceId = (e as { sourceId?: string }).sourceId;
      const message = e instanceof Error ? e.message : String((e as { error?: unknown })?.error ?? e);
      console.warn("MapView: map error", sourceId ?? "", message);
      if (sourceId === "massing-city") {
        massingModeRef.current = "grid";
        massingModeAttemptRef.current = Date.now();
        try {
          if (map.getLayer("massing-city-3d")) map.removeLayer("massing-city-3d");
          if (map.getSource("massing-city")) map.removeSource("massing-city");
        } catch {
          /* already gone */
        }
        refreshMassingCells();
      }
    });

    const fallbackTimer = setTimeout(() => {
      if (!setupDoneRef.current) {
        console.warn("MapView: vector style load timed out, falling back to raster");
        map.setStyle(RASTER_FALLBACK_STYLE as never);
        // 'styledata' fires while the new style is still loading; layers added
        // in that window can be dropped (observed: the massing source survived
        // but its layer was lost and no tiles were ever requested). 'idle'
        // fires after rendering settles — same pattern as the basemap switch.
        const reinit = () => {
          if (!setupDoneRef.current) {
            try {
              setupLayersFnRef.current?.();
            } catch (error) {
              console.warn("MapView: style re-init failed", error);
            }
          }
          refreshMassingCells();
        };
        map.once("idle", reinit);
        // If 'load' re-fires for the new style it re-runs setupCustomLayers
        // directly; 'idle' covers the case where it does not.
      }
    }, 30000);

    mapRef.current = map;

    // The user always wins: any pointer or wheel input immediately cancels
    // running camera animations so focus animations never fight gestures.
    const stopCamera = () => map.stop();
    const canvasEl = map.getCanvas();
    canvasEl.addEventListener("pointerdown", stopCamera);
    canvasEl.addEventListener("wheel", stopCamera, { passive: true });

    return () => {
      canvasEl.removeEventListener("pointerdown", stopCamera);
      canvasEl.removeEventListener("wheel", stopCamera);
      clearTimeout(fallbackTimer);
      cancelAnimationFrame(walkRafRef.current);
      walkRafRef.current = 0;
      markerRef.current?.remove();
      travelerMarkerRef.current?.remove();
      travelerMarkerRef.current = null;
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
      initializedRef.current = false;
      setupDoneRef.current = false;
      setMapLoaded(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId && !route) {
      setAnim({ t: 0, progress: 1 });
      return;
    }
    let raf = 0;
    const start = performance.now();
    const loop = (now: number) => {
      const t = (now - start) / 1000;
      const progress = Math.min(1, easeOutCubic(t / 0.9));
      setAnim({ t, progress });
      // Stop the loop once the draw-in animation completes; a perpetually
      // running rAF re-renders the component at 60fps for as long as a
      // restriction is selected.
      if (progress < 1) raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [selectedId, route]);

  useEffect(() => {
    if (!mapLoaded) return;
    const overlay = overlayRef.current;
    if (!overlay) return;

    const arcProgress = selectedId ? easeOutCubic(anim.progress) : 1;
    const layers: unknown[] = [];

    if (layerToggles.heatmap && points.length > 0) {
      layers.push(
        new HeatmapLayer({
          id: "restriction-heatmap",
          data: points,
          getPosition: (d: PointItem) => d.coordinates,
          getWeight: (d: PointItem) =>
            d.impact_severity === "SEVERE" || d.impact_severity === "HIGH" ? 3 : 1,
          radiusPixels: 70,
          intensity: 1,
          threshold: 0.05,
        }),
      );
    }

    if (layerToggles.towers && points.length > 0) {
      layers.push(
        new ColumnLayer({
          id: "severity-towers",
          data: points,
          diskResolution: 12,
          radius: 35,
          extruded: true,
          elevationScale: 0.65,
          getPosition: (d: PointItem) => d.coordinates,
          getElevation: (d: PointItem) => Math.max(1, d.candidate_edge_count) * 50,
          getFillColor: (d: PointItem) =>
            EVIDENCE_RGB[d.evidence_confidence] ?? [152, 162, 179],
          getLineColor: [255, 255, 255],
          stroked: true,
          pickable: true,
          onClick: (info: { object?: PointItem }) => {
            const picking = useStore.getState().routePicking;
            if (picking && info.object) {
              setRoutePoint(picking, info.object.coordinates);
              return true;
            }
            const id = info.object?.restriction_id;
            if (id) handleFeatureSelect(id);
            return true;
          },
        }),
      );
    }

    if (selectedPoint && ribbonPaths.length > 0) {
      const ribbonData = ribbonPaths.map((p) => ({
        path: slicePath(p, arcProgress),
        color: EVIDENCE_RGB[selectedDetail?.evidence_confidence ?? ""] ?? [10, 166, 184],
      }));
      layers.push(
        new PathLayer({
          id: "evidence-ribbon",
          data: ribbonData,
          getPath: (d: { path: [number, number][] }) => d.path,
          getColor: (d: { color: [number, number, number] }) => d.color,
          getWidth: 5,
          widthUnits: "meters",
          rounded: true,
          opacity: 0.7,
        }),
      );
    }

    if (selectedPoint && arcTargets.length > 0) {
      const arcData = arcTargets.map((target) => ({
        source: selectedPoint,
        target: lerpPt(selectedPoint, target, arcProgress),
      }));
      layers.push(
        new ArcLayer({
          id: "evidence-arcs",
          data: arcData,
          getSourcePosition: (d: { source: [number, number] }) => d.source,
          getTargetPosition: (d: { target: [number, number] }) => d.target,
          getSourceColor: [8, 127, 140, 180],
          getTargetColor: [181, 71, 8, 190],
          getWidth: 2,
          greatCircle: false,
          pickable: false,
        }),
      );
    }

    const routePaths: { path: [number, number][]; color: [number, number, number]; id: string }[] = [];
    if (route?.baseline?.geometry?.type === "LineString") {
      routePaths.push({
        id: "route-baseline",
        path: route.baseline.geometry.coordinates as [number, number][],
        color: [120, 130, 145],
      });
    }
    if (route?.recommended?.geometry?.type === "LineString") {
      routePaths.push({
        id: "route-recommended",
        path: route.recommended.geometry.coordinates as [number, number][],
        color: [8, 127, 140],
      });
    }
    for (const routePath of routePaths) {
      layers.push(
        new PathLayer({
          id: routePath.id,
          data: [routePath],
          getPath: (d: { path: [number, number][] }) => d.path,
          getColor: (d: { color: [number, number, number] }) => d.color,
          getWidth: routePath.id === "route-recommended" ? 7 : 5,
          widthUnits: "meters",
          rounded: true,
          opacity: routePath.id === "route-recommended" ? 0.95 : 0.65,
          dashArray: routePath.id === "route-baseline" ? [8, 5] : undefined,
        }),
      );
    }

    if (activeRouteCoords && routeCumulative && !isWalking) {
      const totalRouteMeters = routeCumulative[routeCumulative.length - 1] || 1;
      const spacing = 140;
      const flowOffset = (anim.t * 16) % spacing;
      const chevrons: { path: [number, number][] }[] = [];
      for (let d = flowOffset; d < totalRouteMeters - 20; d += spacing) {
        const sample = sampleRouteAt(activeRouteCoords, routeCumulative, d);
        if (!sample) continue;
        const back = moveAlong(sample.pos, sample.bearing, -13);
        const left = moveAlong(back, sample.bearing - 90, 4.5);
        const right = moveAlong(back, sample.bearing + 90, 4.5);
        chevrons.push({ path: [left, sample.pos, right] });
      }
      if (chevrons.length > 0) {
        layers.push(
          new PathLayer({
            id: "route-chevrons",
            data: chevrons,
            getPath: (d: { path: [number, number][] }) => d.path,
            getColor: [12, 150, 166],
            getWidth: 3.2,
            widthUnits: "meters",
            rounded: true,
            opacity: 0.95,
            pickable: false,
            parameters: { depthTest: false },
          }),
        );
      }
    }

    if (routeOrigin) {
      layers.push(
        new ScatterplotLayer({
          id: "route-origin-marker",
          data: [{ position: routeOrigin }],
          getPosition: (d: { position: [number, number] }) => d.position,
          radiusUnits: "pixels",
          getRadius: 9,
          getFillColor: [23, 105, 170],
          getLineColor: [255, 255, 255],
          stroked: true,
          lineWidthPixels: 2,
          pickable: false,
        }),
      );
    }
    if (routeDestination) {
      layers.push(
        new ScatterplotLayer({
          id: "route-destination-marker",
          data: [{ position: routeDestination }],
          getPosition: (d: { position: [number, number] }) => d.position,
          radiusUnits: "pixels",
          getRadius: 9,
          getFillColor: [46, 204, 113],
          getLineColor: [255, 255, 255],
          stroked: true,
          lineWidthPixels: 2,
          pickable: false,
        }),
      );
    }

    if (routePois.length > 0) {
      layers.push(
        new ScatterplotLayer({
          id: "poi-rings",
          data: routePois,
          getPosition: (d: PoiFeature) => d.geometry.coordinates,
          radiusUnits: "pixels",
          getRadius: 10,
          filled: false,
          stroked: true,
          lineWidthPixels: 1.5,
          getLineColor: [255, 255, 255, 190],
          pickable: false,
        }),
        new IconLayer({
          id: "poi-icons",
          data: routePois,
          getPosition: (d: PoiFeature) => d.geometry.coordinates,
          getIcon: (d: PoiFeature) => ({
            url: (POI_KIND_STYLES[d.properties.kind] ?? POI_KIND_STYLES.bench).icon,
            width: 64,
            height: 64,
            anchorX: 32,
            anchorY: 32,
            mask: true,
          }),
          sizeUnits: "pixels",
          getSize: 16,
          getColor: (d: PoiFeature) =>
            (POI_KIND_STYLES[d.properties.kind] ?? POI_KIND_STYLES.bench).color,
          getOpacity: 0.95,
          pickable: true,
          autoHighlight: true,
          highlightColor: [253, 176, 34, 110],
        }),
      );
    }

    const pulse = selectedId ? (anim.t * 1.3) % 1 : 0;
    const dotDim = (d: PointItem) =>
      selectedId && d.restriction_id !== selectedId ? 0.22 : 1;
    const dotRadius = (d: PointItem) => {
      if (d.restriction_id === selectedId) return 12;
      const edges = Math.max(1, d.candidate_edge_count ?? 1);
      return 7.5 + Math.min(4, edges - 1);
    };
    const dotClick = (info: { object?: PointItem }) => {
      const picking = useStore.getState().routePicking;
      if (picking && info.object) {
        setRoutePoint(picking, info.object.coordinates);
        return true;
      }
      const id = info.object?.restriction_id;
      if (id) handleFeatureSelect(id);
      return true;
    };

    layers.push(
      new ScatterplotLayer({
        id: "restriction-rings",
        data: points,
        getPosition: (d: PointItem) => d.coordinates,
        radiusUnits: "pixels",
        getRadius: (d: PointItem) => dotRadius(d) + 2.5,
        filled: false,
        stroked: true,
        lineWidthPixels: (d: PointItem) =>
          nearbyRestrictionIds.has(d.restriction_id) ? 2.5 : 1.5,
        getLineColor: (d: PointItem) =>
          d.restriction_id === selectedId
            ? [253, 176, 34, 240]
            : nearbyRestrictionIds.has(d.restriction_id)
              ? [253, 176, 34, 235]
              : [255, 255, 255, 200],
        getOpacity: dotDim,
        pickable: false,
        updateTriggers: {
          getRadius: [selectedId],
          getLineColor: [nearbyRestrictionIds, selectedId],
          lineWidthPixels: [nearbyRestrictionIds],
          getOpacity: [selectedId],
        },
      }),
      new IconLayer({
        id: "restriction-icons",
        data: points,
        getPosition: (d: PointItem) => d.coordinates,
        getIcon: (d: PointItem) => ({
          url: DURATION_ICON_URLS[durationClass(d.duration_hours)],
          width: 64,
          height: 80,
          anchorX: 32,
          anchorY: 78,
          mask: true,
        }),
        sizeUnits: "pixels",
        getSize: (d: PointItem) => dotRadius(d) * 2,
        getColor: (d: PointItem) =>
          EVIDENCE_RGB[d.evidence_confidence] ?? [152, 162, 179],
        getOpacity: dotDim,
        pickable: true,
        autoHighlight: true,
        highlightColor: [253, 176, 34, 120],
        onClick: dotClick,
        updateTriggers: {
          getSize: [selectedId],
          getOpacity: [selectedId],
        },
      }),
    );

    if (mapZoom >= 15.5) {
      layers.push(
        new TextLayer({
          id: "restriction-labels",
          data: points,
          getPosition: (d: PointItem) => d.coordinates,
          getText: (d: PointItem) =>
            d.location?.road || d.location?.name || d.restriction_id,
          getSize: 12,
          sizeUnits: "pixels",
          getPixelOffset: (d: PointItem) => [0, -(dotRadius(d) + 12)],
          getColor: [23, 43, 77, 230],
          background: true,
          getBackgroundColor: [255, 255, 255, 215],
          backgroundPadding: [5, 3],
          fontFamily: "Segoe UI, sans-serif",
          fontWeight: 600,
          characterSet: "auto",
          getOpacity: dotDim,
          pickable: false,
          updateTriggers: {
            getPixelOffset: [selectedId],
            getOpacity: [selectedId],
          },
        }),
      );
    }

    if (selectedPoint && selectedId) {
      layers.push(
        new ScatterplotLayer({
          id: "selection-pulse",
          data: [{ position: selectedPoint }],
          getPosition: (d: { position: [number, number] }) => d.position,
          radiusUnits: "pixels",
          getRadius: 14 + 30 * pulse,
          stroked: true,
          filled: false,
          lineWidthPixels: 2.5,
          getLineColor: [253, 176, 34, Math.round(230 * (1 - pulse))],
          pickable: false,
          updateTriggers: {
            getRadius: pulse,
            getLineColor: pulse,
          },
        }),
      );
    }

    overlay.setProps({ layers: layers as never });
  }, [
    mapLoaded,
    mapZoom,
    points,
    selectedId,
    selectedPoint,
    selectedDetail,
    arcTargets,
    ribbonPaths,
    anim,
    layerToggles,
    handleFeatureSelect,
    route,
    routeOrigin,
    routeDestination,
    setRoutePoint,
    activeRouteCoords,
    routeCumulative,
    routePois,
    nearbyRestrictionIds,
    isWalking,
    restrictionPoiCounts,
  ]);

  // Traveler marker: a DOM marker with the wheelchair glyph. Shows at the
  // origin immediately when a route is computed, then moves along the route
  // during walking. Kept as a separate effect so deck.gl layers don't
  // re-render on every walk frame.
  useEffect(() => {
    const liveMap = mapRef.current;
    if (!liveMap) return;

    let pos: [number, number] | null = null;
    if (isWalking && activeRouteCoords && routeCumulative && walkProgress) {
      const sample = sampleRouteAt(activeRouteCoords, routeCumulative, walkProgress.distance);
      pos = sample?.pos ?? null;
    } else if (routeOrigin) {
      pos = routeOrigin;
    }

    if (pos) {
      if (!travelerMarkerRef.current) {
        const el = document.createElement("div");
        el.className = "traveler-marker";
        el.textContent = "♿";
        travelerMarkerRef.current = new Marker({ element: el, offset: [0, -16] })
          .setLngLat(pos)
          .addTo(liveMap);
      } else {
        travelerMarkerRef.current.setLngLat(pos);
      }
    } else if (travelerMarkerRef.current) {
      travelerMarkerRef.current.remove();
      travelerMarkerRef.current = null;
    }
  }, [walkProgress, isWalking, activeRouteCoords, routeCumulative, routeOrigin]);

  useEffect(() => {
    if (!mapLoaded) return;
    const map = mapRef.current;
    if (!map || !map.getSource("evidence-geometries")) return;

    const features = [] as GeoJSON.Feature[];
    if (selectedDetail?.restriction_geometry && isUsableGeoJson(selectedDetail.restriction_geometry)) {
      features.push({
        type: "Feature",
        geometry: selectedDetail.restriction_geometry as unknown as GeoJSON.Geometry,
        properties: { kind: "restriction" },
      });
    }
    for (const m of selectedMatches) {
      if (m.geometry && isUsableGeoJson(m.geometry)) {
        features.push({
          type: "Feature",
          geometry: m.geometry as unknown as GeoJSON.Geometry,
          properties: { kind: "candidate", id: m.pedestrian_feature_id },
        });
      }
    }
    const source = map.getSource("evidence-geometries") as GeoJSONSource;
    source.setData({
      type: "FeatureCollection",
      features,
    } as GeoJSON.FeatureCollection);
  }, [mapLoaded, selectedDetail, selectedMatches]);

  useEffect(() => {
    if (!mapLoaded) return;
    const map = mapRef.current;
    if (!map || !map.getSource("impact-zone")) return;

    let features: GeoJSON.Feature[] = [];
    if (selectedId && selectedDetail?.restriction_id === selectedId) {
      const coords: [number, number][] = [];
      const geometry = selectedDetail.restriction_geometry;
      if (geometry && isUsableGeoJson(geometry)) {
        flattenCoords(geometry.coordinates, coords);
      } else if (selectedPoint) {
        coords.push(selectedPoint);
      }
      if (coords.length > 0) {
        const hull = bufferHull(coords, 75);
        const ring = [...hull, hull[0]];
        features = [
          {
            type: "Feature",
            geometry: { type: "Polygon", coordinates: [ring] },
            properties: {},
          },
        ];
      }
    }
    const zone = map.getSource("impact-zone") as GeoJSONSource;
    zone.setData({
      type: "FeatureCollection",
      features,
    } as GeoJSON.FeatureCollection);
  }, [mapLoaded, selectedId, selectedDetail, selectedPoint]);

  useEffect(() => {
    if (!mapLoaded) return;
    const map = mapRef.current;
    if (!map) return;
    // Guard: the custom layer only exists after setup runs on a vector basemap;
    // on aerial it never exists and an unguarded call would throw.
    if (map.getLayer("3d-buildings")) {
      map.setLayoutProperty(
        "3d-buildings",
        "visibility",
        layerToggles.buildings ? "visible" : "none",
      );
    }
    refreshMassingCells();
  }, [mapLoaded, layerToggles.buildings, refreshMassingCells]);

  const basemap = useStore((s) => s.basemap);

  useEffect(() => {
    if (!mapLoaded) return;
    const map = mapRef.current;
    if (!map) return;
    if (basemapRef.current === basemap) return;
    basemapRef.current = basemap;
    const style = BASE_STYLES[basemap];
    setupDoneRef.current = false;
    massingActiveRef.current.clear();
    map.setStyle(style as never, { diff: false });
    // Re-run setup once the new style has fully rendered. 'styledata' fires
    // while the style is still loading; 'idle' fires after rendering settles,
    // so custom layers and massing can be re-added safely.
    const reinit = () => {
      if (!setupDoneRef.current) {
        try {
          setupLayersFnRef.current?.();
        } catch (error) {
          console.warn("MapView: style re-init failed", error);
        }
      }
      refreshMassingCells();
    };
    map.once("idle", reinit);
    // If 'load' re-fires for the new style it re-runs setupCustomLayers
    // directly; 'idle' covers the case where it does not.
  }, [mapLoaded, basemap, refreshMassingCells]);

  const fitEvidenceBounds = useCallback(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;
    const geometries: (GeoJSONGeometry | null | undefined)[] = [
      selectedDetail?.restriction_geometry,
      ...selectedMatches.map((m) => m.geometry),
    ];
    let bounds = geometriesBounds(geometries);
    if (!bounds && selectedPoint) {
      bounds = [
        selectedPoint[0] - 0.005,
        selectedPoint[1] - 0.005,
        selectedPoint[0] + 0.005,
        selectedPoint[1] + 0.005,
      ];
    }
    if (bounds) {
      easeToBounds(map, bounds as LngLatBoundsLike, {
        padding: { top: 140, bottom: 120, left: 400, right: 420 },
        maxZoom: 15,
      });
    }
  }, [mapLoaded, selectedDetail, selectedMatches, selectedPoint]);

  useEffect(() => {
    if (!mapLoaded || !points.length) return;
    if (didInitialFitRef.current) return;
    didInitialFitRef.current = true;
    const map = mapRef.current;
    if (!map) return;
    const bounds = geometriesBounds(
      points.map((p) => ({ type: "Point" as const, coordinates: p.coordinates })),
    );
    if (bounds) {
      map.fitBounds(bounds, { padding: 60, maxZoom: 12, duration: 1200, pitch: 0, bearing: 0 });
    }
  }, [mapLoaded, points]);

  const fitEvidenceBoundsRef = useRef(fitEvidenceBounds);
  fitEvidenceBoundsRef.current = fitEvidenceBounds;

  const lastFocusedRef = useRef<{ id: string | null; withDetail: boolean }>({
    id: null,
    withDetail: false,
  });

  useEffect(() => {
    if (!mapLoaded || !selectedId) return;
    // Focus the camera once per selection change (plus once more when the
    // detail geometry arrives) instead of on every store update — repeated
    // focus animations stack and shake the map.
    const hasDetail =
      !!selectedDetail && selectedDetail.restriction_id === selectedId;
    const last = lastFocusedRef.current;
    if (last.id === selectedId && (last.withDetail || !hasDetail)) return;
    lastFocusedRef.current = { id: selectedId, withDetail: hasDetail };
    const timer = setTimeout(() => fitEvidenceBoundsRef.current(), 350);
    return () => clearTimeout(timer);
  }, [mapLoaded, selectedId, selectedDetail]);

  useEffect(() => {
    if (!mapLoaded) return;
    fitEvidenceBounds();
  }, [cameraSignals.fitEvidence, mapLoaded, fitEvidenceBounds]);

  useEffect(() => {
    if (!mapLoaded || !points.length) return;
    const map = mapRef.current;
    if (!map) return;
    const bounds = geometriesBounds(
      points.map((p) => ({ type: "Point" as const, coordinates: p.coordinates })),
    );
    if (bounds) {
      easeToBounds(map, bounds, {
        padding: 60,
        maxZoom: 12,
        duration: 1100,
        pitch: 0,
        bearing: 0,
      });
    }
  }, [cameraSignals.resetView, mapLoaded, points]);

  useEffect(() => {
    if (!mapLoaded) return;
    const map = mapRef.current;
    if (!map) return;
    markerRef.current?.remove();
    markerRef.current = null;
    if (!predictionLocation) return;
    const el = document.createElement("div");
    el.className = "prediction-marker";
    const label = document.createElement("span");
    label.textContent = "ML";
    el.appendChild(label);
    markerRef.current = new Marker({ element: el })
      .setLngLat(predictionLocation)
      .addTo(map);
  }, [mapLoaded, predictionLocation]);

  useEffect(() => {
    if (!mapLoaded || isWalking) return;
    const map = mapRef.current;
    if (!map) return;
    if (groundView) {
      // Engaging ground view from far out must also zoom in, or no buildings
      // (min zoom 13.5) render and the tilted view looks empty.
      const currentZoom = map.getZoom();
      map.easeTo({
        pitch: 60,
        ...(currentZoom < 15 ? { zoom: 16.2 } : {}),
        duration: 1400,
      });
    } else {
      map.easeTo({ pitch: 0, duration: 1200 });
    }
  }, [groundView, mapLoaded, isWalking]);

  const stopWalkEngine = useCallback(() => {
    if (walkRafRef.current) {
      cancelAnimationFrame(walkRafRef.current);
      walkRafRef.current = 0;
    }
    setWalkProgress(null);
    setIsWalking(false);
  }, [setIsWalking]);

  const fitRouteBounds = useCallback(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !route) return;
    const geometries: { type: "LineString"; coordinates: number[][] }[] = [];
    if (route.baseline?.geometry?.type === "LineString") {
      geometries.push(route.baseline.geometry as { type: "LineString"; coordinates: number[][] });
    }
    if (route.recommended?.geometry?.type === "LineString") {
      geometries.push(route.recommended.geometry as { type: "LineString"; coordinates: number[][] });
    }
    if (routeOrigin) {
      geometries.push({ type: "LineString", coordinates: [routeOrigin, routeOrigin] });
    }
    if (routeDestination) {
      geometries.push({ type: "LineString", coordinates: [routeDestination, routeDestination] });
    }
    const bounds = geometriesBounds(geometries);
    if (bounds) {
      easeToBounds(map, bounds, {
        padding: { top: 140, bottom: 160, left: 420, right: 420 },
        maxZoom: 15,
      });
    }
  }, [mapLoaded, route, routeOrigin, routeDestination]);

  const startWalkEngine = useCallback(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    let path: [number, number][] | null = null;

    if (walkOverridePath && walkOverridePath.length >= 2) {
      path = walkOverridePath;
    } else if (selectedPoint && matchGeometries.length) {
      const ordered: [number, number][][] = [];
      const remaining = matchGeometries.map((g) => {
        const pts: number[][] = [];
        flattenCoords(g.coordinates, pts);
        return pts as [number, number][];
      });
      let cursor: [number, number] = selectedPoint;
      while (remaining.length) {
        let bestIdx = 0;
        let bestDist = Infinity;
        remaining.forEach((p, i) => {
          if (!p.length) return;
          const d = approxDistanceMeters(cursor, p[0]);
          if (d < bestDist) {
            bestDist = d;
            bestIdx = i;
          }
        });
        const next = remaining.splice(bestIdx, 1)[0];
        ordered.push(next);
        if (next.length) cursor = next[next.length - 1];
      }

      const concatenated: [number, number][] = [];
      for (const seg of ordered) {
        for (const pt of seg) {
          const last = concatenated[concatenated.length - 1];
          if (!last || last[0] !== pt[0] || last[1] !== pt[1]) {
            concatenated.push(pt);
          }
        }
      }
      path = concatenated.length >= 2 ? concatenated : null;
    }

    if (!path) return;

    stopWalkEngine();

    const cumulative: number[] = [0];
    for (let i = 1; i < path.length; i++) {
      cumulative.push(cumulative[i - 1] + approxDistanceMeters(path[i - 1], path[i]));
    }
    const totalMeters = cumulative[cumulative.length - 1];
    const durationMs = Math.min(75000, Math.max(15000, (totalMeters / 3.5) * 1000));

    setIsWalking(true);
    walkBearingRef.current = bearingDegrees(path![0], path![1]);

    // Descent pre-roll: glide from the current bird's-eye view down to street
    // level at the route start before movement begins, so surroundings load.
    const descentMs = 2800;
    map.flyTo({
      center: path![0],
      zoom: 16.6,
      pitch: 65,
      bearing: walkBearingRef.current,
      duration: descentMs,
      curve: 1.15,
    });

    const start = performance.now();
    const walkingRoute = Boolean(walkOverridePath);
    const walkEvents: WalkEvent[] = walkingRoute
      ? (useStore.getState().route?.recommended?.walk_events ??
        useStore.getState().route?.baseline?.walk_events ??
        [])
      : [];

    const step = (now: number) => {
      const elapsed = now - start;
      if (elapsed < descentMs) {
        const initial = walkContext(walkEvents, 0);
        setWalkProgress({ distance: 0, total: totalMeters, pct: 0, sidewalk: initial.sidewalk, next: initial.next });
        walkRafRef.current = requestAnimationFrame(step);
        return;
      }
      const t = Math.min(1, (elapsed - descentMs) / durationMs);
      const targetDist = totalMeters * t;

      let i = 1;
      while (i < cumulative.length - 1 && cumulative[i] < targetDist) i++;
      const segStart = cumulative[i - 1];
      const segLen = cumulative[i] - segStart || 1;
      const f = Math.max(0, Math.min(1, (targetDist - segStart) / segLen));
      const pos = lerpPt(path![i - 1], path![i], f);
      const targetBearing = bearingDegrees(path![i - 1], path![i]);
      let dBearing = targetBearing - walkBearingRef.current;
      if (dBearing > 180) dBearing -= 360;
      if (dBearing < -180) dBearing += 360;
      walkBearingRef.current = (walkBearingRef.current + dBearing * 0.25 + 360) % 360;

      map.jumpTo({ center: pos, zoom: 16.6, pitch: 65, bearing: walkBearingRef.current });
      const ctx = walkContext(walkEvents, targetDist);
      setWalkProgress({ distance: targetDist, total: totalMeters, pct: t * 100, sidewalk: ctx.sidewalk, next: ctx.next });

      if (t < 1) {
        walkRafRef.current = requestAnimationFrame(step);
      } else {
        walkRafRef.current = 0;
        setWalkProgress(null);
        setIsWalking(false);
        setTimeout(() => {
          if (walkingRoute) fitRouteBounds();
          else fitEvidenceBounds();
        }, 400);
      }
    };

    walkRafRef.current = requestAnimationFrame(step);
  }, [mapLoaded, walkOverridePath, selectedPoint, matchGeometries, stopWalkEngine, setIsWalking, fitEvidenceBounds, fitRouteBounds]);

  useEffect(() => {
    if (walkSignals.start === 0) return;
    const store = useStore.getState();
    if (!store.layerToggles.buildings) {
      store.setLayerToggle("buildings", true);
    }
    startWalkEngine();
  }, [walkSignals.start, startWalkEngine]);

  useEffect(() => {
    if (walkSignals.stop === 0) return;
    stopWalkEngine();
  }, [walkSignals.stop, stopWalkEngine]);

  useEffect(() => {
    if (!selectedId && !walkOverridePath) stopWalkEngine();
  }, [selectedId, walkOverridePath, stopWalkEngine]);

  useEffect(() => () => stopWalkEngine(), [stopWalkEngine]);

  useEffect(() => {
    if (!mapLoaded || !route) return;
    const timer = setTimeout(() => fitRouteBounds(), 200);
    return () => clearTimeout(timer);
  }, [mapLoaded, route, fitRouteBounds]);

  const routeWalkable = useMemo(() => {
    const geometry = route?.recommended?.geometry ?? route?.baseline?.geometry;
    return Boolean(geometry && geometry.type === "LineString" && (geometry.coordinates as number[][]).length >= 2);
  }, [route]);

  const handleWalkRoute = useCallback(() => {
    const geometry = route?.recommended?.geometry ?? route?.baseline?.geometry;
    if (!geometry || geometry.type !== "LineString") return;
    const coords = geometry.coordinates as [number, number][];
    if (coords.length < 2) return;
    setWalkOverridePath(coords);
    startWalk();
  }, [route, setWalkOverridePath, startWalk]);

  useEffect(() => {
    if (!mapLoaded || !routeOrigin || !routeDestination) return;
    if (route) return;
    const map = mapRef.current;
    if (!map) return;
    const bounds: LngLatBoundsLike = [
      Math.min(routeOrigin[0], routeDestination[0]),
      Math.min(routeOrigin[1], routeDestination[1]),
      Math.max(routeOrigin[0], routeDestination[0]),
      Math.max(routeOrigin[1], routeDestination[1]),
    ];
    easeToBounds(map, bounds, {
      padding: { top: 140, bottom: 160, left: 420, right: 420 },
      maxZoom: 15,
    });
  }, [mapLoaded, routeOrigin, routeDestination, route]);

  const rotateMap = useCallback((delta: number) => {
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({ bearing: map.getBearing() + delta, duration: 450 });
  }, []);

  const tiltMap = useCallback((delta: number) => {
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({ pitch: Math.max(0, Math.min(80, map.getPitch() + delta)), duration: 450 });
  }, []);

  const resetOrientation = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({ bearing: 0, pitch: 0, duration: 600 });
  }, []);

  return (
    <>
      <div ref={containerRef} className="maplibre-canvas" />
      <div className="camera-controls" aria-label="Camera angle controls">
        <button onClick={() => rotateMap(-45)} title="Rotate view left (or right-drag the map)">↺</button>
        <button onClick={() => rotateMap(45)} title="Rotate view right (or right-drag the map)">↻</button>
        <button onClick={() => tiltMap(-15)} title="Tilt toward top-down">⌃</button>
        <button onClick={() => tiltMap(15)} title="Tilt toward street level">⌄</button>
        <button onClick={resetOrientation} title="Reset to north-up, top-down">N</button>
      </div>
      {walkProgress && (
        <div className="walk-progress-overlay">
          <div className="walk-stat">
            <span className="walk-stat-label">Distance</span>
            <span className="walk-stat-value">{Math.round(walkProgress.distance)}m / {Math.round(walkProgress.total)}m</span>
          </div>
          <div className="walk-bar">
            <div className="walk-bar-fill" style={{ width: `${walkProgress.pct}%` }} />
          </div>
          <div className="walk-stat">
            <span className="walk-stat-label">Progress</span>
            <span className="walk-stat-value">{Math.round(walkProgress.pct)}%</span>
          </div>
          {walkProgress.sidewalk && (
            <div className="walk-stat">
              <span className="walk-stat-label">Surface</span>
              <span className="walk-stat-value">{walkProgress.sidewalk}</span>
            </div>
          )}
          {walkProgress.next && (
            <div className="walk-stat">
              <span className="walk-stat-label">Ahead</span>
              <span className="walk-stat-value">
                {walkProgress.next.label} in {Math.max(0, Math.round(walkProgress.next.at_m - walkProgress.distance))}m
              </span>
            </div>
          )}
          {activeRouteCoords && routeCumulative && (() => {
            const passed = routePois.filter((poi) => {
              const [plng, plat] = poi.geometry.coordinates;
              return activeRouteCoords.some((v, i) => {
                if (i === 0) return false;
                const d = routeCumulative[i];
                return d <= walkProgress.distance && approxDistanceMeters(v, [plng, plat]) <= POI_ROUTE_PROXIMITY_M;
              });
            }).length;
            return passed > 0 ? (
              <div className="walk-stat">
                <span className="walk-stat-label">Passed</span>
                <span className="walk-stat-value">{passed} amenit{passed === 1 ? "y" : "ies"}</span>
              </div>
            ) : null;
          })()}
          <button className="walk-stop-btn" onClick={stopWalkEngine}>■ Stop</button>
        </div>
      )}
      {route && !isWalking && routeWalkable && (
        <button className="map-walk-fab" onClick={handleWalkRoute} title="Street-level walkthrough of this route">
          ▶ Walk this route
        </button>
      )}
      {route && isWalking && (
        <button className="map-walk-fab stopping" onClick={stopWalkEngine} title="Stop the street-level walkthrough">
          ■ Stop walk
        </button>
      )}
    </>
  );
}
