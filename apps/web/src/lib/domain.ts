import type {
  AnalyticsSummaryResponse,
  ConsoleDataState,
  DataMode,
  DataStatus,
  GeoJSONGeometry,
  HealthResponse,
  MapFeature,
  MatchMapped,
  MatchResponse,
  NetworkImpactMapped,
  NetworkImpactResponse,
  OverviewMetrics,
  RestrictionDetailMapped,
  RestrictionDetailResponse,
  RestrictionListItem,
  RestrictionSummaryResponse,
  SpatialMapped,
  SpatialResponse,
} from "./types";

const EVIDENCE_STATES = [
  "HIGH",
  "MEDIUM",
  "LOW",
  "INSUFFICIENT_EVIDENCE",
  "NOT_EVALUATED",
] as const;

export function coerceMetricValue(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const asNumber = Number(value);
  return Number.isFinite(asNumber) ? asNumber : null;
}

export function buildOverviewMetrics(
  summary: AnalyticsSummaryResponse | null,
  restrictions: RestrictionListItem[] = [],
): OverviewMetrics {
  const totalRestrictions = Number.isFinite(
    Number(summary?.total_restrictions_represented),
  )
    ? Number(summary!.total_restrictions_represented)
    : restrictions.length;
  const evaluatedRestrictions = Number.isFinite(
    Number(summary?.evaluated_restrictions),
  )
    ? Number(summary!.evaluated_restrictions)
    : restrictions.filter((item) => item.impact_evaluable === true).length;
  const evaluationStatusDistribution =
    summary?.evaluation_status_distribution ?? {};
  const evidenceConfidenceDistribution =
    summary?.evidence_confidence_distribution ?? {};
  const impactSeverityDistribution =
    summary?.impact_severity_distribution ?? {};

  const replacementPathRows = restrictions.filter(
    (item) =>
      item.replacement_path_available === true ||
      item.replacement_path_state === "AVAILABLE",
  );

  return {
    totalRestrictions,
    evaluatedRestrictions,
    notEvaluatedCount: Math.max(totalRestrictions - evaluatedRestrictions, 0),
    evaluationStatusDistribution,
    evidenceConfidenceDistribution,
    impactSeverityDistribution,
    replacementPathAvailability: replacementPathRows.length,
  };
}

interface FilterSortOptions {
  query?: string;
  evaluationStatus?: string;
  evidenceConfidence?: string;
  matchType?: string;
  impactSeverity?: string;
  sortKey?: string;
  direction?: "asc" | "desc";
}

export function filterAndSortRestrictions(
  items: RestrictionListItem[] = [],
  options: FilterSortOptions = {},
): RestrictionListItem[] {
  const {
    query = "",
    evaluationStatus = "",
    evidenceConfidence = "",
    matchType = "",
    impactSeverity = "",
    sortKey = "restriction_id",
    direction = "asc",
  } = options;

  const filtered = items.filter((item) => {
    const restrictionId = (item.restriction_id ?? "").toLowerCase();
    const location = item.location ?? null;
    const haystack = [
      restrictionId,
      item.evaluation_status ?? "",
      item.evidence_confidence ?? "",
      item.impact_severity ?? "",
      item.match_type ?? "",
      location?.road ?? "",
      location?.name ?? "",
      location?.from_road ?? "",
      location?.to_road ?? "",
    ]
      .join(" ")
      .toLowerCase();

    const matchesQuery = !query || haystack.includes(query.toLowerCase());
    const matchesEvaluation =
      !evaluationStatus || item.evaluation_status === evaluationStatus;
    const matchesEvidence =
      !evidenceConfidence || item.evidence_confidence === evidenceConfidence;
    const matchesImpact =
      !impactSeverity || item.impact_severity === impactSeverity;
    const matchesMatchType = !matchType || item.match_type === matchType;

    return (
      matchesQuery &&
      matchesEvaluation &&
      matchesEvidence &&
      matchesImpact &&
      matchesMatchType
    );
  });

  const multiplier = direction === "desc" ? -1 : 1;

  filtered.sort((left, right) => {
    const leftValue =
      (left as unknown as Record<string, unknown>)[sortKey] ?? "";
    const rightValue =
      (right as unknown as Record<string, unknown>)[sortKey] ?? "";

    if (typeof leftValue === "number" && typeof rightValue === "number") {
      return (leftValue - rightValue) * multiplier;
    }

    return String(leftValue).localeCompare(String(rightValue)) * multiplier;
  });

  return filtered;
}

