export function createState() {
  return {
    restrictions: [],
    activeRestrictionId: null,
    summary: null,
    health: null,
    mode: 'live',
    status: 'loading',
    message: null,
    selectedDetail: null,
    selectedMatches: [],
    selectedImpacts: [],
    page: 1,
    mapFeatures: [],
    filters: {
      query: '',
      evaluationStatus: '',
      evidenceConfidence: '',
      impactSeverity: '',
      matchType: '',
      sortKey: 'restriction_id',
      direction: 'asc',
    },
  };
}

export function updateState(state, patch) {
  return {
    ...state,
    ...patch,
  };
}
