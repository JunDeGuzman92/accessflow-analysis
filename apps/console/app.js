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
  const severity = Object.entries(metrics.impactSeverityDistribution);
  const total = metrics.totalRestrictions || 1;
  const confidenceColors = { HIGH: '#087f8c', MEDIUM: '#b54708', LOW: '#7f56d9', INSUFFICIENT_EVIDENCE: '#667085', NOT_EVALUATED: '#98a2b3' };
  const severityColors = { NOT_EVALUATED: '#98a2b3', Low: '#b54708', High: '#087f8c' };
  overview.innerHTML = `
    <article class="metric-card"><span>Total restrictions</span><strong>${metrics.totalRestrictions}</strong></article>
    <article class="metric-card"><span>Evaluated / not evaluated</span><strong>${metrics.evaluatedRestrictions} / ${metrics.notEvaluatedCount}</strong></article>
    <article class="metric-card metric-card-wide"><span>Evidence confidence distribution</span>
      <div class="distribution-bar">${confidence.map(([key, value]) => `<div class="dist-segment" style="width:${(value / total * 100).toFixed(1)}%;background:${confidenceColors[key] || '#98a2b3'}" title="${escapeHtml(key)}: ${value}"></div>`).join('')}</div>
      <div class="distribution-labels">${confidence.map(([key, value]) => `<span style="color:${confidenceColors[key] || '#98a2b3'}">${escapeHtml(key)} ${value}</span>`).join(' · ')}</div>
    </article>
    <article class="metric-card metric-card-wide"><span>Impact severity distribution</span>
      <div class="distribution-bar">${severity.map(([key, value]) => `<div class="dist-segment" style="width:${(value / total * 100).toFixed(1)}%;background:${severityColors[key] || '#98a2b3'}" title="${escapeHtml(key)}: ${value}"></div>`).join('')}</div>
      <div class="distribution-labels">${severity.map(([key, value]) => `<span style="color:${severityColors[key] || '#98a2b3'}">${escapeHtml(key)} ${value}</span>`).join(' · ')}</div>
    </article>
    <article class="metric-card"><span>Replacement-path available</span><strong>${metrics.replacementPathAvailability}</strong></article>
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
    <tr data-row-detail="${escapeHtml(item.restriction_id)}">
      <td><input type="checkbox" class="compare-check" data-restriction-id="${escapeHtml(item.restriction_id)}" /></td>
      <td><button class="link-button" data-open-detail="${escapeHtml(item.restriction_id)}">${escapeHtml(item.restriction_id)}</button></td>
      <td>${display(item.source_snapshot)}</td>
      <td><span class="state-chip">${display(item.evaluation_status)}</span></td>
      <td><span class="state-chip">${display(item.evidence_confidence)}</span></td>
      <td>${display(item.match_type)}</td>
      <td>${display(item.impact_severity)}</td>
      <td>${display(item.duration_hours ? `${Math.round(parseFloat(item.duration_hours))}h` : null)}</td>
      <td>${display(item.replacement_path_state)}</td>
    </tr>
  `).join('') : '<tr><td colspan="9" class="empty-cell">No restrictions match the current filters.</td></tr>';

  pageLabel.textContent = `Page ${state.page} of ${totalPages} · ${filtered.length} records`;
  document.querySelector('[data-action="previous-page"]').disabled = state.page <= 1;
  document.querySelector('[data-action="next-page"]').disabled = state.page >= totalPages;
  renderMap();
}

function renderMap(fitBounds = false) {
  if (!mapAdapter) return;
  const filtered = filterAndSortRestrictions(state.restrictions, state.filters);
  const allowed = new Set(filtered.map((item) => item.restriction_id));
  mapAdapter.setFeatures(state.mapFeatures.filter((feature) => allowed.has(feature.restrictionId)), fitBounds);
  mapAdapter.select(resolveMapSelection(state.activeRestrictionId, filtered));
  highlightTableRow(state.activeRestrictionId);
  if (state.activeRestrictionId && state.mode !== 'demo') {
    const detail = state.details[state.activeRestrictionId];
    if (detail && detail.restriction_geometry) {
      mapAdapter.showRestrictionLine(detail.restriction_geometry);
    }
  }
}

