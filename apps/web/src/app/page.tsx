"use client";

import { useEffect, useCallback, useState } from "react";
import dynamic from "next/dynamic";
import { useStore } from "@/store/useStore";
import {
  getAnalyticsSummary,
  getExplanation,
  getHealth,
  getRestriction,
  getRestrictions,
  getRestrictionSpatial,
  getRestrictionNetworkImpact,
} from "@/lib/api-client";
import {
  buildMapFeatures,
  buildMapFeaturesFromCoordinates,
  filterAndSortRestrictions,
  getConsoleDataState,
  mapRestrictionList,
  mapSpatialResponse,
} from "@/lib/domain";
import { DEMO_DATA } from "@/lib/fixtures";
import ReviewQueuePanel from "@/components/ReviewQueuePanel";
import DetailPanel from "@/components/DetailPanel";
import PredictionPanel from "@/components/PredictionPanel";
import LayerControls from "@/components/LayerControls";
import RouteBar from "@/components/RouteBar";
import TimeScrubber from "@/components/TimeScrubber";

const MapView = dynamic(() => import("@/components/MapView"), {
  ssr: false,
  loading: () => (
    <div className="maplibre-canvas map-loading">Loading map…</div>
  ),
});

export default function Home() {
  const loadDashboard = useStore((s) => s.loadDashboard);
  const setSelected = useStore((s) => s.setSelected);
  const setActiveRestrictionId = useStore((s) => s.setActiveRestrictionId);
  const cacheDetail = useStore((s) => s.cacheDetail);
  const setExplanation = useStore((s) => s.setExplanation);
  const setExplanationLoading = useStore((s) => s.setExplanationLoading);
  const overviewExplanation = useStore((s) => s.overviewExplanation);
  const overviewOpen = useStore((s) => s.overviewOpen);
  const setOverviewOpen = useStore((s) => s.setOverviewOpen);
  const setOverviewExplanation = useStore((s) => s.setOverviewExplanation);
  const mode = useStore((s) => s.mode);
  const status = useStore((s) => s.status);
  const message = useStore((s) => s.message);
  const restrictions = useStore((s) => s.restrictions);
  const summary = useStore((s) => s.summary);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [health, summaryResponse, restrictionsResponse] = await Promise.all([
          getHealth(),
          getAnalyticsSummary(),
          getRestrictions({ limit: 100 }),
        ]);
        if (cancelled) return;
        if (!restrictionsResponse || !Array.isArray(restrictionsResponse.items)) {
          throw new Error("Malformed restrictions response.");
        }
        const mappedRestrictions = mapRestrictionList(restrictionsResponse);

        loadDashboard({
          health,
          summary: summaryResponse,
          restrictions: mappedRestrictions,
          mode: "live",
          status: "ready",
          message: null,
          mapFeatures: buildMapFeaturesFromCoordinates(mappedRestrictions),
        });
      } catch (error) {
        if (cancelled) return;
        console.warn(error);
        const dataState = getConsoleDataState({
          apiData: null,
          apiError: error as Error,
          demoData: DEMO_DATA,
        });
        const demoRestrictions = dataState.data?.restrictions ?? [];
        loadDashboard({
          health: dataState.data?.health ?? null,
          summary: dataState.data?.summary ?? null,
          restrictions: demoRestrictions,
          mode: dataState.mode,
          status: dataState.status,
          message: dataState.message,
          details: dataState.data?.details as never,
          matches: dataState.data?.matches as never,
          impacts: dataState.data?.impacts as never,
          mapFeatures: buildMapFeatures({
            restrictions: demoRestrictions,
            details: dataState.data?.details as never,
            matches: dataState.data?.matches as never,
          }),
        });
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [loadDashboard]);

  const openRestriction = useCallback(
    async (restrictionId: string) => {
      setDetailLoading(true);
      setActiveRestrictionId(restrictionId);

      const state = useStore.getState();

      if (state.mode === "demo") {
        setExplanation(null);
        const demoDetail = state.details[restrictionId] ?? null;
        const demoMatches = state.matches[restrictionId] ?? [];
        const demoImpacts = state.impacts[restrictionId] ?? [];
        const restriction = state.restrictions.find(
          (item) => item.restriction_id === restrictionId,
        );
        setSelected({
          detail: demoDetail,
          matches: demoMatches,
          impacts: demoImpacts,
          mapFeatures: buildMapFeatures({
            restrictions: restriction ? [restriction] : [],
            details: { [restrictionId]: { ...(demoDetail ?? {}) } as never },
            matches: { [restrictionId]: demoMatches as never },
          }),
        });
        setDetailLoading(false);
        return;
      }

      try {
        setExplanationLoading(true);
        const [detail, spatial, impacts, explanation] = await Promise.all([
          getRestriction(restrictionId),
          getRestrictionSpatial(restrictionId),
          getRestrictionNetworkImpact(restrictionId),
          getExplanation({ restriction_id: restrictionId }).catch(() => null),
        ]);
        const spatialData = mapSpatialResponse(spatial);
        const mergedDetail = {
          ...detail,
          restriction_geometry: spatialData.restrictionGeometry,
        };
        const restriction = state.restrictions.find(
          (item) => item.restriction_id === restrictionId,
        );
        cacheDetail(
          restrictionId,
          mergedDetail,
          spatialData.candidateFeatures as never,
          impacts,
        );
        setExplanation(explanation);
        setSelected({
          detail: mergedDetail,
          matches: spatialData.candidateFeatures as never,
          impacts,
          mapFeatures: buildMapFeatures({
            restrictions: restriction ? [restriction] : [],
            details: { [restrictionId]: mergedDetail as never },
            matches: { [restrictionId]: spatialData.candidateFeatures as never },
          }),
        });
      } catch (error) {
        console.error("Unable to load detail:", error);
      } finally {
        setDetailLoading(false);
        setExplanationLoading(false);
      }
    },
    [setActiveRestrictionId, setSelected, cacheDetail, setExplanation, setExplanationLoading],
  );

  const statusText = message ?? status.replaceAll("-", " ");
  const total = restrictions.length;
  const evaluated = restrictions.filter((r) => r.impact_evaluable).length;
  const highCount = restrictions.filter(
    (r) => r.impact_severity === "HIGH" || r.impact_severity === "SEVERE",
  ).length;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) return;
      if (e.key === "Escape") {
        useStore.getState().clearSelection();
        return;
      }
      if (e.key === "/" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        document.querySelector<HTMLInputElement>('input[type="search"]')?.focus();
        return;
      }
      const state = useStore.getState();
      const filteredNow = filterAndSortRestrictions(state.restrictions, state.filters);
      if (!filteredNow.length) return;
      const idx = filteredNow.findIndex(
        (r) => r.restriction_id === state.activeRestrictionId,
      );
      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        const next = idx < filteredNow.length - 1 ? idx + 1 : 0;
        openRestriction(filteredNow[next].restriction_id);
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        const prev = idx > 0 ? idx - 1 : filteredNow.length - 1;
        openRestriction(filteredNow[prev].restriction_id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openRestriction]);

  const fetchOverviewExplanation = useCallback(async () => {
    const state = useStore.getState();
    if (state.overviewExplanation) return;
    try {
      const explanation = await getExplanation({ overview: true });
      setOverviewExplanation(explanation);
    } catch (error) {
      console.warn("Overview explanation unavailable:", error);
      setOverviewExplanation(null);
    }
  }, [setOverviewExplanation]);

  useEffect(() => {
    const topbar = document.querySelector<HTMLElement>(".top-bar");
    if (!topbar) return;
    const apply = () => {
      const rect = topbar.getBoundingClientRect();
      document.documentElement.style.setProperty(
        "--topbar-bottom",
        `${Math.ceil(rect.bottom + 12)}px`,
      );
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(topbar);
    return () => {
      observer.disconnect();
      document.documentElement.style.removeProperty("--topbar-bottom");
    };
  }, []);

  const toggleOverview = useCallback(() => {
    const next = !overviewOpen;
    setOverviewOpen(next);
    if (next) fetchOverviewExplanation();
  }, [overviewOpen, setOverviewOpen, fetchOverviewExplanation]);

  return (
    <div className="command-center">
      <MapView onFeatureSelect={openRestriction} />

      <header className="top-bar">
        <div className="brand-mini">
          <h1>AccessFlow</h1>
          <span>Toronto operations console</span>
        </div>
        <div className="stats-chips" role="status" aria-label="Overview metrics">
          <span className="stat-chip"><strong>{total}</strong> restrictions</span>
          <span className="stat-chip"><strong>{evaluated}</strong> evaluated</span>
          <span className="stat-chip stat-high"><strong>{highCount}</strong> high impact</span>
          <button
            className={`toggle-chip ${overviewOpen ? "on" : ""}`}
            onClick={toggleOverview}
            title="Generate an evidence-grounded summary of the current disruption set"
          >
            ✦ AI summary
          </button>
        </div>
        <div className="status-wrap">
          <span className="status-dot" aria-hidden="true" />
          <span className={`status-banner ${status}`}>{statusText}</span>
        </div>
      </header>

      {overviewOpen && (
        <aside className="overview-card" aria-label="City-wide summary">
          <div className="explanation-head">
            <h4>What&apos;s happening city-wide</h4>
            <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
              {overviewExplanation && (
                <span className="explanation-method">{overviewExplanation.method}</span>
              )}
              <button className="icon-button" onClick={() => setOverviewOpen(false)} aria-label="Close summary" title="Close">×</button>
            </div>
          </div>
          {overviewExplanation ? (
            <>
              <p className="explanation-headline">{overviewExplanation.headline}</p>
              <p className="explanation-narrative">{overviewExplanation.narrative}</p>
              {overviewExplanation.bullets.length > 0 && (
                <ul className="explanation-bullets">
                  {overviewExplanation.bullets.map((bullet, i) => (
                    <li key={i}>{bullet}</li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="muted">Analyzing current evidence…</p>
          )}
        </aside>
      )}

      <ReviewQueuePanel onSelect={openRestriction} />

      <RouteBar />

      {detailLoading ? (
        <aside className="detail-panel floating visible-panel" aria-label="Restriction detail">
          <p className="loading" style={{ padding: "20px" }}>Loading restriction evidence…</p>
        </aside>
      ) : (
        <DetailPanel />
      )}

      <PredictionPanel />
      <div className="bottom-left-stack">
        <TimeScrubber />
        <LayerControls />
      </div>
    </div>
  );
}
