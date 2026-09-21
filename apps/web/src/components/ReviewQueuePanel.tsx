"use client";

import { useMemo, useRef, useEffect } from "react";
import { useStore } from "@/store/useStore";
import { filterAndSortRestrictions, formatMissing } from "@/lib/domain";

const CONFIDENCE_COLORS: Record<string, string> = {
  HIGH: "#087f8c",
  MEDIUM: "#b54708",
  LOW: "#7f56d9",
  INSUFFICIENT_EVIDENCE: "#667085",
  NOT_EVALUATED: "#98a2b3",
};

export default function ReviewQueuePanel({
  onSelect,
}: {
  onSelect: (restrictionId: string) => void;
}) {
  const restrictions = useStore((s) => s.restrictions);
  const filters = useStore((s) => s.filters);
  const setFilters = useStore((s) => s.setFilters);
  const activeRestrictionId = useStore((s) => s.activeRestrictionId);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(
    () => filterAndSortRestrictions(restrictions, filters),
    [restrictions, filters],
  );

  useEffect(() => {
    if (!activeRestrictionId || !listRef.current) return;
    const active = listRef.current.querySelector(
      `[data-restriction-id="${CSS.escape(activeRestrictionId)}"]`,
    );
    active?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeRestrictionId]);

  return (
    <aside className="queue-panel" aria-label="Review queue">
      <div className="queue-header">
        <div>
          <p className="eyebrow">Review queue</p>
          <h3>Restrictions</h3>
        </div>
        <span className="queue-count">{filtered.length}</span>
      </div>
      <div className="queue-filters">
        <input
          type="search"
          placeholder="Search street, area, or ID…"
          value={filters.query}
          onChange={(e) => setFilters({ query: e.target.value })}
          aria-label="Search restrictions"
        />
        <select
          value={filters.evidenceConfidence}
          onChange={(e) => setFilters({ evidenceConfidence: e.target.value })}
          aria-label="Filter by confidence"
        >
          <option value="">All confidence</option>
          <option>HIGH</option>
          <option>MEDIUM</option>
          <option>INSUFFICIENT_EVIDENCE</option>
        </select>
        <select
          value={filters.evaluationStatus}
          onChange={(e) => setFilters({ evaluationStatus: e.target.value })}
          aria-label="Filter by evaluation"
        >
          <option value="">All states</option>
          <option>EVALUATED</option>
          <option>NOT_EVALUATED</option>
        </select>
      </div>
      <div className="queue-list" ref={listRef}>
        {filtered.length === 0 && (
          <p className="muted" style={{ padding: "12px" }}>
            No restrictions match the current filters.
          </p>
        )}
        {filtered.map((item) => {
          const isActive = item.restriction_id === activeRestrictionId;
          const color = CONFIDENCE_COLORS[item.evidence_confidence] ?? "#98a2b3";
          const primaryLabel = item.location?.road || item.location?.name || item.restriction_id;
          const crossStreets =
            item.location?.from_road && item.location?.to_road
              ? `${item.location.from_road} → ${item.location.to_road}`
              : item.location?.name || "";
          return (
            <button
              key={item.restriction_id}
              data-restriction-id={item.restriction_id}
              className={`queue-row ${isActive ? "active" : ""}`}
              onClick={() => onSelect(item.restriction_id)}
              title={`${item.restriction_id}${crossStreets ? ` — ${crossStreets}` : ""}`}
            >
              <span className="queue-dot" style={{ background: color }} />
              <span className="queue-row-main">
                <span className="queue-id">{primaryLabel}</span>
                <span className="queue-sub">
                  {crossStreets
                    ? `${crossStreets} · impact ${formatMissing(item.impact_severity)}`
                    : `${formatMissing(item.match_type)} · impact ${formatMissing(item.impact_severity)}`}
                </span>
              </span>
              <span className="queue-badge">{item.candidate_edge_count}</span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