export function mapRestrictionList(
  response: { items?: RestrictionSummaryResponse[] } | null | undefined,
): RestrictionListItem[] {
  const items = Array.isArray(response?.items) ? response!.items : [];
  return items.map((item) => ({
    restriction_id: item.restriction_id,
    evaluation_status: item.evaluation_status,
    impact_severity: item.impact_severity,
    evidence_confidence: item.evidence_confidence,
    candidate_edge_count: Number(item.candidate_edge_count ?? 0),
    impact_evaluable: Boolean(item.impact_evaluable),
    source_snapshot: item.provenance?.source_snapshot ?? null,
    match_type: item.match_type ?? null,
    replacement_path_available: false,
    replacement_path_state: "UNAVAILABLE",
    coordinates: item.coordinates ?? null,
    location: item.location ?? null,
    duration_hours: item.duration_hours ?? null,
  }));
}

export function mapRestrictionDetail(
  response: RestrictionDetailResponse,
): RestrictionDetailMapped {
  return {
    restriction_id: response.restriction_id,
    evaluation_status: response.evaluation_status,
    impact_severity: response.impact_severity,
    evidence_confidence: response.evidence_confidence,
    impact_evaluable: Boolean(response.impact_evaluable),
    candidate_edge_count: Number(response.candidate_edge_count ?? 0),
    valid_restriction_polyline: Boolean(response.valid_restriction_polyline),
    fallback_geometry_used: Boolean(response.fallback_geometry_used),
    duration_hours: coerceMetricValue(response.duration_hours),
    reason_codes: Array.isArray(response.reason_codes)
      ? response.reason_codes
      : [],
    limitations: Array.isArray(response.limitations)
      ? response.limitations
      : [],
    restriction_geometry: response.restriction_geometry ?? null,
    provenance: response.provenance ?? null,
    source_snapshot: response.provenance?.source_snapshot ?? null,
    source_publisher: response.provenance?.publisher ?? null,
    temporal_information: null,
  };
}

interface SpatialFeatureResponseLike {
  feature_id: string;
  geometry: GeoJSONGeometry | null;
  match_type: string;
  confidence: string;
  distance_m: number | null;
  source: string | null;
  candidate_rank: number | null;
  candidate_status: string;
}

export function mapMatches(
  response: MatchResponse[] | SpatialFeatureResponseLike[] = [],
): MatchMapped[] {
  return Array.isArray(response)
    ? response.map((item) => ({
        pedestrian_feature_id:
          (item as MatchResponse).pedestrian_feature_id ??
          (item as SpatialFeatureResponseLike).feature_id,
        match_type: item.match_type,
        evidence_confidence:
          (item as MatchResponse).evidence_confidence ??
          (item as SpatialFeatureResponseLike).confidence,
        distance_m: coerceMetricValue(item.distance_m),
        candidate_status: item.candidate_status ?? "CANDIDATE_AFFECTED_SEGMENT",
        geometry: item.geometry ?? null,
      }))
    : [];
}

export function mapNetworkImpact(
  response: NetworkImpactResponse[] = [],
): NetworkImpactMapped[] {
  return Array.isArray(response)
    ? response.map((item) => ({
        scenario: item.scenario,
        evaluation_status: item.evaluation_status,
        candidate_edge_count: Number(item.candidate_edge_count ?? 0),
        evaluated_edge_count: Number(item.evaluated_edge_count ?? 0),
        alternative_path_edge_count: Number(
          item.alternative_path_edge_count ?? 0,
        ),
        local_connectivity_loss_count: Number(
          item.local_connectivity_loss_count ?? 0,
        ),
        local_connectivity_loss_fraction: coerceMetricValue(
          item.local_connectivity_loss_fraction,
        ),
        median_replacement_ratio: coerceMetricValue(
          item.median_replacement_ratio,
        ),
        max_replacement_ratio: coerceMetricValue(item.max_replacement_ratio),
        median_added_replacement_distance_m: coerceMetricValue(
          item.median_added_replacement_distance_m,
        ),
        max_added_replacement_distance_m: coerceMetricValue(
          item.max_added_replacement_distance_m,
        ),
        set_evaluation_status: item.set_evaluation_status,
        limitations: Array.isArray(item.limitations) ? item.limitations : [],
      }))
    : [];
}

export function mapSpatialResponse(
  response: SpatialResponse | null | undefined,
): SpatialMapped {
  const safe = response ?? ({} as Partial<SpatialResponse>);
  const mapFeature = (item: SpatialFeatureResponseLike): MatchMapped => ({
    pedestrian_feature_id: item.feature_id,
    match_type: item.match_type,
    evidence_confidence: item.confidence,
    distance_m: coerceMetricValue(item.distance_m),
    candidate_status: item.candidate_status,
    geometry: item.geometry,
  });

  return {
    restrictionId: safe.restriction_id ?? null,
    restrictionGeometry: safe.restriction_geometry ?? null,
    geometryStatus: safe.geometry_status ?? "NOT_AVAILABLE",
    crs: safe.crs ?? null,
    provenance: safe.provenance ?? null,
    matchedFeatures: (safe.matched_features ?? []).map(mapFeature),
    candidateFeatures: (safe.candidate_features ?? []).map(mapFeature),
  };
}

export function formatMissing(
  value: unknown,
  label = "Not available from current API artifact.",
): string {
  return value === null || value === undefined || value === ""
    ? label
    : String(value);
}

