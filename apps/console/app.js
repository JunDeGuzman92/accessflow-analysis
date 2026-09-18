import { getAnalyticsSummary, getHealth, getRestriction, getRestrictionNetworkImpact, getRestrictionSpatial, getRestrictions } from './api.js';
import { DEMO_DATA } from './fixtures.js';
import { buildMapFeatures, buildOverviewMetrics, filterAndSortRestrictions, formatMissing, getConsoleDataState, mapMatches, mapNetworkImpact, mapRestrictionDetail, mapRestrictionList, mapSpatialResponse, resolveMapSelection } from './domain.js';
import { createMapAdapter } from './map-adapter.js';
import { createState } from './state.js';

const state = createState();
const pageSize = 10;
let mapAdapter;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
}

function display(value) {
  return escapeHtml(formatMissing(value));
}

function setStatus(status, message = null) {
  state.status = status;
  state.message = message;
  const statusBanner = document.querySelector('[data-role="status"]');
  if (statusBanner) {
    statusBanner.className = `status-banner ${status}`;
    statusBanner.textContent = message || status.replaceAll('-', ' ');
    statusBanner.hidden = !message && status === 'ready';
  }
}

function renderOverview() {
  const overview = document.querySelector('[data-role="overview"]');
  const metrics = buildOverviewMetrics(state.summary, state.restrictions);
  const confidence = Object.entries(metrics.evidenceConfidenceDistribution);
  overview.innerHTML = `
    <article class="metric-card"><span>Total restrictions</span><strong>${metrics.totalRestrictions}</strong></article>
    <article class="metric-card"><span>Matched restrictions</span><strong>${metrics.evaluatedRestrictions}</strong></article>
    <article class="metric-card"><span>Evaluated / not evaluated</span><strong>${metrics.evaluatedRestrictions} / ${metrics.notEvaluatedCount}</strong></article>
    <article class="metric-card"><span>Evidence confidence</span><strong>${confidence.length ? confidence.map(([key, value]) => `${escapeHtml(key)} ${value}`).join(' · ') : 'Not available'}</strong></article>
    <article class="metric-card"><span>Replacement paths</span><strong>${metrics.replacementPathAvailability}</strong></article>
    <article class="metric-card"><span>Connectivity-loss cases</span><strong>${metrics.connectivityLossCases}</strong></article>
  `;
}

function renderTable() {
  const tableBody = document.querySelector('[data-role="restriction-table-body"]');
  const pageLabel = document.querySelector('[data-role="page-label"]');
  const filtered = filterAndSortRestrictions(state.restrictions, state.filters);
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  state.page = Math.min(state.page || 1, totalPages);
  const pageItems = filtered.slice((state.page - 1) * pageSize, state.page * pageSize);

  tableBody.innerHTML = pageItems.length ? pageItems.map((item) => `
    <tr>
      <td><button class="link-button" data-open-detail="${escapeHtml(item.restriction_id)}">${escapeHtml(item.restriction_id)}</button></td>
      <td>${display(item.source_snapshot)}</td>
      <td><span class="state-chip">${display(item.evaluation_status)}</span></td>
      <td><span class="state-chip">${display(item.evidence_confidence)}</span></td>
      <td>${display(item.match_type)}</td>
      <td>${display(item.impact_severity)}</td>
      <td>${display(item.replacement_path_state)}</td>
    </tr>
  `).join('') : '<tr><td colspan="7" class="empty-cell">No restrictions match the current filters.</td></tr>';

  pageLabel.textContent = `Page ${state.page} of ${totalPages} · ${filtered.length} records`;
  document.querySelector('[data-action="previous-page"]').disabled = state.page <= 1;
  document.querySelector('[data-action="next-page"]').disabled = state.page >= totalPages;
  tableBody.querySelectorAll('[data-open-detail]').forEach((button) => button.addEventListener('click', () => openRestriction(button.dataset.openDetail)));
  renderMap();
}

