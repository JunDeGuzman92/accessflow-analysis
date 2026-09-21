"use client";

import { useMemo } from "react";
import { useStore } from "@/store/useStore";
import {
  mapMatches,
  mapNetworkImpact,
  mapRestrictionDetail,
  formatMissing,
  isUsableGeoJson,
} from "@/lib/domain";
import type { MatchResponse, NetworkImpactResponse, RestrictionDetailResponse } from "@/lib/types";

const CONFIDENCE_COLORS: Record<string, string> = {
  HIGH: "#087f8c",
  MEDIUM: "#b54708",
  LOW: "#7f56d9",
  INSUFFICIENT_EVIDENCE: "#667085",
  NOT_EVALUATED: "#98a2b3",
};

const IMPACT_COLORS: Record<string, string> = {
  High: "#e74c3c",
  Low: "#f39c12",
  NOT_EVALUATED: "#98a2b3",
};

function display(value: unknown): string {
  return formatMissing(value);
}

function formatDurationDisplay(hours: number | null): string {
  if (hours == null) return "N/A";
  if (hours >= 24) {
    return `${Math.round(hours / 24)} days (${Math.round(hours)}h)`;
  }
  return `${Math.round(hours)} hours`;
}

export default function DetailPanel() {
  const rawDetail = useStore((s) => s.selectedDetail) as RestrictionDetailResponse | null;
  const rawMatches = useStore((s) => s.selectedMatches) as MatchResponse[];
  const rawImpacts = useStore((s) => s.selectedImpacts) as NetworkImpactResponse[];
  const clearSelection = useStore((s) => s.clearSelection);
  const focusEvidence = useStore((s) => s.focusEvidence);
  const startWalk = useStore((s) => s.startWalk);
  const stopWalk = useStore((s) => s.stopWalk);
  const isWalking = useStore((s) => s.isWalking);
  const groundView = useStore((s) => s.groundView);
  const setGroundView = useStore((s) => s.setGroundView);
  const explanation = useStore((s) => s.explanation);
  const explanationLoading = useStore((s) => s.explanationLoading);

  const decisionSteps = useMemo(() => {
    if (!rawDetail) return [] as { title: string; detail: string }[];
    const detail = mapRestrictionDetail(rawDetail);
    const impacts = mapNetworkImpact(rawImpacts);
    const steps: { title: string; detail: string }[] = [];
    const severity = detail.impact_severity;
    const hasReplacement = impacts.some(
      (impact) => impact.alternative_path_edge_count > 0,
    );
    const connectivityLoss = impacts.some(
      (impact) => impact.local_connectivity_loss_count > 0,
    );
    const longDuration = detail.duration_hours != null && detail.duration_hours >= 24 * 14;

    if (severity === "High" || severity === "SEVERE" || connectivityLoss) {
      steps.push({
        title: "Escalate for accessibility planning review",
        detail: connectivityLoss
          ? "The modeled network loses connectivity when these candidate segments are removed — there may be no reasonable walking detour. Escalate to mobility planning and accessibility services."
          : "High modeled impact: the replacement path is substantial or impractical for pedestrians with limited mobility. Route to accessibility planning review.",
      });
    }
    steps.push(
      hasReplacement
        ? {
            title: "Validate the modeled detour in the field",
            detail: "A replacement path exists in the network model. Walk the modeled detour to confirm it is passable (curb cuts, width, surface) before communicating it as an alternative.",
          }
        : {
            title: "No modeled detour — verify before communicating alternatives",
            detail: "The current artifacts do not contain a viable replacement path. Confirm conditions on site before advising pedestrians on alternate routes.",
          },
    );
    if (detail.evidence_confidence === "INSUFFICIENT_EVIDENCE" || detail.evidence_confidence === "NOT_EVALUATED") {
      steps.push({
        title: "Strengthen the evidence record",
        detail: "Spatial evidence is weak for this restriction. Cross-check the source permit and on-site conditions before treating the modeled impact as actionable.",
      });
    }
    if (longDuration) {
      steps.push({
        title: "Plan for a long disruption window",
        detail: "The source feed indicates a multi-week disruption. Consider proactive wayfinding signage and notifying nearby facilities and transit stops serving pedestrians with disabilities.",
      });
    }
    steps.push({
      title: "Publish with limitations",
      detail: "Candidate segments are evidence, not confirmed closures. Any public communication should state that closure status and detour quality come from modeled analytical artifacts.",
    });
    return steps;
  }, [rawDetail, rawImpacts]);

  if (!rawDetail) {
    return (
      <aside className="detail-panel floating hidden-panel" aria-label="Restriction detail">
        <div className="detail-empty">
          <p className="muted">Click a restriction on the map or in the queue to inspect its evidence.</p>
        </div>
      </aside>
    );
  }

  const detail = mapRestrictionDetail(rawDetail);
  const matches = mapMatches(rawMatches);
  const impacts = mapNetworkImpact(rawImpacts);
  const hasWalkableGeometry = matches.some((m) => m.geometry && isUsableGeoJson(m.geometry));

  const geometryMessage = detail.restriction_geometry
    ? "Geometry supplied by current API artifact."
    : "Geometry not available from current API artifact.";

  return (
    <aside className="detail-panel floating visible-panel" aria-label="Restriction detail">
      <div className="detail-heading">
        <div>
          <p className="eyebrow">Restriction detail</p>
          <h3>{detail.restriction_id}</h3>
          {rawDetail?.location?.name && (
            <p className="detail-location" title="Publisher-provided location from the source feed">
              📍 {rawDetail.location.name}
            </p>
          )}
          {!rawDetail?.location?.name && rawDetail?.location?.road && (
            <p className="detail-location" title="Publisher-provided road name from the source feed">
              📍 {rawDetail.location.road}
              {rawDetail.location.from_road && rawDetail.location.to_road
                ? ` (${rawDetail.location.from_road} → ${rawDetail.location.to_road})`
                : ""}
            </p>
          )}
        </div>
        <div className="detail-actions">
          <span
            className="state-chip prominent"
            style={{
              borderColor: CONFIDENCE_COLORS[detail.evidence_confidence] || "#bcccdc",
              color: CONFIDENCE_COLORS[detail.evidence_confidence] || "inherit",
            }}
          >
            {display(detail.evidence_confidence)}
          </span>
          <span
            className="state-chip"
            style={{
              borderColor: IMPACT_COLORS[detail.impact_severity] || "#bcccdc",
              color: IMPACT_COLORS[detail.impact_severity] || "inherit",
            }}
          >
            {display(detail.impact_severity)}
          </span>
        </div>
        <button className="icon-button" onClick={clearSelection} aria-label="Close detail panel" title="Close">
          ×
        </button>
      </div>
      <div className="detail-actions-row">
        <button className="secondary-button" onClick={focusEvidence} title="Zoom to evidence on the map">
          Focus evidence
        </button>
        {!isWalking && (
          <button
            className={`secondary-button ${groundView ? "on" : ""}`}
            onClick={() => setGroundView(!groundView)}
            title="Toggle ground-level perspective — drag to orbit freely"
          >
            {groundView ? "● Ground view on" : "○ Ground view"}
          </button>
        )}
        {hasWalkableGeometry && !isWalking && (
          <button className="secondary-button walk-button" onClick={startWalk} title="Animated walk along affected segments (optional)">
            ▶ Walk affected segments
          </button>
        )}
        {isWalking && (
          <button className="secondary-button stop-walk-button" onClick={stopWalk} title="Stop the street-level walk">
            ■ Stop walk
          </button>
        )}
      </div>
      <div className="detail-scroll">
        {(explanation || explanationLoading) && (
          <section className="explanation-card">
            <div className="explanation-head">
              <h4>Why it matters</h4>
              {explanation && (
                <span className="explanation-method">{explanation.method}</span>
              )}
            </div>
            {explanationLoading && !explanation ? (
              <p className="muted">Analyzing evidence…</p>
            ) : explanation ? (
              <>
                <p className="explanation-headline">{explanation.headline}</p>
                <p className="explanation-narrative">{explanation.narrative}</p>
                {explanation.bullets.length > 0 && (
                  <ul className="explanation-bullets">
                    {explanation.bullets.map((bullet, i) => (
                      <li key={i}>{bullet}</li>
                    ))}
                  </ul>
                )}
              </>
            ) : null}
          </section>
        )}
        <section className="decision-framework" aria-label="Recommended next steps">
          <h4>Recommended next steps</h4>
          <p className="decision-note">
            Suggested actions derived from this restriction&apos;s evidence — modeled severity, detour
            availability, and source duration — by the deterministic rule engine.
          </p>
          <ol className="decision-steps">
            {decisionSteps.map((step, i) => (
              <li key={i}>
                <strong>{step.title}</strong>
                <span>{step.detail}</span>
              </li>
            ))}
          </ol>
        </section>
        <div className="detail-grid">
          <section>
            <h4>Key metrics</h4>
            <dl>
              <div><dt>Evaluation status</dt><dd>{display(detail.evaluation_status)}</dd></div>
              <div><dt>Candidate segments</dt><dd>{display(detail.candidate_edge_count)}</dd></div>
              <div><dt>Duration</dt><dd>{formatDurationDisplay(detail.duration_hours)}</dd></div>
              <div><dt>Valid polyline</dt><dd>{detail.valid_restriction_polyline ? "Yes" : "No"}</dd></div>
              <div><dt>Fallback geometry</dt><dd>{detail.fallback_geometry_used ? "Yes" : "No"}</dd></div>
              <div><dt>Publisher</dt><dd>{display(detail.source_publisher)}</dd></div>
            </dl>
          </section>
          <section>
            <h4>Spatial match evidence</h4>
            {matches.length > 0 ? (
              <table className="match-table">
                <thead>
                  <tr>
                    <th>Feature</th>
                    <th>Type</th>
                    <th>Conf.</th>
                    <th style={{ textAlign: "right" }}>Dist.</th>
                  </tr>
                </thead>
                <tbody>
                  {matches.slice(0, 8).map((match) => (
                    <tr key={match.pedestrian_feature_id}>
                      <td className="match-id">{match.pedestrian_feature_id}</td>
                      <td>{match.match_type}</td>
                      <td>
                        <span style={{ color: CONFIDENCE_COLORS[match.evidence_confidence] || "#333" }}>
                          {match.evidence_confidence}
                        </span>
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {match.distance_m != null ? `${match.distance_m.toFixed(1)} m` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">No candidate segments recorded.</p>
            )}
            {matches.length > 8 && (
              <p className="muted more-matches">+ {matches.length - 8} more matches</p>
            )}
          </section>
        </div>
        <section className="map-panel">
          <h4>Geometry status</h4>
          <p>{geometryMessage}</p>
          {matches.some((match) => match.geometry) ? (
            <p className="geometry-present">Candidate geometry is present — shown as glowing segments and a 3D ribbon on the map.</p>
          ) : (
            <p className="muted">No candidate geometry is available to draw.</p>
          )}
        </section>
        {impacts.length > 0 && (
          <section>
            <h4>Route comparison — replacement-path analysis</h4>
            {impacts.map((impact) => (
              <article key={impact.scenario} className="compare-card">
                <div className="compare-head">
                  <strong>{impact.scenario}</strong>
                  <span className="state-chip">{display(impact.evaluation_status)}</span>
                </div>
                <div className="compare-cols">
                  <div className="compare-col affected">
                    <h5>Affected route</h5>
                    <span>{impact.candidate_edge_count} candidate segments</span>
                    <span>{impact.evaluated_edge_count} evaluated edges</span>
                    <span>Connectivity loss: {display(impact.local_connectivity_loss_count)}</span>
                  </div>
                  <div className="compare-col replacement">
                    <h5>Best available detour</h5>
                    <span>{impact.alternative_path_edge_count} alternative-path edges</span>
                    <span>
                      Added distance: {display(impact.median_added_replacement_distance_m)}m median /{" "}
                      {display(impact.max_added_replacement_distance_m)}m max
                    </span>
                    <span>
                      Replacement ratio: {display(impact.median_replacement_ratio)} median /{" "}
                      {display(impact.max_replacement_ratio)} max
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </section>
        )}
        {detail.limitations.length > 0 && (
          <section>
            <h4>Limitations</h4>
            <ul>
              {detail.limitations.map((limit, i) => (
                <li key={i}>{limit}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </aside>
  );
}
