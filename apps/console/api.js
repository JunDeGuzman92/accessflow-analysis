export const API_BASE_URL = globalThis.ACCESSFLOW_API_BASE_URL ?? 'http://127.0.0.1:8000';

export async function fetchJson(url, options = {}) {
  const requestUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;
  const response = await fetch(requestUrl, {
    headers: { Accept: 'application/json' },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Request failed (${response.status}): ${detail || requestUrl}`);
  }

  return response.json();
}

export async function getHealth() {
  return fetchJson('/health');
}

export async function getRestrictions(params = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  const url = query ? `/api/v1/restrictions?${query}` : '/api/v1/restrictions';
  return fetchJson(url);
}

export async function getRestriction(restrictionId) {
  return fetchJson(`/api/v1/restrictions/${encodeURIComponent(restrictionId)}`);
}

export async function getRestrictionMatches(restrictionId) {
  return fetchJson(`/api/v1/restrictions/${encodeURIComponent(restrictionId)}/matches`);
}

export async function getRestrictionSpatial(restrictionId) {
  return fetchJson(`/api/v1/restrictions/${encodeURIComponent(restrictionId)}/spatial`);
}

export async function getRestrictionNetworkImpact(restrictionId) {
  return fetchJson(`/api/v1/restrictions/${encodeURIComponent(restrictionId)}/network-impact`);
}

export async function getAnalyticsSummary() {
  return fetchJson('/api/v1/analytics/summary');
}