function renderMap() {
  if (!mapAdapter) return;
  const filtered = filterAndSortRestrictions(state.restrictions, state.filters);
  const allowed = new Set(filtered.map((item) => item.restriction_id));
  mapAdapter.setFeatures(state.mapFeatures.filter((feature) => allowed.has(feature.restrictionId)));
  mapAdapter.select(resolveMapSelection(state.activeRestrictionId, filtered));
}

function renderDetail(detail, matches, impacts) {
  const panel = document.querySelector('[data-role="detail-panel"]');
  if (!detail) {
    panel.innerHTML = '<p class="muted">Select a restriction to inspect its evidence.</p>';
    return;
  }
  const mappedDetail = mapRestrictionDetail(detail);
  const mappedMatches = mapMatches(matches);
  const mappedImpacts = mapNetworkImpact(impacts);
  state.activeRestrictionId = mappedDetail.restriction_id;
  if (state.mode !== 'demo') {
    state.mapFeatures = buildMapFeatures({ restrictions: [state.restrictions.find((item) => item.restriction_id === mappedDetail.restriction_id) ?? { restriction_id: mappedDetail.restriction_id, evidence_confidence: mappedDetail.evidence_confidence }], details: { [mappedDetail.restriction_id]: mappedDetail }, matches: { [mappedDetail.restriction_id]: mappedMatches } });
  }
  renderMap();
  const geometryMessage = mappedDetail.restriction_geometry ? 'Geometry supplied by current API artifact.' : 'Geometry not available from current API artifact.';

  panel.innerHTML = `
    <div class="detail-heading"><div><p class="eyebrow">Restriction detail</p><h3>${escapeHtml(mappedDetail.restriction_id)}</h3></div><span class="state-chip prominent">${display(mappedDetail.evaluation_status)}</span></div>
    <div class="detail-grid">
      <section><h4>Source and temporal information</h4><dl>
        <div><dt>Publisher</dt><dd>${display(mappedDetail.source_publisher)}</dd></div>
        <div><dt>Source snapshot</dt><dd>${display(mappedDetail.source_snapshot)}</dd></div>
        <div><dt>Duration hours</dt><dd>${display(mappedDetail.duration_hours)}</dd></div>
        <div><dt>Temporal fields</dt><dd>${display(mappedDetail.temporal_information)}</dd></div>
      </dl></section>
      <section><h4>Evidence state</h4><dl>
        <div><dt>Evidence confidence</dt><dd>${display(mappedDetail.evidence_confidence)}</dd></div>
        <div><dt>Impact severity</dt><dd>${display(mappedDetail.impact_severity)}</dd></div>
        <div><dt>Candidate segments</dt><dd>${display(mappedDetail.candidate_edge_count)}</dd></div>
        <div><dt>Reason codes</dt><dd>${mappedDetail.reason_codes.length ? mappedDetail.reason_codes.map(escapeHtml).join(', ') : 'None recorded'}</dd></div>
      </dl></section>
    </div>
    <section><h4>Spatial match evidence</h4>${mappedMatches.length ? `<ul>${mappedMatches.map((match) => `<li><strong>${escapeHtml(match.pedestrian_feature_id)}</strong> · ${display(match.match_type)} · ${display(match.evidence_confidence)} · distance ${display(match.distance_m)} m</li>`).join('')}</ul>` : '<p class="muted">No candidate segments recorded for this restriction.</p>'}</section>
    <section class="map-panel"><h4>Map panel</h4><p>${geometryMessage}</p>${mappedMatches.some((match) => match.geometry) ? '<p>Candidate geometry is present in the current API artifact.</p>' : '<p class="muted">No candidate geometry is available to draw.</p>'}</section>
    <section><h4>Replacement-path analysis</h4>${mappedImpacts.length ? `<div class="impact-list">${mappedImpacts.map((impact) => `<article><strong>${escapeHtml(impact.scenario)}</strong><span>Status: ${display(impact.evaluation_status)}</span><span>Max replacement ratio: ${display(impact.max_replacement_ratio)}</span><span>Added distance: ${display(impact.max_added_replacement_distance_m)} m</span><span>Connectivity loss: ${display(impact.local_connectivity_loss_count)}</span></article>`).join('')}</div>` : '<p class="muted">Replacement-path analysis not available from the current API artifact.</p>'}</section>
    <section><h4>Limitations</h4><ul>${mappedDetail.limitations.length ? mappedDetail.limitations.map((limit) => `<li>${escapeHtml(limit)}</li>`).join('') : '<li>No limitations recorded.</li>'}</ul></section>
  `;
}

