export type GeometryType = "Point" | "LineString" | "MultiLineString";

export interface GeoJSONGeometry {
  type: GeometryType;
  coordinates: number[] | number[][] | number[][][];
}

export type EvidenceConfidence =
  | "HIGH"
  | "MEDIUM"
  | "LOW"
  | "INSUFFICIENT_EVIDENCE"
  | "NOT_EVALUATED";

export type ImpactSeverity =
  | "SEVERE"
  | "HIGH"
  | "MODERATE"
  | "LOW"
  | "NOT_EVALUATED";

export type GeometryStatus = "AVAILABLE" | "PARTIAL" | "NOT_AVAILABLE";

export interface Provenance {
  publisher: string;
  analytical_status: string;
  methodology_version: string;
  source_snapshot: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
}

export interface RestrictionLocation {
  road: string | null;
  name: string | null;
  from_road: string | null;
  to_road: string | null;
}

export interface RestrictionSummaryResponse {
  restriction_id: string;
  evaluation_status: string;
  impact_severity: string;
  evidence_confidence: string;
  candidate_edge_count: number;
  impact_evaluable: boolean;
  provenance: Provenance;
  coordinates: number[] | null;
  location: RestrictionLocation | null;
  match_type: string | null;
  duration_hours: number | null;
}

export interface RestrictionDetailResponse extends RestrictionSummaryResponse {
  valid_restriction_polyline: boolean;
  fallback_geometry_used: boolean;
  duration_hours: number | null;
  reason_codes: string[];
  limitations: string[];
  restriction_geometry: GeoJSONGeometry | null;
}

export interface MatchResponse {
  pedestrian_feature_id: string;
  match_type: string;
  evidence_confidence: string;
  distance_m: number | null;
  candidate_status: string;
  geometry: GeoJSONGeometry | null;
}

export interface SpatialFeatureResponse {
  feature_id: string;
  geometry: GeoJSONGeometry | null;
  match_type: string;
  confidence: string;
  distance_m: number | null;
  source: string | null;
  candidate_rank: number | null;
  candidate_status: string;
}

export interface SpatialResponse {
  restriction_id: string;
  restriction_geometry: GeoJSONGeometry | null;
  matched_features: SpatialFeatureResponse[];
  candidate_features: SpatialFeatureResponse[];
  crs: string;
  evidence_confidence: string;
  geometry_status: GeometryStatus;
  provenance: Provenance;
}

export interface NetworkImpactResponse {
  scenario: string;
  evaluation_status: string;
  candidate_edge_count: number;
  evaluated_edge_count: number;
  alternative_path_edge_count: number;
  local_connectivity_loss_count: number;
  local_connectivity_loss_fraction: number | null;
  median_replacement_ratio: number | null;
  max_replacement_ratio: number | null;
  median_added_replacement_distance_m: number | null;
  max_added_replacement_distance_m: number | null;
  set_evaluation_status: string;
  set_component_increase: number | null;
  set_disconnected_boundary_pair_count: number | null;
  limitations: string[];
  provenance: Provenance;
}

export interface RestrictionPage {
  items: RestrictionSummaryResponse[];
  total: number;
  offset: number;
  limit: number;
}

export interface AnalyticsSummaryResponse {
  total_restrictions_represented: number;
  evaluated_restrictions: number;
  evaluation_status_distribution: Record<string, number>;
  impact_severity_distribution: Record<string, number>;
  evidence_confidence_distribution: Record<string, number>;
  provenance: Provenance;
}

export interface PredictionRequest {
  type: string;
  road_class: string;
  directions_affected: string;
  work_period: string;
  district: string;
  latitude: number;
  longitude: number;
  duration_days: number;
  special_event: string;
}

export interface PredictionResponse {
  prediction: string;
  confidence: number;
  probabilities: Record<string, number>;
}

export interface WalkEvent {
  at_m: number;
  kind: "sidewalk_change" | "crosswalk" | "signal";
  label: string;
}

export interface RoutePath {
  geometry: GeoJSONGeometry | null;
  distance_m: number;
  edge_count: number;
  barriers_on_path: number;
  walk_events: WalkEvent[];
}

export interface RouteComparison {
  added_distance_m: number | null;
  distance_ratio: number | null;
  avoided_barrier_count: number;
}

