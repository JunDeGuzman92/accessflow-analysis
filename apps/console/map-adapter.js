import { evidenceStateLabel, isUsableGeoJson } from './domain.js';

const VIEWBOX = { width: 900, height: 420 };

function coordinatePairs(geometry) {
  if (!isUsableGeoJson(geometry)) return [];
  if (geometry.type === 'Point') return [geometry.coordinates];
  if (geometry.type === 'LineString') return geometry.coordinates;
  if (geometry.type === 'MultiLineString') return geometry.coordinates.flat();
  if (geometry.type === 'Polygon') return geometry.coordinates.flat();
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat(2);
  return [];
}

export function geometryBounds(features = []) {
  const points = features.flatMap((feature) => coordinatePairs(feature.geometry)).filter((point) => Array.isArray(point) && point.length >= 2 && Number.isFinite(point[0]) && Number.isFinite(point[1]));
  if (!points.length) return null;
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

export function createProjection(bounds, viewBox = VIEWBOX) {
  if (!bounds) return null;
  const width = Math.max(bounds.maxX - bounds.minX, 0.00001);
  const height = Math.max(bounds.maxY - bounds.minY, 0.00001);
  const padding = 36;
  const scale = Math.min((viewBox.width - padding * 2) / width, (viewBox.height - padding * 2) / height);
  return ([x, y]) => [padding + (x - bounds.minX) * scale, viewBox.height - padding - (y - bounds.minY) * scale];
}

function geometryPath(geometry, project) {
  const paths = [];
  const lines = geometry.type === 'LineString' ? [geometry.coordinates] : geometry.type === 'MultiLineString' ? geometry.coordinates : geometry.type === 'Polygon' ? geometry.coordinates : geometry.type === 'MultiPolygon' ? geometry.coordinates.flat() : [];
  lines.forEach((line) => {
    if (line.length) paths.push(line.map((coordinate, index) => `${index ? 'L' : 'M'} ${project(coordinate).join(' ')}`).join(' '));
  });
  return paths;
}

export function createMapAdapter(container, onFeatureSelect) {
  let features = [];
  let selectedRestrictionId = null;
  let transform = { x: 0, y: 0, scale: 1 };
  let projection = null;

  function render() {
    const bounds = geometryBounds(features);
    projection = createProjection(bounds);
    if (!projection) {
      container.innerHTML = '<div class="map-empty">Geometry not available from current API artifact.</div>';
      return;
    }
    const markup = features.map((feature, index) => {
      const paths = geometryPath(feature.geometry, projection);
      const point = feature.geometry.type === 'Point' ? projection(feature.geometry.coordinates) : null;
      const selected = feature.restrictionId === selectedRestrictionId;
      const state = evidenceStateLabel(feature.evidenceConfidence);
      const shape = point ? `<circle cx="${point[0]}" cy="${point[1]}" r="${selected ? 8 : 6}" />` : paths.map((path) => `<path d="${path}" />`).join('');
      return `<g class="map-feature map-${feature.kind} evidence-${state.toLowerCase()} ${selected ? 'selected' : ''}" data-feature-index="${index}" tabindex="0" role="button" aria-label="${feature.restrictionId} ${feature.kind} ${state}">${shape}</g>`;
    }).join('');
    container.innerHTML = `<svg viewBox="0 0 ${VIEWBOX.width} ${VIEWBOX.height}" role="img" aria-label="Evidence geometry map"><g transform="translate(${transform.x} ${transform.y}) scale(${transform.scale})">${markup}</g></svg>`;
    container.querySelectorAll('[data-feature-index]').forEach((element) => {
      const feature = features[Number(element.dataset.featureIndex)];
      element.addEventListener('click', () => onFeatureSelect(feature.restrictionId));
      element.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onFeatureSelect(feature.restrictionId); } });
    });
  }

  return {
    setFeatures(nextFeatures) { features = nextFeatures; render(); },
    select(restrictionId) { selectedRestrictionId = restrictionId; render(); },
    zoomIn() { transform.scale = Math.min(transform.scale * 1.25, 8); render(); },
    zoomOut() { transform.scale = Math.max(transform.scale / 1.25, 0.5); render(); },
    pan(x, y) { transform.x += x; transform.y += y; render(); },
    fitSelected() { transform = { x: 0, y: 0, scale: 1 }; render(); },
    resetExtent() { transform = { x: 0, y: 0, scale: 1 }; render(); },
  };
}