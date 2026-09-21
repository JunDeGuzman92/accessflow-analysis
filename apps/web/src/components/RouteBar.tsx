"use client";

import { useCallback } from "react";
import { getExplanation, getRoute } from "@/lib/api-client";
import { useStore } from "@/store/useStore";

function formatDistance(meters: number | null | undefined): string {
  if (meters == null) return "—";
  if (meters >= 1000) return `${(meters / 1000).toFixed(2)} km`;
  return `${Math.round(meters)} m`;
}

export default function RouteBar() {
  const routePicking = useStore((s) => s.routePicking);
  const setRoutePicking = useStore((s) => s.setRoutePicking);
  const routeOrigin = useStore((s) => s.routeOrigin);
  const routeDestination = useStore((s) => s.routeDestination);
  const routeAvoid = useStore((s) => s.routeAvoid);
  const setRouteAvoid = useStore((s) => s.setRouteAvoid);
  const route = useStore((s) => s.route);
  const routeLoading = useStore((s) => s.routeLoading);
  const routeError = useStore((s) => s.routeError);
  const setRoute = useStore((s) => s.setRoute);
  const setRouteLoading = useStore((s) => s.setRouteLoading);
  const setRouteError = useStore((s) => s.setRouteError);
  const clearRoute = useStore((s) => s.clearRoute);
  const routeExplanation = useStore((s) => s.routeExplanation);
  const setRouteExplanation = useStore((s) => s.setRouteExplanation);
  const routeNearbyCount = useStore((s) => s.routeNearbyCount);
  const activeRestrictionId = useStore((s) => s.activeRestrictionId);
  const startWalk = useStore((s) => s.startWalk);
  const setWalkOverridePath = useStore((s) => s.setWalkOverridePath);
  const stopWalk = useStore((s) => s.stopWalk);
  const isWalking = useStore((s) => s.isWalking);

  const canFindRoute = routeOrigin !== null && routeDestination !== null && !routeLoading;

  const findRoute = useCallback(async () => {
    if (!routeOrigin || !routeDestination) return;
    setRouteLoading(true);
    setRouteError(null);
    setRouteExplanation(null);
    let avoidParam: string | null = null;
    if (routeAvoid === "all") avoidParam = "all";
    if (routeAvoid === "selected" && activeRestrictionId) avoidParam = activeRestrictionId;
    try {
      const response = await getRoute(routeOrigin, routeDestination, avoidParam);
      setRoute(response);
      getExplanation({
        origin: routeOrigin,
        destination: routeDestination,
        avoid: avoidParam,
      })
        .then(setRouteExplanation)
        .catch(() => setRouteExplanation(null));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Route request failed.";
      setRouteError(`Unable to compute route: ${message}`);
    } finally {
      setRouteLoading(false);
    }
  }, [routeOrigin, routeDestination, routeAvoid, activeRestrictionId, setRoute, setRouteError, setRouteLoading, setRouteExplanation]);

  const walkRoute = useCallback(() => {
    const geometry = route?.recommended?.geometry ?? route?.baseline?.geometry;
    if (!geometry || geometry.type !== "LineString") return;
    const coords = geometry.coordinates as number[][];
    if (coords.length < 2) return;
    setWalkOverridePath(coords as [number, number][]);
    startWalk();
  }, [route, setWalkOverridePath, startWalk]);

  const stopWalking = useCallback(() => {
    stopWalk();
    setWalkOverridePath(null);
  }, [stopWalk, setWalkOverridePath]);

  const avoidDisabled = routeAvoid === "selected" && !activeRestrictionId;

  return (
    <div className="route-bar-wrap" aria-label="Accessible routing">
      <div className="route-bar">
        <button
          className={`toggle-chip ${routePicking === "origin" ? "on picking" : ""} ${routeOrigin ? "set" : ""}`}
          onClick={() => setRoutePicking(routePicking === "origin" ? null : "origin")}
          title="Click the map to set the route origin"
        >
          {routePicking === "origin" ? "Click map…" : routeOrigin ? "● Origin set" : "Set origin"}
        </button>
        <button
          className={`toggle-chip ${routePicking === "destination" ? "on picking" : ""} ${routeDestination ? "set" : ""}`}
          onClick={() => setRoutePicking(routePicking === "destination" ? null : "destination")}
          title="Click the map to set the route destination"
        >
          {routePicking === "destination" ? "Click map…" : routeDestination ? "◆ Destination set" : "Set destination"}
        </button>
        <label className="route-avoid" title="Candidate segments are evidence, not confirmed closures">
          Avoid
          <select value={routeAvoid} onChange={(e) => setRouteAvoid(e.target.value as typeof routeAvoid)}>
            <option value="none">nothing</option>
            <option value="selected" disabled={!activeRestrictionId}>
              selected restriction{activeRestrictionId ? "" : " (none selected)"}
            </option>
            <option value="all">all represented disruptions</option>
          </select>
        </label>
        <button className="toggle-chip route-find" onClick={findRoute} disabled={!canFindRoute} title="Compute routes on the real pedestrian network">
          {routeLoading ? "Routing…" : "Find route"}
        </button>
        {(route || routeOrigin || routeDestination) && (
          <button className="toggle-chip" onClick={clearRoute} title="Clear route inputs and results">
            Clear
          </button>
        )}
      </div>

      {routeError && <div className="route-error">{routeError}</div>}

      {route && (
        <div className="route-results">
          <div className="route-results-head">
            <strong>Route comparison</strong>
            <button className="icon-button" onClick={clearRoute} aria-label="Close route results" title="Close">×</button>
          </div>
          {!route.reachable ? (
            <p className="route-unreachable">
              Origin and destination are on disconnected parts of the pedestrian network —
              no walking route exists between them in the current data.
            </p>
          ) : (
            <>
              <div className="route-compare">
                <div className="route-compare-col baseline">
                  <h5>Baseline</h5>
                  <span>{formatDistance(route.baseline.distance_m)}</span>
                  <span>{route.baseline.edge_count} segments</span>
                  {route.baseline.barriers_on_path > 0 && (
                    <span className="route-barrier-warn">
                      crosses {route.baseline.barriers_on_path} barrier segment{route.baseline.barriers_on_path === 1 ? "" : "s"}
                    </span>
                  )}
                </div>
                <div className="route-compare-col recommended">
                  <h5>{route.recommended ? "Recommended" : "No detour"}</h5>
                  {route.recommended ? (
                    <>
                      <span>{formatDistance(route.recommended.distance_m)}</span>
                      <span>{route.recommended.edge_count} segments</span>
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </div>
              </div>
              {route.comparison && route.recommended && (
                <div className="route-comparison-line">
                  {route.comparison.added_distance_m !== null && route.comparison.added_distance_m > 0 ? (
                    <>
                      Detour adds <strong>{formatDistance(route.comparison.added_distance_m)}</strong>
                      {route.comparison.distance_ratio !== null && <> ({route.comparison.distance_ratio}×)</>}
                      {route.comparison.avoided_barrier_count > 0 && (
                        <> · avoids <strong>{route.comparison.avoided_barrier_count}</strong> barrier segment{route.comparison.avoided_barrier_count === 1 ? "" : "s"}</>
                      )}
                    </>
                  ) : (
                    <>Shortest available path — no additional distance from avoidance.</>
                  )}
                </div>
              )}
              {routeNearbyCount > 0 && (
                <div className="route-nearby-line">
                  <span className="route-nearby-badge" aria-hidden="true">●</span>
                  <strong>{routeNearbyCount}</strong> represented disruption{routeNearbyCount === 1 ? "" : "s"} within 75 m of this route
                  <span className="muted"> — highlighted on the map</span>
                </div>
              )}
              {route.route_character && (
                <div className="route-character" aria-label="Route character from source network data">
                  <h5>Route character</h5>
                  <div className="route-character-chips">
                    {Object.entries(route.route_character.sidewalk_counts)
                      .sort((a, b) => b[1] - a[1])
                      .slice(0, 3)
                      .map(([sidewalk, count]) => (
                        <span key={sidewalk} className="character-chip sidewalk" title={`${count} path segments: ${sidewalk}`}>
                          {sidewalk} ×{count}
                        </span>
                      ))}
                    {route.route_character.crosswalk_count > 0 && (
                      <span className="character-chip crosswalk" title="Path segments flagged as crosswalks in the source network">
                        crosswalks ×{route.route_character.crosswalk_count}
                      </span>
                    )}
                    {route.route_character.pedestrian_signal_count > 0 && (
                      <span className="character-chip signal" title="Path segments with a pedestrian signal (PX) in the source network">
                        signals ×{route.route_character.pedestrian_signal_count}
                      </span>
                    )}
                    {Object.keys(route.route_character.road_type_counts).length > 0 && (
                      <span className="character-chip roadtype" title="Path segments per road type from the source network">
                        {Object.entries(route.route_character.road_type_counts)
                          .sort((a, b) => b[1] - a[1])
                          .map(([type, count]) => `${type.toLowerCase()} ×${count}`)
                          .join(" · ")}
                      </span>
                    )}
                  </div>
                </div>
              )}
              {!route.recommended && route.baseline.barriers_on_path > 0 && (
                <div className="route-comparison-line">
                  No alternative path exists after avoiding these candidate segments.
                </div>
              )}
              {routeExplanation && (
                <div className="explanation-card route-explanation">
                  <div className="explanation-head">
                    <h4>Why this route?</h4>
                    <span className="explanation-method">{routeExplanation.method}</span>
                  </div>
                  <p className="explanation-headline">{routeExplanation.headline}</p>
                  <p className="explanation-narrative">{routeExplanation.narrative}</p>
                </div>
              )}
              <div className="route-actions">
                {(route.recommended?.geometry || route.baseline.geometry) && !isWalking && (
                  <button className="secondary-button walk-button" onClick={walkRoute}>
                    ▶ Walk this route
                  </button>
                )}
                {isWalking && (
                  <button className="secondary-button stop-walk-button" onClick={stopWalking}>
                    ■ Stop walk
                  </button>
                )}
              </div>
              <p className="route-limitations">
                Candidate segments are not confirmed closures · lengths use a haversine approximation ·
                topology derived from the Toronto pedestrian network.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