interface ConsoleDataStateInput {
  apiData: {
    health: HealthResponse | null;
    summary: AnalyticsSummaryResponse | null;
    restrictions: RestrictionListItem[];
  } | null;
  apiError: Error | null;
  demoData: DemoData | null;
}

interface DemoData {
  demo: boolean;
  health: HealthResponse;
  summary: AnalyticsSummaryResponse;
  restrictions: RestrictionListItem[];
  details: Record<string, RestrictionDetailResponse>;
  matches: Record<string, MatchResponse[]>;
  impacts: Record<string, NetworkImpactResponse[]>;
}

export function getConsoleDataState({
  apiData,
  apiError,
  demoData,
}: ConsoleDataStateInput): ConsoleDataState {
  if (apiData) {
    return {
      mode: "live" as DataMode,
      status: "ready" as DataStatus,
      data: apiData,
      message: null,
    };
  }
  if (demoData) {
    return {
      mode: "demo" as DataMode,
      status: "api-unavailable" as DataStatus,
      data: {
        health: demoData.health,
        summary: demoData.summary,
        restrictions: demoData.restrictions,
        details: demoData.details,
        matches: demoData.matches,
        impacts: demoData.impacts,
        demo: true,
      },
      message: "Live API unavailable. Showing deterministic demo/sample data.",
    };
  }
  return {
    mode: "empty" as DataMode,
    status: apiError ? ("api-unavailable" as DataStatus) : ("empty" as DataStatus),
    data: null,
    message: apiError
      ? "Live API unavailable and no demo data is configured."
      : "No records returned by the current API artifact.",
  };
}

export function isUsableGeoJson(
  geometry: unknown,
): geometry is GeoJSONGeometry {
  return Boolean(
    geometry &&
      typeof geometry === "object" &&
      typeof (geometry as GeoJSONGeometry).type === "string" &&
      (geometry as GeoJSONGeometry).coordinates,
  );
}

interface BuildMapFeaturesInput {
  restrictions?: RestrictionListItem[];
  details?: Record<string, RestrictionDetailMapped | RestrictionDetailResponse>;
  matches?: Record<string, MatchMapped[]>;
}

export function buildMapFeatures({
  restrictions = [],
  details = {},
  matches = {},
}: BuildMapFeaturesInput): MapFeature[] {
  return restrictions.flatMap((restriction) => {
    const detail = details[restriction.restriction_id] ?? {};
    const restrictionGeometry = isUsableGeoJson(
      (detail as RestrictionDetailMapped).restriction_geometry ??
        (detail as RestrictionDetailResponse).restriction_geometry,
    )
      ? [
          {
            restrictionId: restriction.restriction_id,
            kind: "restriction" as const,
            evidenceConfidence: restriction.evidence_confidence,
            evaluationStatus: restriction.evaluation_status,
            matchType: restriction.match_type,
            durationHours: restriction.duration_hours,
            geometry: (
              (detail as RestrictionDetailMapped).restriction_geometry ??
              (detail as RestrictionDetailResponse).restriction_geometry
            ) as GeoJSONGeometry,
          },
        ]
      : [];
    const matchFeatures = (matches[restriction.restriction_id] ?? [])
      .filter((match) => isUsableGeoJson(match.geometry))
      .map((match) => ({
        restrictionId: restriction.restriction_id,
        kind:
          match.match_type === "INTERSECTS" ||
          match.match_type === "direct_intersection"
            ? ("direct-match" as const)
            : ("proximity-match" as const),
        evidenceConfidence: match.evidence_confidence,
        evaluationStatus: restriction.evaluation_status,
        matchType: match.match_type,
        durationHours: null,
        geometry: match.geometry as GeoJSONGeometry,
      }));
    return [...restrictionGeometry, ...matchFeatures];
  });
}

export function evidenceStateLabel(value: string | null | undefined): string {
  return EVIDENCE_STATES.includes(value as (typeof EVIDENCE_STATES)[number])
    ? value!
    : "UNKNOWN";
}

export function resolveMapSelection(
  restrictionId: string | null,
  visibleRestrictions: RestrictionListItem[] = [],
): string | null {
  return visibleRestrictions.some(
    (item) => item.restriction_id === restrictionId,
  )
    ? restrictionId
    : null;
}

export function buildMapFeaturesFromCoordinates(
  restrictions: RestrictionListItem[],
): MapFeature[] {
  return restrictions
    .filter((r) => r.coordinates && r.coordinates.length === 2)
    .map((r) => ({
      restrictionId: r.restriction_id,
      kind: "restriction" as const,
      evidenceConfidence: r.evidence_confidence,
      evaluationStatus: r.evaluation_status,
      matchType: r.match_type,
      durationHours: r.duration_hours,
      geometry: {
        type: "Point" as const,
        coordinates: r.coordinates!,
      },
    }));
}
