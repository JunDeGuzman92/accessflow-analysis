import type {
  AnalyticsSummaryResponse,
  HealthResponse,
  MatchResponse,
  NetworkImpactResponse,
  RestrictionDetailResponse,
  RestrictionListItem,
} from "./types";

interface DemoData {
  demo: boolean;
  health: HealthResponse;
  summary: AnalyticsSummaryResponse;
  restrictions: RestrictionListItem[];
  details: Record<string, RestrictionDetailResponse>;
  matches: Record<string, MatchResponse[]>;
  impacts: Record<string, NetworkImpactResponse[]>;
}

export const DEMO_DATA: DemoData = {
  demo: true,
  health: { status: "demo", version: "sample-fixture" },
  summary: {
    total_restrictions_represented: 3,
    evaluated_restrictions: 2,
    evaluation_status_distribution: { EVALUATED: 2, NOT_EVALUATED: 1 },
    evidence_confidence_distribution: {
      HIGH: 1,
      MEDIUM: 1,
      INSUFFICIENT_EVIDENCE: 1,
    },
    impact_severity_distribution: { MODERATE: 1, HIGH: 1, NOT_EVALUATED: 1 },
    provenance: {
      publisher: "AccessFlow deterministic SAMPLE/DEMO fixture",
      analytical_status: "SAMPLE",
      methodology_version: "demo",
      source_snapshot: "demo-fixture",
    },
  },
  restrictions: [
    {
      restriction_id: "DEMO-001",
      evaluation_status: "EVALUATED",
      impact_severity: "HIGH",
      evidence_confidence: "HIGH",
      candidate_edge_count: 2,
      impact_evaluable: true,
      source_snapshot: "demo-fixture",
      match_type: "INTERSECTS",
      replacement_path_available: true,
      replacement_path_state: "AVAILABLE",
      coordinates: [-79.38, 43.65],
      location: { road: "Bay St", name: "Bay St from Queen St W to Dundas St W", from_road: "Queen St W", to_road: "Dundas St W" },
      duration_hours: 8,
    },
    {
      restriction_id: "DEMO-002",
      evaluation_status: "EVALUATED",
      impact_severity: "MODERATE",
      evidence_confidence: "MEDIUM",
      candidate_edge_count: 1,
      impact_evaluable: true,
      source_snapshot: "demo-fixture",
      match_type: "WITHIN_DISTANCE",
      replacement_path_available: false,
      replacement_path_state: "NOT_EVALUATED",
      coordinates: [-79.375, 43.652],
      location: { road: "University Ave", name: "University Ave from Dundas St W to Armoury St", from_road: "Dundas St W", to_road: "Armoury St" },
      duration_hours: null,
    },
    {
      restriction_id: "DEMO-003",
      evaluation_status: "NOT_EVALUATED",
      impact_severity: "NOT_EVALUATED",
      evidence_confidence: "INSUFFICIENT_EVIDENCE",
      candidate_edge_count: 0,
      impact_evaluable: false,
      source_snapshot: "demo-fixture",
      match_type: null,
      replacement_path_available: false,
      replacement_path_state: "NOT_EVALUATED",
      coordinates: null,
      location: null,
      duration_hours: null,
    },
  ],
  details: {
    "DEMO-001": {
      restriction_id: "DEMO-001",
      evaluation_status: "EVALUATED",
      impact_severity: "HIGH",
      evidence_confidence: "HIGH",
      candidate_edge_count: 2,
      impact_evaluable: true,
      provenance: {
        publisher: "AccessFlow deterministic SAMPLE/DEMO fixture",
        analytical_status: "SAMPLE",
        methodology_version: "demo",
        source_snapshot: "demo-fixture",
      },
      coordinates: [-79.38, 43.65],
      location: { road: "Bay St", name: "Bay St from Queen St W to Dundas St W", from_road: "Queen St W", to_road: "Dundas St W" },
      match_type: "INTERSECTS",
      duration_hours: 8,
      valid_restriction_polyline: true,
      fallback_geometry_used: false,
      reason_codes: [],
      limitations: ["SAMPLE/DEMO geometry only; not a Toronto result."],
      restriction_geometry: { type: "Point", coordinates: [-79.38, 43.65] },
    },
    "DEMO-002": {
      restriction_id: "DEMO-002",
      evaluation_status: "EVALUATED",
      impact_severity: "MODERATE",
      evidence_confidence: "MEDIUM",
      candidate_edge_count: 1,
      impact_evaluable: true,
      provenance: {
        publisher: "AccessFlow deterministic SAMPLE/DEMO fixture",
        analytical_status: "SAMPLE",
        methodology_version: "demo",
        source_snapshot: "demo-fixture",
      },
      coordinates: [-79.375, 43.652],
      location: { road: "University Ave", name: "University Ave from Dundas St W to Armoury St", from_road: "Dundas St W", to_road: "Armoury St" },
      match_type: "WITHIN_DISTANCE",
      duration_hours: null,
      valid_restriction_polyline: false,
      fallback_geometry_used: false,
      reason_codes: ["TEMPORAL_DATA_NOT_PROVIDED"],
      limitations: [
        "Temporal fields are not present in the current API artifact.",
        "SAMPLE/DEMO geometry only; not a Toronto result.",
      ],
      restriction_geometry: {
        type: "Point",
        coordinates: [-79.375, 43.652],
      },
    },
    "DEMO-003": {
      restriction_id: "DEMO-003",
      evaluation_status: "NOT_EVALUATED",
      impact_severity: "NOT_EVALUATED",
      evidence_confidence: "INSUFFICIENT_EVIDENCE",
      candidate_edge_count: 0,
      impact_evaluable: false,
      provenance: {
        publisher: "AccessFlow deterministic demo fixture",
        analytical_status: "SAMPLE",
        methodology_version: "demo",
        source_snapshot: "demo-fixture",
      },
      coordinates: null,
      location: null,
      match_type: null,
      duration_hours: null,
      valid_restriction_polyline: false,
      fallback_geometry_used: false,
      reason_codes: ["NO_CANDIDATE_EDGE"],
      limitations: [
        "Insufficient evidence for network evaluation.",
        "Demo fixture only; not a Toronto result.",
      ],
      restriction_geometry: null,
    },
  },
  matches: {
    "DEMO-001": [
      {
        pedestrian_feature_id: "SAMPLE-SEGMENT-001",
        match_type: "INTERSECTS",
        evidence_confidence: "HIGH",
        distance_m: 0,
        candidate_status: "CANDIDATE_AFFECTED_SEGMENT",
        geometry: {
          type: "LineString",
          coordinates: [
            [-79.381, 43.649],
            [-79.379, 43.651],
          ],
        },
      },
    ],
    "DEMO-002": [
      {
        pedestrian_feature_id: "SAMPLE-SEGMENT-002",
        match_type: "WITHIN_DISTANCE",
        evidence_confidence: "MEDIUM",
        distance_m: 14,
        candidate_status: "CANDIDATE_AFFECTED_SEGMENT",
        geometry: {
          type: "LineString",
          coordinates: [
            [-79.376, 43.651],
            [-79.374, 43.653],
          ],
        },
      },
    ],
  },
  impacts: {},
};
