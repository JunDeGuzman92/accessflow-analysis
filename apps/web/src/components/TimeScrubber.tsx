"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "@/store/useStore";
import { filterAndSortRestrictions } from "@/lib/domain";

const SPEEDS: { label: string; hoursPerSecond: number }[] = [
  { label: "Slow", hoursPerSecond: 40 },
  { label: "Normal", hoursPerSecond: 120 },
  { label: "Fast", hoursPerSecond: 400 },
];

function formatHours(hours: number): string {
  if (hours >= 24) {
    return `${Math.round(hours / 24)}d`;
  }
  return `${Math.round(hours)}h`;
}

export default function TimeScrubber() {
  const restrictions = useStore((s) => s.restrictions);
  const filters = useStore((s) => s.filters);
  const timeFilterHours = useStore((s) => s.timeFilterHours);
  const setTimeFilterHours = useStore((s) => s.setTimeFilterHours);
  const isTimePlaying = useStore((s) => s.isTimePlaying);
  const setIsTimePlaying = useStore((s) => s.setIsTimePlaying);
  const [speedIndex, setSpeedIndex] = useState(1);
  const rafRef = useRef<number>(0);
  const lastTickRef = useRef<number>(0);

  const filtered = useMemo(
    () => filterAndSortRestrictions(restrictions, filters),
    [restrictions, filters],
  );

  const maxHours = useMemo(() => {
    const durations = filtered
      .map((r) => r.duration_hours)
      .filter((h): h is number => h != null && h > 0);
    return durations.length ? Math.ceil(Math.max(...durations)) : 0;
  }, [filtered]);

  const currentHours = timeFilterHours ?? 0;

  const activeCount = useMemo(() => {
    if (currentHours <= 0) return filtered.length;
    return filtered.filter(
      (r) => r.duration_hours != null && currentHours <= r.duration_hours,
    ).length;
  }, [filtered, currentHours]);

  useEffect(() => {
    if (!isTimePlaying || maxHours <= 0) {
      lastTickRef.current = 0;
      return;
    }
    const hoursPerSecond = SPEEDS[speedIndex].hoursPerSecond;

    const tick = (now: number) => {
      if (!lastTickRef.current) lastTickRef.current = now;
      const elapsedSeconds = (now - lastTickRef.current) / 1000;
      lastTickRef.current = now;
      const next = currentHours + elapsedSeconds * hoursPerSecond;
      if (next >= maxHours) {
        setTimeFilterHours(0);
        setIsTimePlaying(false);
        return;
      }
      setTimeFilterHours(next);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
      lastTickRef.current = 0;
    };
  }, [isTimePlaying, speedIndex, currentHours, maxHours, setTimeFilterHours, setIsTimePlaying]);

  const handlePlay = () => {
    if (maxHours <= 0) return;
    setIsTimePlaying(true);
    if ((timeFilterHours ?? 0) >= maxHours) {
      setTimeFilterHours(0);
    }
  };

  const handleReset = () => {
    setIsTimePlaying(false);
    setTimeFilterHours(null);
  };

  if (!restrictions.length || maxHours <= 0) return null;

  return (
    <div className="time-scrubber" aria-label="Closure duration timeline">
      <div className="time-scrubber-controls">
        <button
          className={`toggle-chip ${isTimePlaying ? "on" : ""}`}
          onClick={isTimePlaying ? () => setIsTimePlaying(false) : handlePlay}
          title={isTimePlaying ? "Pause the timeline" : "Play the closure timeline"}
        >
          {isTimePlaying ? "❚❚" : "▶"}
        </button>
        <button className="toggle-chip" onClick={handleReset} title="Reset to show all closures">
          ⟲
        </button>
        <select
          value={speedIndex}
          onChange={(e) => setSpeedIndex(Number(e.target.value))}
          aria-label="Playback speed"
          title="Playback speed"
        >
          {SPEEDS.map((speed, i) => (
            <option key={speed.label} value={i}>
              {speed.label}
            </option>
          ))}
        </select>
      </div>
      <div className="time-scrubber-slider">
        <span className="time-label">{formatHours(currentHours)}</span>
        <input
          type="range"
          min={0}
          max={maxHours}
          step={1}
          value={currentHours}
          onChange={(e) => {
            setIsTimePlaying(false);
            setTimeFilterHours(Number(e.target.value));
          }}
          aria-label="Closure duration timeline (hours)"
        />
        <span className="time-label">{formatHours(maxHours)}</span>
      </div>
      <div className="time-scrubber-stats">
        <strong>{activeCount}</strong> active closures
        {currentHours > 0 ? (
          <span className="muted"> at {formatHours(currentHours)} into disruption</span>
        ) : (
          <span className="muted"> (all)</span>
        )}
      </div>
    </div>
  );
}
