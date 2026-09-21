const EVIDENCE_COLORS = {
  HIGH: '#087f8c',
  MEDIUM: '#b54708',
  LOW: '#7f56d9',
  INSUFFICIENT_EVIDENCE: '#667085',
  NOT_EVALUATED: '#98a2b3',
};

const EVIDENCE_LABELS = {
  HIGH: 'High confidence',
  MEDIUM: 'Medium confidence',
  LOW: 'Low confidence',
  INSUFFICIENT_EVIDENCE: 'Insufficient evidence',
  NOT_EVALUATED: 'Not evaluated',
};

const TORONTO_CENTER = [-79.3832, 43.6532];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

function matchTypeLabel(mt) {
  if (mt === 'direct_intersection') return 'Direct intersection';
  if (mt === 'proximity') return 'Proximity match';
  return mt || 'Unknown';
}

export function createMapAdapter(container, onFeatureSelect) {
  if (!container || typeof maplibregl === 'undefined') {
    container.innerHTML = '<div class="map-empty">Map library not available. Check browser console.</div>';
    return { setFeatures() {}, select() {}, showRestrictionLine() {}, zoomIn() {}, zoomOut() {}, fitSelected() {}, resetExtent() {} };
  }

  const map = new maplibregl.Map({
    container,
    style: {
      version: 8,
      sources: {
        osm: {
          type: 'raster',
          tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
          tileSize: 256,
          attribution: '&copy; OpenStreetMap contributors',
        },
      },
      layers: [
        {
          id: 'osm-tiles',
          type: 'raster',
          source: 'osm',
          minzoom: 0,
          maxzoom: 19,
        },
      ],
    },
    center: TORONTO_CENTER,
    zoom: 11,
  });

  map.addControl(new maplibregl.NavigationControl(), 'top-right');

  let restrictionSource = 'restrictions';
  let restrictionLayer = 'restriction-points';
  let heatmapLayer = 'restriction-heatmap';
  let bufferSource = 'restriction-buffers';
  let bufferLayer = 'restriction-buffers-fill';
  let highlightSource = 'highlight';
  let highlightLayer = 'highlight-line';
  let selectedId = null;
  let showHeatmap = false;
  let showBuffers = true;

  class LayerToggleControl {
    onAdd(map) {
      this._map = map;
      this._container = document.createElement('div');
      this._container.className = 'maplibregl-ctrl maplibregl-ctrl-group';
      this._container.style.cssText = 'display:flex;flex-direction:column;gap:2px;padding:4px;';
      const heatBtn = document.createElement('button');
      heatBtn.type = 'button';
      heatBtn.title = 'Toggle heatmap';
      heatBtn.textContent = 'H';
      heatBtn.style.cssText = 'width:28px;height:28px;font-weight:700;font-size:12px;border:none;background:#fff;color:#333;cursor:pointer;border-radius:3px;';
      heatBtn.onclick = () => {
        showHeatmap = !showHeatmap;
        map.setLayoutProperty(heatmapLayer, 'visibility', showHeatmap ? 'visible' : 'none');
        heatBtn.style.background = showHeatmap ? '#087f8c' : '#fff';
        heatBtn.style.color = showHeatmap ? '#fff' : '#333';
      };
      const bufBtn = document.createElement('button');
      bufBtn.type = 'button';
      bufBtn.title = 'Toggle buffer zones';
      bufBtn.textContent = 'B';
      bufBtn.style.cssText = 'width:28px;height:28px;font-weight:700;font-size:12px;border:none;background:#fff;color:#333;cursor:pointer;border-radius:3px;';
      bufBtn.onclick = () => {
        showBuffers = !showBuffers;
        map.setLayoutProperty(bufferLayer, 'visibility', showBuffers ? 'visible' : 'none');
        bufBtn.style.background = showBuffers ? '#087f8c' : '#fff';
        bufBtn.style.color = showBuffers ? '#fff' : '#333';
      };
      this._container.appendChild(heatBtn);
      this._container.appendChild(bufBtn);
      return this._container;
    }
    onRemove() {
      this._container.parentNode.removeChild(this._container);
      this._map = undefined;
    }
  }

  map.addControl(new LayerToggleControl(), 'top-right');

  map.on('load', () => {
    map.addSource(bufferSource, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    map.addLayer({
      id: bufferLayer,
      type: 'fill',
      source: bufferSource,
      paint: {
        'fill-color': ['match', ['get', 'evidence_confidence'], ...Object.entries(EVIDENCE_COLORS).flatMap(([k, v]) => [k, v]), '#98a2b3'],
        'fill-opacity': 0.12,
      },
    });

    map.addSource(restrictionSource, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    map.addLayer({
      id: heatmapLayer,
      type: 'heatmap',
      source: restrictionSource,
      layout: { visibility: 'none' },
      paint: {
        'heatmap-weight': ['coalesce', ['get', 'heat_weight'], 1],
        'heatmap-intensity': 0.8,
        'heatmap-color': [
          'interpolate', ['linear'], ['heatmap-density'],
          0, 'rgba(0,0,0,0)',
          0.2, '#e0f2f1',
          0.4, '#80cbc4',
          0.6, '#087f8c',
          0.8, '#b54708',
          1, '#e74c3c',
        ],
        'heatmap-radius': 25,
        'heatmap-opacity': 0.6,
      },
    });

    map.addLayer({
      id: restrictionLayer,
      type: 'circle',
      source: restrictionSource,
      paint: {
        'circle-radius': 7,
        'circle-stroke-width': 2,
        'circle-stroke-color': '#fff',
        'circle-color': ['match', ['get', 'evidence_confidence'], ...Object.entries(EVIDENCE_COLORS).flatMap(([k, v]) => [k, v]), '#98a2b3'],
      },
    });

    map.addSource(highlightSource, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    map.addLayer({
      id: highlightLayer,
      type: 'line',
      source: highlightSource,
      paint: {
        'line-color': '#fdb022',
        'line-width': 4,
      },
    });

    const pulseSource = 'selected-pulse';
    const pulseLayer = 'selected-pulse-ring';
    const predSource = 'prediction-marker';
    const predLayer = 'prediction-point';

    map.addSource(pulseSource, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({
      id: pulseLayer,
      type: 'circle',
      source: pulseSource,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['get', 'phase'], 0, 8, 1, 20],
        'circle-color': '#fdb022',
        'circle-opacity': ['interpolate', ['linear'], ['get', 'phase'], 0, 0.7, 1, 0],
        'circle-stroke-color': '#fdb022',
        'circle-stroke-width': 2,
        'circle-stroke-opacity': ['interpolate', ['linear'], ['get', 'phase'], 0, 0.9, 1, 0],
      },
    });

    map.addSource(predSource, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({
      id: predLayer,
      type: 'circle',
      source: predSource,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': 12,
        'circle-color': '#e74c3c',
        'circle-stroke-color': '#fff',
        'circle-stroke-width': 3,
        'circle-opacity': 0.9,
      },
    });

    let pulsePhase = 0;
    let pulseAnimFrame = null;
    function animatePulse() {
      pulsePhase = (pulsePhase + 0.02) % 1;
      const source = map.getSource(pulseSource);
      if (source) {
        const data = source._data;
        if (data?.features?.length) {
          const updated = { ...data, features: data.features.map((f) => ({ ...f, properties: { ...f.properties, phase: pulsePhase } })) };
          source.setData(updated);
        }
      }
      pulseAnimFrame = requestAnimationFrame(animatePulse);
    }
    animatePulse();

    map.on('click', restrictionLayer, (e) => {
      const feature = e.features?.[0];
      if (feature) {
        const props = feature.properties;
        const id = props.restriction_id;
        selectedId = id;
        onFeatureSelect(id);

        const coords = feature.geometry.coordinates;
        map.flyTo({ center: coords, zoom: 15, duration: 800 });

        const confidence = props.evidence_confidence || 'UNKNOWN';
        const status = (props.evaluation_status || 'UNKNOWN').replace(/_/g, ' ');
        const matchType = props.match_type || '';
        new maplibregl.Popup({ maxWidth: '320px' })
          .setLngLat(coords)
          .setHTML(
            `<div style="font-family:system-ui,-apple-system,sans-serif;font-size:13px;padding:4px 0;min-width:200px">
              <div style="font-weight:600;font-size:14px;margin-bottom:6px;color:#101828">${escapeHtml(id)}</div>
              <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px">
                <span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;background:${EVIDENCE_COLORS[confidence] || '#98a2b3'};color:#fff">${escapeHtml(confidence)}</span>
                ${matchType ? `<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;background:#e4e7ec;color:#344054">${escapeHtml(matchTypeLabel(matchType))}</span>` : ''}
              </div>
              <div style="color:#667085;font-size:12px;margin-bottom:8px">${escapeHtml(status)}</div>
              <button onclick="globalThis.__openRestriction('${escapeHtml(id)}')" style="background:#087f8c;color:#fff;border:none;padding:5px 12px;border-radius:6px;font-size:12px;cursor:pointer;font-weight:500">View Details</button>
            </div>`
          )
          .addTo(map);
      }
    });

    map.on('mouseenter', restrictionLayer, () => {
      map.getCanvas().style.cursor = 'pointer';
    });

    map.on('mouseleave', restrictionLayer, () => {
      map.getCanvas().style.cursor = '';
    });
  });

  function waitForLoad(callback) {
    if (map.loaded()) callback();
    else map.on('load', callback);
  }

  function makeBuffer(coords, radiusKm = 0.3) {
    const degPerKm = 1 / 111;
    const r = radiusKm * degPerKm;
    const lng = coords[0], lat = coords[1];
    const steps = 24;
    const polygon = [];
    for (let i = 0; i < steps; i++) {
      const angle = (2 * Math.PI * i) / steps;
      polygon.push([lng + r * Math.cos(angle), lat + r * Math.sin(angle) * 1.3]);
    }
    polygon.push(polygon[0]);
    return polygon;
  }

  return {
    setFeatures(features, fitBounds = true) {
      waitForLoad(() => {
        const points = features.filter((f) => f.geometry?.type === 'Point');
        const heatWeights = { HIGH: 3, MEDIUM: 2, LOW: 1, INSUFFICIENT_EVIDENCE: 0.5, NOT_EVALUATED: 0.3 };
        const geojson = {
          type: 'FeatureCollection',
          features: features.map((f) => ({
            type: 'Feature',
            geometry: f.geometry,
            properties: {
              restriction_id: f.restrictionId,
              evidence_confidence: f.evidenceConfidence,
              evaluation_status: f.evaluationStatus || 'UNKNOWN',
              match_type: f.matchType || '',
              kind: f.kind,
              heat_weight: heatWeights[f.evidenceConfidence] || 0.5,
              duration_hours: f.durationHours ?? 0,
            },
          })),
        };
        map.getSource(restrictionSource)?.setData(geojson);

        const bufferFeatures = points.map((f) => ({
          type: 'Feature',
          geometry: { type: 'Polygon', coordinates: [makeBuffer(f.geometry.coordinates)] },
          properties: {
            restriction_id: f.restrictionId,
            evidence_confidence: f.evidenceConfidence,
          },
        }));
        map.getSource(bufferSource)?.setData({ type: 'FeatureCollection', features: bufferFeatures });

        if (fitBounds) {
          const bounds = new maplibregl.LngLatBounds();
          features.forEach((f) => {
            if (f.geometry?.type === 'Point') {
              bounds.extend(f.geometry.coordinates);
            } else if (f.geometry?.coordinates) {
              const coords = f.geometry.type === 'MultiLineString'
                ? f.geometry.coordinates.flat()
                : f.geometry.coordinates;
              coords.forEach((c) => bounds.extend(c));
            }
          });
          if (!bounds.isEmpty()) {
            map.fitBounds(bounds, { padding: 50, maxZoom: 14 });
          }
        }
      });
    },

    setTimeFilter(activeIds) {
      waitForLoad(() => {
        if (activeIds === null) {
          map.setFilter(restrictionLayer, null);
          map.setFilter(bufferLayer, null);
          map.setFilter(heatmapLayer, null);
        } else {
          const idList = [...activeIds];
          map.setFilter(restrictionLayer, ['in', ['get', 'restriction_id'], ['literal', idList]]);
          map.setFilter(bufferLayer, ['in', ['get', 'restriction_id'], ['literal', idList]]);
          map.setFilter(heatmapLayer, ['in', ['get', 'restriction_id'], ['literal', idList]]);
        }
      });
    },

    select(restrictionId) {
      selectedId = restrictionId;
      waitForLoad(() => {
        if (restrictionId) {
          const source = map.getSource(restrictionSource);
          if (source) {
            const data = source._data;
            if (data?.features) {
              const feature = data.features.find((f) => f.properties?.restriction_id === restrictionId);
              if (feature) {
                map.getSource(pulseSource)?.setData({
                  type: 'FeatureCollection',
                  features: [{ type: 'Feature', geometry: feature.geometry, properties: { phase: 0 } }],
                });
              }
            }
          }
        } else {
          map.getSource(pulseSource)?.setData({ type: 'FeatureCollection', features: [] });
        }
      });
    },

    showPredictionMarker(coords, prediction, confidence) {
      waitForLoad(() => {
        const color = prediction === 'High' ? '#e74c3c' : prediction === 'Low' ? '#f39c12' : '#2ecc71';
        map.getSource(predSource)?.setData({
          type: 'FeatureCollection',
          features: [{
            type: 'Feature',
            geometry: { type: 'Point', coordinates: coords },
            properties: { prediction, confidence: String(confidence) },
          }],
        });
        map.setLayoutProperty(predLayer, 'visibility', 'visible');
        map.setPaintProperty(predLayer, 'circle-color', color);
        map.flyTo({ center: coords, zoom: 14, duration: 1000 });
        setTimeout(() => {
          map.setLayoutProperty(predLayer, 'visibility', 'none');
        }, 8000);
      });
    },

    showRestrictionLine(geometry) {
      waitForLoad(() => {
        if (geometry && geometry.coordinates) {
          map.getSource(highlightSource)?.setData({
            type: 'FeatureCollection',
            features: [{ type: 'Feature', geometry, properties: {} }],
          });
          if (geometry.type === 'LineString') {
            const bounds = new maplibregl.LngLatBounds();
            geometry.coordinates.forEach((c) => bounds.extend(c));
            map.fitBounds(bounds, { padding: 80, maxZoom: 16 });
          }
        } else {
          map.getSource(highlightSource)?.setData({
            type: 'FeatureCollection',
            features: [],
          });
        }
      });
    },

    zoomIn() { map.zoomIn(); },
    zoomOut() { map.zoomOut(); },
    zoomToCoordinates(coords) {
      map.flyTo({ center: coords, zoom: 15, duration: 800 });
    },
    fitSelected() {
      if (selectedId) {
        const source = map.getSource(restrictionSource);
        if (source) {
          const data = source._data;
          if (data?.features) {
            const feature = data.features.find((f) => f.properties?.restriction_id === selectedId);
            if (feature) {
              map.fitBounds(new maplibregl.LngLatBounds().extend(feature.geometry.coordinates), { padding: 80 });
            }
          }
        }
      }
    },
    resetExtent() { map.fitBounds([[-79.6, 43.55], [-79.1, 43.85]], { padding: 30 }); },
  };
}