async function openRestriction(restrictionId) {
  const panel = document.querySelector('[data-role="detail-panel"]');
  panel.innerHTML = '<p class="loading">Loading restriction evidence...</p>';
  try {
    if (state.mode === 'demo') {
      renderDetail(state.demoDetails[restrictionId], state.demoMatches[restrictionId] || [], state.demoImpacts[restrictionId] || []);
      return;
    }
    const [detail, spatial, impacts] = await Promise.all([getRestriction(restrictionId), getRestrictionSpatial(restrictionId), getRestrictionNetworkImpact(restrictionId)]);
    const spatialData = mapSpatialResponse(spatial);
    renderDetail({ ...detail, restriction_geometry: spatialData.restrictionGeometry }, spatialData.candidateFeatures, impacts);
  } catch (error) {
    panel.innerHTML = `<p class="error-text">Unable to load detail: ${escapeHtml(error.message)}</p>`;
  }
}

function wireControls() {
  ['query', 'evaluationStatus', 'evidenceConfidence', 'matchType'].forEach((name) => {
    const element = document.querySelector(`[data-filter="${name}"]`);
    element.addEventListener('input', () => { state.filters[name] = element.value; state.page = 1; renderTable(); });
  });
  document.querySelectorAll('[data-sort]').forEach((button) => button.addEventListener('click', () => {
    const key = button.dataset.sort;
    state.filters.direction = state.filters.sortKey === key && state.filters.direction === 'asc' ? 'desc' : 'asc';
    state.filters.sortKey = key;
    renderTable();
  }));
  document.querySelector('[data-action="previous-page"]').addEventListener('click', () => { state.page -= 1; renderTable(); });
  document.querySelector('[data-action="next-page"]').addEventListener('click', () => { state.page += 1; renderTable(); });
  document.querySelector('[data-map-action="zoom-in"]').addEventListener('click', () => mapAdapter.zoomIn());
  document.querySelector('[data-map-action="zoom-out"]').addEventListener('click', () => mapAdapter.zoomOut());
  document.querySelector('[data-map-action="pan-left"]').addEventListener('click', () => mapAdapter.pan(-30, 0));
  document.querySelector('[data-map-action="pan-right"]').addEventListener('click', () => mapAdapter.pan(30, 0));
  document.querySelector('[data-map-action="pan-up"]').addEventListener('click', () => mapAdapter.pan(0, -30));
  document.querySelector('[data-map-action="pan-down"]').addEventListener('click', () => mapAdapter.pan(0, 30));
  document.querySelector('[data-map-action="fit-selected"]').addEventListener('click', () => mapAdapter.fitSelected());
  document.querySelector('[data-map-action="reset"]').addEventListener('click', () => mapAdapter.resetExtent());
}

function applyData(dataState) {
  state.mode = dataState.mode;
  state.status = dataState.status;
  state.message = dataState.message;
  state.health = dataState.data?.health ?? null;
  state.summary = dataState.data?.summary ?? null;
  state.restrictions = dataState.data?.restrictions ?? [];
  state.demoDetails = dataState.data?.details ?? {};
  state.demoMatches = dataState.data?.matches ?? {};
  state.demoImpacts = dataState.data?.impacts ?? {};
  state.mapFeatures = dataState.data?.demo ? buildMapFeatures({ restrictions: state.restrictions, details: state.demoDetails, matches: state.demoMatches }) : [];
  setStatus(dataState.status, dataState.message);
  renderOverview();
  renderTable();
  if (!state.restrictions.length) document.querySelector('[data-role="detail-panel"]').innerHTML = '<p class="muted">No restriction detail is available.</p>';
}

