export function coerceMetricValue(value) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const asNumber = Number(value);
  return Number.isFinite(asNumber) ? asNumber : null;
}

export function describeEvidenceStatus(value) {
  return value ?? 'UNKNOWN';
}

export function describeRestrictionState(item) {
  const evaluationStatus = item?.evaluation_status ?? 'UNKNOWN';
  const impactSeverity = item?.impact_severity ?? 'UNKNOWN';
  const evidenceConfidence = item?.evidence_confidence ?? 'UNKNOWN';

  return {
    restrictionId: item?.restriction_id ?? 'UNKNOWN',
    evaluationStatus,
    impactSeverity,
    evidenceConfidence,
    impactEvaluable: Boolean(item?.impact_evaluable),
    matchStatus: item?.match_type ?? 'NO_MATCH',
    replacementStatus: item?.replacement_state ?? 'UNAVAILABLE',
  };
}

export function buildOverviewMetrics(summary, restrictions = []) {
  const totalRestrictions = Number.isFinite(Number(summary?.total_restrictions_represented)) ? Number(summary.total_restrictions_represented) : restrictions.length;
  const evaluatedRestrictions = Number.isFinite(Number(summary?.evaluated_restrictions)) ? Number(summary.evaluated_restrictions) : restrictions.filter((item) => item.impact_evaluable === true).length;
  const evaluationStatusDistribution = summary?.evaluation_status_distribution ?? {};
  const evidenceConfidenceDistribution = summary?.evidence_confidence_distribution ?? {};
  const impactSeverityDistribution = summary?.impact_severity_distribution ?? {};

  const replacementPathRows = restrictions.filter((item) => item.replacement_path_available === true || item.replacement_path_state === 'AVAILABLE');

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

export function filterAndSortRestrictions(items = [], options = {}) {
  const {
    query = '',
    evaluationStatus = '',
    evidenceConfidence = '',
    matchType = '',
    impactSeverity = '',
    sortKey = 'restriction_id',
    direction = 'asc',
  } = options;

  const filtered = items.filter((item) => {
    const restrictionId = (item.restriction_id ?? '').toLowerCase();
    const haystack = [
      restrictionId,
      item.evaluation_status ?? '',
      item.evidence_confidence ?? '',
      item.impact_severity ?? '',
      item.match_type ?? '',
    ].join(' ').toLowerCase();

    const matchesQuery = !query || haystack.includes(query.toLowerCase());
    const matchesEvaluation = !evaluationStatus || item.evaluation_status === evaluationStatus;
    const matchesEvidence = !evidenceConfidence || item.evidence_confidence === evidenceConfidence;
    const matchesImpact = !impactSeverity || item.impact_severity === impactSeverity;
    const matchesMatchType = !matchType || item.match_type === matchType;

    return matchesQuery && matchesEvaluation && matchesEvidence && matchesImpact && matchesMatchType;
  });

  const multiplier = direction === 'desc' ? -1 : 1;

  filtered.sort((left, right) => {
    const leftValue = left[sortKey] ?? '';
    const rightValue = right[sortKey] ?? '';

    if (typeof leftValue === 'number' && typeof rightValue === 'number') {
      return (leftValue - rightValue) * multiplier;
    }

    return String(leftValue).localeCompare(String(rightValue)) * multiplier;
  });

  return filtered;
}

export function mapRestrictionList(response) {
  const items = Array.isArray(response?.items) ? response.items : [];
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
    replacement_path_state: 'UNAVAILABLE',
    coordinates: item.coordinates ?? null,
    duration_hours: item.duration_hours ?? null,
  }));
}

export function mapRestrictionDetail(response) {
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
    reason_codes: Array.isArray(response.reason_codes) ? response.reason_codes : [],
    limitations: Array.isArray(response.limitations) ? response.limitations : [],
    restriction_geometry: response.restriction_geometry ?? null,
    provenance: response.provenance ?? null,
    source_snapshot: response.provenance?.source_snapshot ?? null,
    source_publisher: response.provenance?.publisher ?? null,
    temporal_information: null,
  };
}