function highlightTableRow(restrictionId) {
  document.querySelectorAll('[data-role="restriction-table-body"] tr').forEach((tr) => {
    tr.classList.remove('row-highlighted');
  });
  if (!restrictionId) return;
  const btn = document.querySelector(`[data-open-detail="${CSS.escape(restrictionId)}"]`);
  if (btn) {
    const tr = btn.closest('tr');
    if (tr) {
      tr.classList.add('row-highlighted');
      tr.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }
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
  renderMap();
  if (mapAdapter && mappedDetail.restriction_geometry) {
    mapAdapter.showRestrictionLine(mappedDetail.restriction_geometry);
  }
  const geometryMessage = mappedDetail.restriction_geometry ? 'Geometry supplied by current API artifact.' : 'Geometry not available from current API artifact.';
  const confidenceColor = { HIGH: '#087f8c', MEDIUM: '#b54708', LOW: '#7f56d9', INSUFFICIENT_EVIDENCE: '#667085', NOT_EVALUATED: '#98a2b3' };
  const impactColor = { High: '#e74c3c', Low: '#f39c12', NOT_EVALUATED: '#98a2b3' };
  const durHours = mappedDetail.duration_hours;
  const durDisplay = durHours != null ? (durHours >= 24 ? `${Math.round(durHours / 24)} days (${Math.round(durHours)}h)` : `${Math.round(durHours)} hours`) : 'N/A';

  panel.innerHTML = `
    <div class="detail-heading"><div><p class="eyebrow">Restriction detail</p><h3>${escapeHtml(mappedDetail.restriction_id)}</h3></div><div style="display:flex;gap:8px;align-items:center"><span class="state-chip prominent" style="border-color:${confidenceColor[mappedDetail.evidence_confidence] || '#bcccdc'};color:${confidenceColor[mappedDetail.evidence_confidence] || 'inherit'}">${display(mappedDetail.evidence_confidence)}</span><span class="state-chip" style="border-color:${impactColor[mappedDetail.impact_severity] || '#bcccdc'};color:${impactColor[mappedDetail.impact_severity] || 'inherit'}">${display(mappedDetail.impact_severity)}</span><button class="secondary-button" onclick="if(globalThis.mapAdapter){globalThis.mapAdapter.fitSelected()}" title="Zoom to this restriction on the map">Zoom</button></div></div>
    <div class="detail-grid">
      <section><h4>Key metrics</h4><dl>
        <div><dt>Evaluation status</dt><dd>${display(mappedDetail.evaluation_status)}</dd></div>
        <div><dt>Candidate segments</dt><dd>${display(mappedDetail.candidate_edge_count)}</dd></div>
        <div><dt>Duration</dt><dd>${escapeHtml(durDisplay)}</dd></div>
        <div><dt>Valid polyline</dt><dd>${mappedDetail.valid_restriction_polyline ? 'Yes' : 'No'}</dd></div>
        <div><dt>Fallback geometry</dt><dd>${mappedDetail.fallback_geometry_used ? 'Yes' : 'No'}</dd></div>
        <div><dt>Publisher</dt><dd>${display(mappedDetail.source_publisher)}</dd></div>
      </dl></section>
      <section><h4>Spatial match evidence</h4>
        ${mappedMatches.length ? `<table style="width:100%;font-size:.82rem;border-collapse:collapse"><thead><tr style="border-bottom:1px solid #e4e7ec"><th style="text-align:left;padding:4px 6px;color:#667085">Feature</th><th style="text-align:left;padding:4px 6px;color:#667085">Type</th><th style="text-align:left;padding:4px 6px;color:#667085">Confidence</th><th style="text-align:right;padding:4px 6px;color:#667085">Distance</th></tr></thead><tbody>${mappedMatches.slice(0, 8).map((match) => `<tr style="border-bottom:1px solid #f0f0f0"><td style="padding:4px 6px;font-weight:600">${escapeHtml(match.pedestrian_feature_id)}</td><td style="padding:4px 6px">${escapeHtml(match.match_type)}</td><td style="padding:4px 6px"><span style="color:${confidenceColor[match.evidence_confidence] || '#333'}">${escapeHtml(match.evidence_confidence)}</span></td><td style="padding:4px 6px;text-align:right">${match.distance_m != null ? match.distance_m.toFixed(1) + ' m' : '—'}</td></tr>`).join('')}</tbody></table>${mappedMatches.length > 8 ? `<p class="muted" style="margin-top:6px;font-size:.78rem">+ ${mappedMatches.length - 8} more matches</p>` : ''}` : '<p class="muted">No candidate segments recorded.</p>'}
      </section>
    </div>
    <section class="map-panel"><h4>Geometry status</h4><p>${geometryMessage}</p>${mappedMatches.some((match) => match.geometry) ? '<p style="color:#087f8c;font-weight:500">Candidate geometry is present in the current API artifact.</p>' : '<p class="muted">No candidate geometry is available to draw.</p>'}</section>
    ${mappedImpacts.length ? `<section><h4>Replacement-path analysis</h4><div class="impact-list">${mappedImpacts.map((impact) => `<article><strong>${escapeHtml(impact.scenario)}</strong><span>Status: ${display(impact.evaluation_status)}</span><span>Max replacement ratio: ${display(impact.max_replacement_ratio)}</span><span>Added distance: ${display(impact.max_added_replacement_distance_m)} m</span><span>Connectivity loss: ${display(impact.local_connectivity_loss_count)}</span></article>`).join('')}</div></section>` : ''}
    ${mappedDetail.limitations.length ? `<section><h4>Limitations</h4><ul>${mappedDetail.limitations.map((limit) => `<li>${escapeHtml(limit)}</li>`).join('')}</ul></section>` : ''}
  `;
}

async function openRestriction(restrictionId) {
  const panel = document.querySelector('[data-role="detail-panel"]');
  panel.innerHTML = '<p class="loading">Loading restriction evidence...</p>';
  try {
    if (state.mode === 'demo') {
      renderDetail(state.details[restrictionId], state.matches[restrictionId] || [], state.impacts[restrictionId] || []);
      return;
    }
    const [detail, spatial, impacts] = await Promise.all([getRestriction(restrictionId), getRestrictionSpatial(restrictionId), getRestrictionNetworkImpact(restrictionId)]);
    const spatialData = mapSpatialResponse(spatial);
    state.details[restrictionId] = { ...detail, restriction_geometry: spatialData.restrictionGeometry };
    state.matches[restrictionId] = spatialData.candidateFeatures;
    state.impacts[restrictionId] = impacts;
    renderDetail(state.details[restrictionId], state.matches[restrictionId], state.impacts[restrictionId]);
    if (mapAdapter) {
      if (spatialData.restrictionGeometry) {
        mapAdapter.showRestrictionLine(spatialData.restrictionGeometry);
      } else {
        const restriction = state.restrictions.find((r) => r.restriction_id === restrictionId);
        if (restriction?.coordinates?.length === 2) {
          mapAdapter.zoomToCoordinates(restriction.coordinates);
        }
      }
    }
  } catch (error) {
    panel.innerHTML = `<p class="error-text">Unable to load detail: ${escapeHtml(error.message)}</p>`;
  }
}

function wireControls() {
  ['query', 'evaluationStatus', 'evidenceConfidence', 'matchType'].forEach((name) => {
    const element = document.querySelector(`[data-filter="${name}"]`);
    element.addEventListener('input', () => { state.filters[name] = element.value; state.page = 1; renderTable(); });
  });
  document.querySelectorAll('[data-sort]').forEach((button) => {
    button.addEventListener('click', () => {
      const key = button.dataset.sort;
      state.filters.direction = state.filters.sortKey === key && state.filters.direction === 'asc' ? 'desc' : 'asc';
      state.filters.sortKey = key;
      renderTable();
    });
  });
  document.querySelector('[data-action="previous-page"]').addEventListener('click', () => { state.page -= 1; renderTable(); });
  document.querySelector('[data-action="next-page"]').addEventListener('click', () => { state.page += 1; renderTable(); });

  document.querySelectorAll('[data-filter-confidence]').forEach((legendItem) => {
    legendItem.style.cursor = 'pointer';
    legendItem.addEventListener('click', () => {
      const confidence = legendItem.dataset.filterConfidence;
      const select = document.querySelector('[data-filter="evidenceConfidence"]');
      if (select) {
        select.value = select.value === confidence ? '' : confidence;
        state.filters.evidenceConfidence = select.value;
        state.page = 1;
        renderTable();
      }
    });
  });

  const tableBody = document.querySelector('[data-role="restriction-table-body"]');
  if (tableBody) {
    tableBody.addEventListener('click', (e) => {
      const row = e.target.closest('[data-row-detail]');
      if (!row) return;
      if (e.target.closest('input[type="checkbox"]')) return;
      openRestriction(row.dataset.rowDetail);
    });
  }
}

function applyData(dataState) {
  state.mode = dataState.mode;
  state.status = dataState.status;
  state.message = dataState.message;
  state.health = dataState.data?.health ?? null;
  state.summary = dataState.data?.summary ?? null;
  state.restrictions = dataState.data?.restrictions ?? [];
  state.details = dataState.data?.details ?? {};
  state.matches = dataState.data?.matches ?? {};
  state.impacts = dataState.data?.impacts ?? {};
  if (dataState.data?.demo) {
    state.mapFeatures = buildMapFeatures({ restrictions: state.restrictions, details: state.details, matches: state.matches });
  }
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
    const restrictions = mapRestrictionList(restrictionsResponse);
    const data = { health, summary, restrictions };

    const detailsMap = {};
    const matchesMap = {};

    restrictions.forEach((r) => {
      if (r.coordinates && r.coordinates.length === 2) {
        detailsMap[r.restriction_id] = {
          restriction_id: r.restriction_id,
          restriction_geometry: { type: 'Point', coordinates: r.coordinates },
          evidence_confidence: r.evidence_confidence,
        };
      }
    });

    state.mapFeatures = buildMapFeatures({ restrictions, details: detailsMap, matches: matchesMap });

    applyData(getConsoleDataState({ apiData: data, apiError: null, demoData: null }));
    renderMap(true);
    initTimeAnimation();
  } catch (error) {
    console.warn(error);
    applyData(getConsoleDataState({ apiData: null, apiError: error, demoData: DEMO_DATA }));
    initTimeAnimation();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  globalThis.__openRestriction = openRestriction;
  mapAdapter = createMapAdapter(document.getElementById('maplibre-map'), openRestriction);
  globalThis.mapAdapter = mapAdapter;
  wireControls();
  renderDetail(null);
  loadDashboard();
  initPredictionForm();
  initWebSocket();
  initSidebarNav();
  initCsvExport();
  initComparison();
  initKeyboardNav();
});