async function loadDashboard() {
  setStatus('loading', 'Loading live AccessFlow API data...');
  try {
    const [health, summary, restrictionsResponse] = await Promise.all([getHealth(), getAnalyticsSummary(), getRestrictions({ limit: 100 })]);
    if (!restrictionsResponse || !Array.isArray(restrictionsResponse.items)) throw new Error('Malformed restrictions response.');
    const data = { health, summary, restrictions: mapRestrictionList(restrictionsResponse) };
    applyData(getConsoleDataState({ apiData: data, apiError: null, demoData: null }));
  } catch (error) {
    console.warn(error);
    applyData(getConsoleDataState({ apiData: null, apiError: error, demoData: DEMO_DATA }));
  }
}

document.addEventListener('DOMContentLoaded', () => {
  mapAdapter = createMapAdapter(document.querySelector('[data-role="map"]'), openRestriction);
  wireControls();
  renderDetail(null);
  loadDashboard();
  initPredictionForm();
  initWebSocket();
});

function initPredictionForm() {
  const form = document.getElementById('predict-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());
    data.latitude = parseFloat(data.latitude);
    data.longitude = parseFloat(data.longitude);
    data.duration_days = parseFloat(data.duration_days);

    try {
      const API_BASE = globalThis.ACCESSFLOW_API_BASE_URL || '';
      const resp = await fetch(`${API_BASE}/api/v1/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const result = await resp.json();
      showPredictionResult(result);
    } catch (err) {
      console.error('Prediction failed:', err);
      alert('Prediction failed. Make sure the API is running.');
    }
  });
}

function showPredictionResult(result) {
  const container = document.getElementById('prediction-result');
  container.style.display = 'block';

  const predEl = document.getElementById('result-prediction');
  predEl.textContent = result.prediction;
  predEl.className = `result-value impact-${result.prediction.toLowerCase()}`;

  document.getElementById('result-confidence').textContent = `${(result.confidence * 100).toFixed(1)}%`;

  const probsEl = document.getElementById('result-probabilities');
  probsEl.innerHTML = Object.entries(result.probabilities)
    .map(([cls, prob]) => {
      const pct = (prob * 100).toFixed(1);
      const color = cls === 'High' ? '#e74c3c' : cls === 'Low' ? '#f39c12' : '#2ecc71';
      return `<div class="prob-bar"><span class="prob-label">${cls}</span><div class="prob-track"><div class="prob-fill" style="width:${pct}%;background:${color}"></div></div><span class="prob-value">${pct}%</span></div>`;
    }).join('');
}

function initWebSocket() {
  const feed = document.getElementById('live-feed');
  const statusDot = document.getElementById('ws-status');
  const API_BASE = globalThis.ACCESSFLOW_API_BASE_URL || `ws://${location.host}`;

  let ws;
  try {
    ws = new WebSocket(API_BASE.replace('http', 'ws') + '/ws');
  } catch {
    feed.innerHTML = '<p class="muted">WebSocket unavailable</p>';
    return;
  }

  ws.onopen = () => {
    statusDot.classList.add('connected');
    feed.innerHTML = '<p class="muted">Connected. Waiting for updates...</p>';
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'prediction') {
      const d = msg.data;
      const item = document.createElement('div');
      item.className = 'feed-item';
      item.innerHTML = `<span class="feed-time">${new Date(msg.timestamp).toLocaleTimeString()}</span><span class="feed-road">${escapeHtml(d.road)}</span><span class="feed-impact impact-${(d.impact || 'none').toLowerCase()}">${escapeHtml(d.impact || '?')}</span>`;
      feed.prepend(item);
      if (feed.children.length > 20) feed.lastChild.remove();
    } else if (msg.type === 'status') {
      const item = document.createElement('div');
      item.className = 'feed-item feed-status';
      item.innerHTML = `<span class="feed-time">${new Date(msg.timestamp).toLocaleTimeString()}</span><span>${escapeHtml(msg.data.event)}</span>`;
      feed.prepend(item);
    }
  };

  ws.onclose = () => {
    statusDot.classList.remove('connected');
    feed.innerHTML = '<p class="muted">Disconnected. Reconnecting...</p>';
    setTimeout(initWebSocket, 5000);
  };

  ws.onerror = () => {
    statusDot.classList.remove('connected');
  };
}