export function mapMatches(response = []) {
  return Array.isArray(response) ? response.map((item) => ({
    pedestrian_feature_id: item.pedestrian_feature_id ?? item.feature_id,
    match_type: item.match_type,
    evidence_confidence: item.evidence_confidence ?? item.confidence,
    distance_m: coerceMetricValue(item.distance_m),
    candidate_status: item.candidate_status ?? 'CANDIDATE_AFFECTED_SEGMENT',
    geometry: item.geometry ?? null,
  })) : [];
}

export function mapNetworkImpact(response = []) {
  return Array.isArray(response) ? response.map((item) => ({
    scenario: item.scenario,
    evaluation_status: item.evaluation_status,
    candidate_edge_count: Number(item.candidate_edge_count ?? 0),
    evaluated_edge_count: Number(item.evaluated_edge_count ?? 0),
    alternative_path_edge_count: Number(item.alternative_path_edge_count ?? 0),
    local_connectivity_loss_count: Number(item.local_connectivity_loss_count ?? 0),
    local_connectivity_loss_fraction: coerceMetricValue(item.local_connectivity_loss_fraction),
    median_replacement_ratio: coerceMetricValue(item.median_replacement_ratio),
    max_replacement_ratio: coerceMetricValue(item.max_replacement_ratio),
    median_added_replacement_distance_m: coerceMetricValue(item.median_added_replacement_distance_m),
    max_added_replacement_distance_m: coerceMetricValue(item.max_added_replacement_distance_m),
    set_evaluation_status: item.set_evaluation_status,
    limitations: Array.isArray(item.limitations) ? item.limitations : [],
  })) : [];
}

export function mapSpatialResponse(response = {}) {
  return {
    restrictionId: response.restriction_id ?? null,
    restrictionGeometry: response.restriction_geometry ?? null,
    geometryStatus: response.geometry_status ?? 'NOT_AVAILABLE',
    crs: response.crs ?? null,
    provenance: response.provenance ?? null,
    matchedFeatures: mapMatches(response.matched_features),
    candidateFeatures: mapMatches(response.candidate_features),
  };
}

export function formatMissing(value, label = 'Not available from current API artifact.') {
  return value === null || value === undefined || value === '' ? label : value;
}

export function getConsoleDataState({ apiData, apiError, demoData }) {
  if (apiData) {
    return { mode: 'live', status: 'ready', data: apiData, message: null };
  }
  if (demoData) {
    return { mode: 'demo', status: 'api-unavailable', data: demoData, message: 'Live API unavailable. Showing deterministic demo/sample data.' };
  }
  return { mode: 'empty', status: apiError ? 'api-unavailable' : 'empty', data: null, message: apiError ? 'Live API unavailable and no demo data is configured.' : 'No records returned by the current API artifact.' };
}

export function isUsableGeoJson(geometry) {
  return Boolean(geometry && typeof geometry === 'object' && typeof geometry.type === 'string' && geometry.coordinates);
}

export function buildMapFeatures({ restrictions = [], details = {}, matches = {} }) {
  return restrictions.flatMap((restriction) => {
    const detail = details[restriction.restriction_id] ?? {};
    const restrictionGeometry = isUsableGeoJson(detail.restriction_geometry) ? [{
      restrictionId: restriction.restriction_id,
      kind: 'restriction',
      evidenceConfidence: restriction.evidence_confidence,
      evaluationStatus: restriction.evaluation_status,
      matchType: restriction.match_type,
      durationHours: restriction.duration_hours,
      geometry: detail.restriction_geometry,
    }] : [];
    const matchFeatures = (matches[restriction.restriction_id] ?? []).filter((match) => isUsableGeoJson(match.geometry)).map((match) => ({
      restrictionId: restriction.restriction_id,
      kind: match.match_type === 'INTERSECTS' ? 'direct-match' : 'proximity-match',
      evidenceConfidence: match.evidence_confidence,
      evaluationStatus: restriction.evaluation_status,
      matchType: match.match_type,
      geometry: match.geometry,
    }));
    return [...restrictionGeometry, ...matchFeatures];
  });
}

export function evidenceStateLabel(value) {
  return ['HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT_EVIDENCE', 'NOT_EVALUATED'].includes(value) ? value : 'UNKNOWN';
}

export function resolveMapSelection(restrictionId, visibleRestrictions = []) {
  return visibleRestrictions.some((item) => item.restriction_id === restrictionId) ? restrictionId : null;
}
