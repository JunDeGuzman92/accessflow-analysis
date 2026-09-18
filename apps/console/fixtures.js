export const DEMO_DATA = {
  demo: true,
  health: { status: 'demo', version: 'sample-fixture' },
  summary: {
    total_restrictions_represented: 3,
    evaluated_restrictions: 2,
    evaluation_status_distribution: { EVALUATED: 2, NOT_EVALUATED: 1 },
    evidence_confidence_distribution: { HIGH: 1, MEDIUM: 1, INSUFFICIENT_EVIDENCE: 1 },
    impact_severity_distribution: { MODERATE: 1, HIGH: 1, NOT_EVALUATED: 1 },
  },
  restrictions: [
    { restriction_id: 'DEMO-001', evaluation_status: 'EVALUATED', impact_severity: 'HIGH', evidence_confidence: 'HIGH', candidate_edge_count: 2, impact_evaluable: true, source_snapshot: 'demo-fixture', match_type: 'INTERSECTS', connectivity_loss: true, replacement_path_available: true, replacement_path_state: 'AVAILABLE' },
    { restriction_id: 'DEMO-002', evaluation_status: 'EVALUATED', impact_severity: 'MODERATE', evidence_confidence: 'MEDIUM', candidate_edge_count: 1, impact_evaluable: true, source_snapshot: 'demo-fixture', match_type: 'WITHIN_DISTANCE', connectivity_loss: false, replacement_path_available: false, replacement_path_state: 'NOT_EVALUATED' },
    { restriction_id: 'DEMO-003', evaluation_status: 'NOT_EVALUATED', impact_severity: 'NOT_EVALUATED', evidence_confidence: 'INSUFFICIENT_EVIDENCE', candidate_edge_count: 0, impact_evaluable: false, source_snapshot: 'demo-fixture', match_type: null, connectivity_loss: null, replacement_path_available: false, replacement_path_state: 'NOT_EVALUATED' },
  ],
  details: {
    'DEMO-001': { restriction_id: 'DEMO-001', evaluation_status: 'EVALUATED', impact_severity: 'HIGH', evidence_confidence: 'HIGH', candidate_edge_count: 2, impact_evaluable: true, valid_restriction_polyline: true, fallback_geometry_used: false, duration_hours: 8, reason_codes: [], limitations: ['SAMPLE/DEMO geometry only; not a Toronto result.'], restriction_geometry: { type: 'Point', coordinates: [-79.38, 43.65] }, provenance: { publisher: 'AccessFlow deterministic SAMPLE/DEMO fixture', source_snapshot: 'demo-fixture' }, temporal_information: null },
    'DEMO-002': { restriction_id: 'DEMO-002', evaluation_status: 'EVALUATED', impact_severity: 'MODERATE', evidence_confidence: 'MEDIUM', candidate_edge_count: 1, impact_evaluable: true, valid_restriction_polyline: false, fallback_geometry_used: false, duration_hours: null, reason_codes: ['TEMPORAL_DATA_NOT_PROVIDED'], limitations: ['Temporal fields are not present in the current API artifact.', 'SAMPLE/DEMO geometry only; not a Toronto result.'], restriction_geometry: { type: 'Point', coordinates: [-79.375, 43.652] }, provenance: { publisher: 'AccessFlow deterministic SAMPLE/DEMO fixture', source_snapshot: 'demo-fixture' }, temporal_information: null },
    'DEMO-003': { restriction_id: 'DEMO-003', evaluation_status: 'NOT_EVALUATED', impact_severity: 'NOT_EVALUATED', evidence_confidence: 'INSUFFICIENT_EVIDENCE', candidate_edge_count: 0, impact_evaluable: false, valid_restriction_polyline: false, fallback_geometry_used: false, duration_hours: null, reason_codes: ['NO_CANDIDATE_EDGE'], limitations: ['Insufficient evidence for network evaluation.', 'Demo fixture only; not a Toronto result.'], restriction_geometry: null, provenance: { publisher: 'AccessFlow deterministic demo fixture', source_snapshot: 'demo-fixture' }, temporal_information: null },
  },
  matches: { 'DEMO-001': [{ pedestrian_feature_id: 'SAMPLE-SEGMENT-001', match_type: 'INTERSECTS', evidence_confidence: 'HIGH', distance_m: 0, geometry: { type: 'LineString', coordinates: [[-79.381, 43.649], [-79.379, 43.651]] } }], 'DEMO-002': [{ pedestrian_feature_id: 'SAMPLE-SEGMENT-002', match_type: 'WITHIN_DISTANCE', evidence_confidence: 'MEDIUM', distance_m: 14, geometry: { type: 'LineString', coordinates: [[-79.376, 43.651], [-79.374, 43.653]] } }] },
  impacts: {},
};