function initSidebarNav() {
  document.querySelectorAll('.nav-item').forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = link.getAttribute('href').slice(1);
      const target = document.getElementById(targetId);
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
      document.querySelectorAll('.nav-item').forEach((l) => l.classList.remove('active'));
      link.classList.add('active');
    });
  });
  const sections = ['overview', 'restrictions', 'predict', 'detail'];
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const id = entry.target.id;
        document.querySelectorAll('.nav-item').forEach((l) => {
          l.classList.toggle('active', l.getAttribute('href') === `#${id}`);
        });
      }
    });
  }, { threshold: 0.3 });
  sections.forEach((id) => {
    const el = document.getElementById(id);
    if (el) observer.observe(el);
  });
}

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
      showPredictionResult(result, [data.longitude, data.latitude]);
    } catch (err) {
      console.error('Prediction failed:', err);
      alert('Prediction failed. Make sure the API is running.');
    }
  });
}

function showPredictionResult(result, coords) {
  const container = document.getElementById('prediction-result');
  container.style.display = 'block';
  container.classList.add('result-enter');
  setTimeout(() => container.classList.remove('result-enter'), 400);

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

  if (coords && mapAdapter?.showPredictionMarker) {
    mapAdapter.showPredictionMarker(coords, result.prediction, result.confidence);
  }
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

      const districtCoords = {
        'Toronto and East York': [-79.3832, 43.6532],
        'Scarborough': [-79.2580, 43.7766],
        'Etobicoke York': [-79.4980, 43.6465],
        'North York': [-79.4428, 43.7617],
      };
      const coords = districtCoords[d.road] || [-79.3832, 43.6532];
      if (mapAdapter?.showPredictionMarker) {
        mapAdapter.showPredictionMarker(coords, d.impact, d.confidence || 0.5);
      }
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

function initCsvExport() {
  const btn = document.getElementById('export-csv');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const filtered = filterAndSortRestrictions(state.restrictions, state.filters);
    const headers = ['restriction_id', 'evaluation_status', 'evidence_confidence', 'match_type', 'impact_severity', 'candidate_edge_count', 'duration_hours', 'coordinates_lon', 'coordinates_lat'];
    const rows = filtered.map((r) => [
      r.restriction_id, r.evaluation_status, r.evidence_confidence, r.match_type || '', r.impact_severity, r.candidate_edge_count, r.duration_hours || '', r.coordinates?.[0] ?? '', r.coordinates?.[1] ?? '',
    ]);
    const csv = [headers.join(','), ...rows.map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `accessflow-restrictions-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  });
}

function initComparison() {
  const compareSet = new Set();
  const compareBtn = document.getElementById('compare-btn');
  const closeBtn = document.getElementById('close-compare');
  const panel = document.getElementById('compare-panel');
  const content = document.getElementById('compare-content');
  const selectAll = document.getElementById('select-all');

  function updateCompareBtn() {
    compareBtn.textContent = `Compare (${compareSet.size})`;
    compareBtn.disabled = compareSet.size < 2;
  }

  document.addEventListener('change', (e) => {
    if (e.target.matches('.compare-check')) {
      const id = e.target.dataset.restrictionId;
      if (e.target.checked) compareSet.add(id);
      else compareSet.delete(id);
      updateCompareBtn();
    }
  });

  if (selectAll) {
    selectAll.addEventListener('change', (e) => {
      const checkboxes = document.querySelectorAll('.compare-check');
      checkboxes.forEach((cb) => {
        cb.checked = e.target.checked;
        const id = cb.dataset.restrictionId;
        if (e.target.checked) compareSet.add(id);
        else compareSet.delete(id);
      });
      updateCompareBtn();
    });
  }

  compareBtn.addEventListener('click', () => {
    const ids = [...compareSet].slice(0, 2);
    if (ids.length < 2) return;
    const r1 = state.restrictions.find((r) => r.restriction_id === ids[0]);
    const r2 = state.restrictions.find((r) => r.restriction_id === ids[1]);
    if (!r1 || !r2) return;

    const fields = [
      { key: 'evidence_confidence', label: 'Confidence', order: ['HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT_EVIDENCE', 'NOT_EVALUATED'] },
      { key: 'impact_severity', label: 'Impact', order: ['High', 'Low', 'NOT_EVALUATED'] },
      { key: 'match_type', label: 'Match type', order: [] },
      { key: 'candidate_edge_count', label: 'Candidate edges', numeric: true },
      { key: 'evaluation_status', label: 'Status', order: [] },
    ];

    content.innerHTML = [r1, r2].map((r, i) => `
      <div class="compare-card">
        <h4>${escapeHtml(r.restriction_id)}</h4>
        ${fields.map((f) => {
          const v1 = i === 0 ? r[f.key] : null;
          const v2 = i === 1 ? r[f.key] : null;
          const val = r[f.key];
          return `<div class="compare-row"><span class="compare-label">${f.label}</span><span class="compare-value">${escapeHtml(val ?? 'N/A')}</span></div>`;
        }).join('')}
      </div>
    `).join('');

    panel.style.display = 'block';
    panel.scrollIntoView({ behavior: 'smooth' });
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', () => { panel.style.display = 'none'; });
  }
}

function initTimeAnimation() {
  const slider = document.getElementById('time-slider');
  const label = document.getElementById('time-label');
  const maxLabel = document.getElementById('time-max');
  const activeCount = document.getElementById('time-active-count');
  const playBtn = document.getElementById('anim-play');
  const pauseBtn = document.getElementById('anim-pause');
  const resetBtn = document.getElementById('anim-reset');
  const speedSelect = document.getElementById('anim-speed');
  if (!slider) return;

  if (!state.restrictions.length) {
    label.textContent = 'Waiting for data...';
    return;
  }

  const restrictionsWithDuration = state.restrictions
    .filter((r) => r.duration_hours != null && r.duration_hours !== '')
    .map((r) => ({ id: r.restriction_id, duration: parseFloat(r.duration_hours) || 0 }));

  if (!restrictionsWithDuration.length) {
    label.textContent = 'No duration data';
    return;
  }

  const durations = restrictionsWithDuration.map((r) => r.duration).filter((d) => d > 0);
  const maxDuration = durations.length ? Math.max(...durations) : 1;
  slider.max = Math.ceil(maxDuration);
  slider.value = 0;
  maxLabel.textContent = `${Math.ceil(maxDuration)}h`;
  label.textContent = '0 hours';

  function updateAtTime(t) {
    label.textContent = `${Math.round(t)} hours`;
    const active = restrictionsWithDuration.filter((r) => t <= r.duration);
    activeCount.textContent = active.length;
    if (mapAdapter && mapAdapter.setTimeFilter) {
      if (t === 0) {
        mapAdapter.setTimeFilter(null);
      } else {
        const activeIds = new Set(active.map((r) => r.id));
        mapAdapter.setTimeFilter(activeIds);
      }
    }
  }

  slider.addEventListener('input', () => { updateAtTime(parseFloat(slider.value)); });

  let animInterval = null;
  if (playBtn) {
    playBtn.addEventListener('click', () => {
      if (animInterval) return;
      const speed = parseInt(speedSelect.value) || 1000;
      animInterval = setInterval(() => {
        let val = parseFloat(slider.value) + Math.ceil(maxDuration / 200);
        if (val > parseFloat(slider.max)) val = 0;
        slider.value = val;
        updateAtTime(val);
      }, speed / 20);
    });
  }
  if (pauseBtn) {
    pauseBtn.addEventListener('click', () => { clearInterval(animInterval); animInterval = null; });
  }
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      clearInterval(animInterval);
      animInterval = null;
      slider.value = 0;
      updateAtTime(0);
    });
  }

  updateAtTime(0);
}

function initKeyboardNav() {
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
    const filtered = filterAndSortRestrictions(state.restrictions, state.filters);
    if (!filtered.length) return;
    const currentIdx = filtered.findIndex((r) => r.restriction_id === state.activeRestrictionId);
    if (e.key === 'ArrowDown' || e.key === 'j') {
      e.preventDefault();
      const next = currentIdx < filtered.length - 1 ? currentIdx + 1 : 0;
      openRestriction(filtered[next].restriction_id);
    } else if (e.key === 'ArrowUp' || e.key === 'k') {
      e.preventDefault();
      const prev = currentIdx > 0 ? currentIdx - 1 : filtered.length - 1;
      openRestriction(filtered[prev].restriction_id);
    } else if (e.key === 'Escape') {
      state.activeRestrictionId = null;
      renderDetail(null);
      renderMap();
      if (mapAdapter?.setTimeFilter) mapAdapter.setTimeFilter(null);
    } else if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      document.querySelector('[data-filter="query"]')?.focus();
    }
  });
}
