"use client";

import { useStore, type BasemapId } from "@/store/useStore";

const LEGEND_ITEMS = [
  { label: "HIGH", color: "#087f8c" },
  { label: "MEDIUM", color: "#b54708" },
  { label: "LOW", color: "#7f56d9" },
  { label: "INSUFFICIENT", color: "#667085" },
  { label: "NOT_EVALUATED", color: "#98a2b3" },
];

const BASEMAP_OPTIONS: [BasemapId, string][] = [
  ["streets", "Streets"],
  ["light", "Light"],
  ["dark", "Dark"],
  ["aerial", "Aerial"],
];

export default function LayerControls() {
  const layerToggles = useStore((s) => s.layerToggles);
  const setLayerToggle = useStore((s) => s.setLayerToggle);
  const basemap = useStore((s) => s.basemap);
  const setBasemap = useStore((s) => s.setBasemap);
  const groundView = useStore((s) => s.groundView);
  const setGroundView = useStore((s) => s.setGroundView);
  const resetView = useStore((s) => s.resetView);

  return (
    <div className="layer-controls" aria-label="Map layer controls">
      <div className="layer-toggles">
        <div className="basemap-switcher" role="group" aria-label="Basemap style">
          {BASEMAP_OPTIONS.map(([id, label]) => (
            <button
              key={id}
              className={`toggle-chip basemap-chip ${basemap === id ? "on" : ""}`}
              onClick={() => setBasemap(id)}
              aria-pressed={basemap === id}
              title={`Switch the basemap to ${label}`}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className={`toggle-chip ${layerToggles.buildings ? "on" : ""}`}
          onClick={() => setLayerToggle("buildings", !layerToggles.buildings)}
          aria-pressed={layerToggles.buildings}
          title="Real City of Toronto 3D Massing buildings where available (downtown clip), OpenStreetMap building footprints elsewhere"
        >
          3D Buildings
        </button>
        <button
          className={`toggle-chip ${groundView ? "on" : ""}`}
          onClick={() => setGroundView(!groundView)}
          aria-pressed={groundView}
          title="Tilt the camera to a pedestrian street-level perspective"
        >
          Ground view
        </button>
        <button
          className={`toggle-chip ${layerToggles.towers ? "on" : ""}`}
          onClick={() => setLayerToggle("towers", !layerToggles.towers)}
          aria-pressed={layerToggles.towers}
          title="3D columns whose height encodes candidate segment count"
        >
          3D Towers
        </button>
        <button
          className={`toggle-chip ${layerToggles.heatmap ? "on" : ""}`}
          onClick={() => setLayerToggle("heatmap", !layerToggles.heatmap)}
          aria-pressed={layerToggles.heatmap}
          title="Disruption density heatmap, weighted by impact severity"
        >
          Heatmap
        </button>
        <button className="toggle-chip" onClick={resetView} title="Reset the map view to all restrictions">
          Reset view
        </button>
      </div>
      <div className="legend-list" aria-label="Evidence legend">
        {LEGEND_ITEMS.map((item) => (
          <span key={item.label} className="legend-entry">
            <span className="legend-swatch" style={{ background: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
      <p className="legend-note">
        Click a dot for its evidence constellation · ↑/↓ or j/k navigate · Esc deselect · / search.
        Candidate segments are not confirmed closures.
      </p>
    </div>
  );
}
