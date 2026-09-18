"""Model performance monitoring and drift detection."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class PredictionLog:
    """Log entry for a single prediction."""
    timestamp: str
    prediction: str
    confidence: float
    probabilities: dict[str, float]
    input_features: dict[str, float]


@dataclass
class DriftReport:
    """Report on model drift detection."""
    timestamp: str
    baseline_distribution: dict[str, float]
    current_distribution: dict[str, float]
    drift_detected: bool
    drift_magnitude: float
    threshold: float


class ModelMonitor:
    """Monitor model predictions and detect drift."""

    def __init__(
        self,
        log_dir: Path,
        baseline_distribution: Optional[dict[str, float]] = None,
        drift_threshold: float = 0.1,
    ) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_distribution = baseline_distribution or {"None": 0.78, "Low": 0.13, "High": 0.09}
        self.drift_threshold = drift_threshold
        self.log_file = self.log_dir / "predictions.jsonl"

    def log_prediction(self, log: PredictionLog) -> None:
        """Append a prediction log entry."""
        with open(self.log_file, "a") as f:
            f.write(json.dumps({
                "timestamp": log.timestamp,
                "prediction": log.prediction,
                "confidence": log.confidence,
                "probabilities": log.probabilities,
                "input_features": log.input_features,
            }) + "\n")

    def get_recent_predictions(self, n: int = 100) -> list[dict]:
        """Get the last n predictions from the log."""
        if not self.log_file.exists():
            return []

        with open(self.log_file) as f:
            lines = f.readlines()

        recent = lines[-n:] if len(lines) > n else lines
        return [json.loads(line) for line in recent]

    def compute_distribution(self, predictions: list[dict]) -> dict[str, float]:
        """Compute the distribution of predictions."""
        if not predictions:
            return {}

        counts = {}
        for pred in predictions:
            label = pred["prediction"]
            counts[label] = counts.get(label, 0) + 1

        total = len(predictions)
        return {k: v / total for k, v in counts.items()}

    def detect_drift(self, n: int = 100) -> DriftReport:
        """Detect drift by comparing recent predictions to baseline."""
        recent = self.get_recent_predictions(n)
        current_dist = self.compute_distribution(recent)

        # Compute drift magnitude (Jensen-Shannon divergence approximation)
        all_labels = set(self.baseline_distribution.keys()) | set(current_dist.keys())
        drift_magnitude = 0.0
        for label in all_labels:
            p = self.baseline_distribution.get(label, 0.0)
            q = current_dist.get(label, 0.0)
            if p > 0 and q > 0:
                m = (p + q) / 2
                drift_magnitude += 0.5 * (p * np.log(p / m) + q * np.log(q / m))

        return DriftReport(
            timestamp=datetime.utcnow().isoformat(),
            baseline_distribution=self.baseline_distribution,
            current_distribution=current_dist,
            drift_detected=drift_magnitude > self.drift_threshold,
            drift_magnitude=drift_magnitude,
            threshold=self.drift_threshold,
        )

    def get_summary(self) -> dict:
        """Get a summary of monitoring metrics."""
        recent = self.get_recent_predictions(1000)
        if not recent:
            return {"status": "no_predictions"}

        dist = self.compute_distribution(recent)
        avg_confidence = np.mean([p["confidence"] for p in recent])

        return {
            "total_predictions": len(recent),
            "distribution": dist,
            "average_confidence": float(avg_confidence),
            "baseline_distribution": self.baseline_distribution,
        }