export interface RouteCharacter {
  sidewalk_counts: Record<string, number>;
  road_type_counts: Record<string, number>;
  crosswalk_count: number;
  pedestrian_signal_count: number;
}

export interface RouteResponse {
  origin: number[];
  destination: number[];
  origin_node: number;
  destination_node: number;
  avoid: string | null;
  baseline: RoutePath;
  recommended: RoutePath | null;
  comparison: RouteComparison | null;
  route_character: RouteCharacter | null;
  reachable: boolean;
  limitations: string[];
  provenance: Provenance;
}

export type RouteAvoidMode = "none" | "selected" | "all";
export type RoutePicking = "origin" | "destination" | null;

export interface ExplanationCitation {
  restriction_id: string | null;
  fields: string[];
}

export interface ExplanationResponse {
  kind: "restriction" | "route" | "overview";
  headline: string;
  narrative: string;
  bullets: string[];
  citations: ExplanationCitation[];
  method: string;
  limitations: string[];
  provenance: Provenance;
}

export interface RestrictionListItem {
  restriction_id: string;
  evaluation_status: string;
  impact_severity: string;
  evidence_confidence: string;
  candidate_edge_count: number;
  impact_evaluable: boolean;
  source_snapshot: string | null;
  match_type: string | null;
  replacement_path_available: boolean;
  replacement_path_state: string;
  coordinates: number[] | null;
  location: RestrictionLocation | null;
  duration_hours: number | null;
}

export interface RestrictionDetailMapped {
  restriction_id: string;
  evaluation_status: string;
  impact_severity: string;
  evidence_confidence: string;
  impact_evaluable: boolean;
  candidate_edge_count: number;
  valid_restriction_polyline: boolean;
  fallback_geometry_used: boolean;
  duration_hours: number | null;
  reason_codes: string[];
  limitations: string[];
  restriction_geometry: GeoJSONGeometry | null;
  provenance: Provenance | null;
  source_snapshot: string | null;
  source_publisher: string | null;
  temporal_information: string | null;
}

export interface MatchMapped {
  pedestrian_feature_id: string;
  match_type: string;
  evidence_confidence: string;
  distance_m: number | null;
  candidate_status: string;
  geometry: GeoJSONGeometry | null;
}

export interface NetworkImpactMapped {
  scenario: string;
  evaluation_status: string;
  candidate_edge_count: number;
  evaluated_edge_count: number;
  alternative_path_edge_count: number;
  local_connectivity_loss_count: number;
  local_connectivity_loss_fraction: number | null;
  median_replacement_ratio: number | null;
  max_replacement_ratio: number | null;
  median_added_replacement_distance_m: number | null;
  max_added_replacement_distance_m: number | null;
  set_evaluation_status: string;
  limitations: string[];
}

export interface SpatialMapped {
  restrictionId: string | null;
  restrictionGeometry: GeoJSONGeometry | null;
  geometryStatus: GeometryStatus;
  crs: string | null;
  provenance: Provenance | null;
  matchedFeatures: MatchMapped[];
  candidateFeatures: MatchMapped[];
}

export type MapFeatureKind = "restriction" | "direct-match" | "proximity-match";

export interface MapFeature {
  restrictionId: string;
  kind: MapFeatureKind;
  evidenceConfidence: string;
  evaluationStatus: string;
  matchType: string | null;
  durationHours: number | null;
  geometry: GeoJSONGeometry;
}

export type DataMode = "live" | "demo" | "empty";
export type DataStatus = "loading" | "ready" | "api-unavailable" | "empty";

export interface ConsoleDataState {
  mode: DataMode;
  status: DataStatus;
  data: {
    health: HealthResponse | null;
    summary: AnalyticsSummaryResponse | null;
    restrictions: RestrictionListItem[];
    details?: Record<string, RestrictionDetailResponse>;
    matches?: Record<string, MatchResponse[]>;
    impacts?: Record<string, NetworkImpactResponse[]>;
    demo?: boolean;
  } | null;
  message: string | null;
}

export interface OverviewMetrics {
  totalRestrictions: number;
  evaluatedRestrictions: number;
  notEvaluatedCount: number;
  evaluationStatusDistribution: Record<string, number>;
  evidenceConfidenceDistribution: Record<string, number>;
  impactSeverityDistribution: Record<string, number>;
  replacementPathAvailability: number;
}
