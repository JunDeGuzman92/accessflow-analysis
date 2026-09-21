import type {
  AnalyticsSummaryResponse,
  ExplanationResponse,
  HealthResponse,
  NetworkImpactResponse,
  PredictionRequest,
  PredictionResponse,
  RestrictionDetailResponse,
  RestrictionPage,
  RouteResponse,
  SpatialResponse,
} from "./types";

export const API_BASE_URL: string =
  typeof globalThis !== "undefined" &&
  (globalThis as Record<string, unknown>).ACCESSFLOW_API_BASE_URL
    ? (globalThis as Record<string, unknown>).ACCESSFLOW_API_BASE_URL as string
    : "";

/** Martin tile server TileJSON endpoint for the city-wide 3D Massing layer.
 *  Uses 127.0.0.1 (like the API URL) rather than the `localhost` name, which
 *  some proxies and IPv6-first resolvers mishandle. */
export const MASSING_TILE_URL: string =
  typeof globalThis !== "undefined" &&
  (globalThis as Record<string, unknown>).ACCESSFLOW_TILE_URL
    ? (globalThis as Record<string, unknown>).ACCESSFLOW_TILE_URL as string
    : "http://127.0.0.1:3002/massing";

export async function fetchJson<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const requestUrl = url.startsWith("http") ? url : `${API_BASE_URL}${url}`;
  const response = await fetch(requestUrl, {
    headers: { Accept: "application/json" },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Request failed (${response.status}): ${detail || requestUrl}`);
  }

  return response.json() as Promise<T>;
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/health");
}

export interface MassingManifest {
  schema: string;
  cell_size: [number, number];
  clip: [number, number, number, number];
  cells: Record<string, [number, number, number, number]>;
  building_count: number;
  provenance: Record<string, string>;
}

export async function getMassingManifest(): Promise<MassingManifest> {
  return fetchJson<MassingManifest>("/api/v1/massing/manifest");
}

export async function getMassingCell(cell: string): Promise<unknown> {
  return fetchJson<unknown>(`/api/v1/massing/${encodeURIComponent(cell)}`);
}

export interface PoiFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    kind: string;
    name: string;
    details?: string | null;
    accessible?: string | null;
  };
}

export interface PoiCollection {
  type: "FeatureCollection";
  features: PoiFeature[];
}

export async function getPois(): Promise<PoiCollection> {
  return fetchJson<PoiCollection>("/api/v1/pois");
}

export async function getRestrictions(
  params: Record<string, string | number | undefined> = {},
): Promise<RestrictionPage> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  const url = query ? `/api/v1/restrictions?${query}` : "/api/v1/restrictions";
  return fetchJson<RestrictionPage>(url);
}

export async function getRestriction(
  restrictionId: string,
): Promise<RestrictionDetailResponse> {
  return fetchJson<RestrictionDetailResponse>(
    `/api/v1/restrictions/${encodeURIComponent(restrictionId)}`,
  );
}

export async function getRestrictionSpatial(
  restrictionId: string,
): Promise<SpatialResponse> {
  return fetchJson<SpatialResponse>(
    `/api/v1/restrictions/${encodeURIComponent(restrictionId)}/spatial`,
  );
}

export async function getRestrictionNetworkImpact(
  restrictionId: string,
): Promise<NetworkImpactResponse[]> {
  return fetchJson<NetworkImpactResponse[]>(
    `/api/v1/restrictions/${encodeURIComponent(restrictionId)}/network-impact`,
  );
}

export async function getAnalyticsSummary(): Promise<AnalyticsSummaryResponse> {
  return fetchJson<AnalyticsSummaryResponse>("/api/v1/analytics/summary");
}

export async function predictImpact(
  request: PredictionRequest,
): Promise<PredictionResponse> {
  return fetchJson<PredictionResponse>("/api/v1/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function getRoute(
  origin: [number, number],
  destination: [number, number],
  avoid: string | null,
): Promise<RouteResponse> {
  const params = new URLSearchParams({
    origin: `${origin[0]},${origin[1]}`,
    destination: `${destination[0]},${destination[1]}`,
  });
  if (avoid) {
    params.set("avoid", avoid);
  }
  return fetchJson<RouteResponse>(`/api/v1/route?${params.toString()}`);
}

export async function getExplanation(params: {
  restriction_id?: string;
  origin?: [number, number];
  destination?: [number, number];
  avoid?: string | null;
  overview?: boolean;
}): Promise<ExplanationResponse> {
  const search = new URLSearchParams();
  if (params.restriction_id) search.set("restriction_id", params.restriction_id);
  if (params.origin) search.set("origin", `${params.origin[0]},${params.origin[1]}`);
  if (params.destination) search.set("destination", `${params.destination[0]},${params.destination[1]}`);
  if (params.avoid) search.set("avoid", params.avoid);
  if (params.overview) search.set("overview", "true");
  return fetchJson<ExplanationResponse>(`/api/v1/ai/explain?${search.toString()}`);
}
