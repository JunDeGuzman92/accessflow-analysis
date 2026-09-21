"use client";

import { useState } from "react";
import { predictImpact } from "@/lib/api-client";
import { useStore } from "@/store/useStore";
import type { PredictionRequest } from "@/lib/types";

export default function PredictionPanel() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const setPredictionResult = useStore((s) => s.setPredictionResult);
  const setPredictionLocation = useStore((s) => s.setPredictionLocation);
  const predictionResult = useStore((s) => s.predictionResult);
  const selectedDetail = useStore((s) => s.selectedDetail);
  const [coords, setCoords] = useState<[number, number]>([-79.3832, 43.6532]);
  const [durationDays, setDurationDays] = useState(30);

  const useSelectedLocation = () => {
    const c = selectedDetail?.coordinates;
    if (c && c.length === 2) {
      setCoords([c[0], c[1]]);
      if (selectedDetail?.duration_hours != null) {
        setDurationDays(Math.max(1, Math.round(selectedDetail.duration_hours / 24)));
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const formData = new FormData(e.currentTarget);
    const data = Object.fromEntries(formData.entries());
    const request: PredictionRequest = {
      type: data.type as string,
      road_class: data.road_class as string,
      directions_affected: data.directions_affected as string,
      work_period: data.work_period as string,
      district: data.district as string,
      latitude: coords[1],
      longitude: coords[0],
      duration_days: durationDays,
      special_event: (data.special_event as string) || "No",
    };

    try {
      const result = await predictImpact(request);
      setPredictionResult(result);
      setPredictionLocation([request.longitude, request.latitude]);
    } catch (err) {
      setError("Prediction failed. Make sure the API is running.");
      console.error("Prediction failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const hasSelectionCoords = Boolean(
    selectedDetail?.coordinates && selectedDetail.coordinates.length === 2,
  );

  return (
    <section className={`predict-panel ${open ? "open" : ""}`} aria-label="Impact prediction">
      <button className="predict-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="predict-toggle-dot" aria-hidden="true" />
        What-if: predict impact
        <span className="predict-chevron" aria-hidden="true">{open ? "▾" : "▴"}</span>
      </button>
      {open && (
        <div className="predict-body">
          <p className="predict-hint">
            <strong>What this is:</strong> the same impact-classification model that labels every
            restriction in the review queue. Describe a hypothetical closure — or reuse a selected
            restriction&apos;s location — and the model predicts its pedestrian-network impact level.
          </p>
          <p className="muted predict-hint">
            The result drops an <strong>ML marker on the map</strong> at that location, so you can compare
            it against nearby represented restrictions (colored dots) and plan routes around them.
          </p>
          {hasSelectionCoords && (
            <button
              type="button"
              className="secondary-button predict-prefill"
              onClick={useSelectedLocation}
              title="Copy the selected restriction's coordinates and duration into the form"
            >
              ⌖ Use selected restriction&apos;s location
            </button>
          )}
          <form onSubmit={handleSubmit} className="predict-form">
            <div className="form-grid">
              <label>
                Closure Type
                <select name="type" required defaultValue="CONSTRUCTION">
                  <option value="CONSTRUCTION">Construction</option>
                  <option value="ROAD_CLOSED">Road Closed</option>
                </select>
              </label>
              <label>
                Road Class
                <select name="road_class" required defaultValue="Major Arterial Road">
                  <option value="Major Arterial Road">Major Arterial</option>
                  <option value="Local Road">Local Road</option>
                  <option value="Minor Arterial Road">Minor Arterial</option>
                  <option value="Collector">Collector</option>
                </select>
              </label>
              <label>
                Directions
                <select name="directions_affected" required defaultValue="ONE_DIRECTION">
                  <option value="ONE_DIRECTION">One Direction</option>
                  <option value="BOTH_DIRECTIONS">Both Directions</option>
                </select>
              </label>
              <label>
                Work Period
                <select name="work_period" required defaultValue="Continuous">
                  <option value="Continuous">Continuous</option>
                  <option value="Daily">Daily</option>
                  <option value="Weekdays">Weekdays</option>
                  <option value="Weekends">Weekends</option>
                </select>
              </label>
              <label>
                District
                <select name="district" required defaultValue="Toronto and East York">
                  <option value="Toronto and East York">Toronto &amp; East York</option>
                  <option value="Scarborough">Scarborough</option>
                  <option value="Etobicoke York">Etobicoke York</option>
                  <option value="North York">North York</option>
                </select>
              </label>
              <label>
                Special Event
                <select name="special_event" defaultValue="No">
                  <option value="No">No</option>
                  <option value="Yes">Yes</option>
                </select>
              </label>
              <label>
                Latitude
                <input
                  type="number" name="latitude" step="0.0001" required
                  value={coords[1]}
                  onChange={(e) => setCoords([coords[0], parseFloat(e.target.value) || 0])}
                />
              </label>
              <label>
                Longitude
                <input
                  type="number" name="longitude" step="0.0001" required
                  value={coords[0]}
                  onChange={(e) => setCoords([parseFloat(e.target.value) || 0, coords[1]])}
                />
              </label>
              <label>
                Duration (days)
                <input
                  type="number" name="duration_days" step="1" required
                  value={durationDays}
                  onChange={(e) => setDurationDays(parseInt(e.target.value, 10) || 1)}
                />
              </label>
            </div>
            <button type="submit" className="primary-button" disabled={loading}>
              {loading ? "Predicting…" : "Predict impact"}
            </button>
          </form>
          {error && <p className="error-text">{error}</p>}
          {predictionResult && (
            <div className="prediction-result">
              <h4>Model prediction</h4>
              <p className="muted predict-hint">
                The marker on the map marks the predicted location. Nearby dots show represented
                restrictions — select one to compare its <em>actual</em> modeled impact with this
                hypothetical one.
              </p>
              <div className="result-grid">
                <div className="result-item">
                  <span className="result-label">Impact Level</span>
                  <span className={`result-value impact-${predictionResult.prediction.toLowerCase()}`}>
                    {predictionResult.prediction}
                  </span>
                </div>
                <div className="result-item">
                  <span className="result-label">Confidence</span>
                  <span className="result-value">
                    {(predictionResult.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
              <div className="probabilities">
                {Object.entries(predictionResult.probabilities).map(([cls, prob]) => {
                  const pct = (prob * 100).toFixed(1);
                  const color = cls === "High" ? "#e74c3c" : cls === "Low" ? "#f39c12" : "#2ecc71";
                  return (
                    <div key={cls} className="prob-bar">
                      <span className="prob-label">{cls}</span>
                      <div className="prob-track">
                        <div className="prob-fill" style={{ width: `${pct}%`, background: color }} />
                      </div>
                      <span className="prob-value">{pct}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
