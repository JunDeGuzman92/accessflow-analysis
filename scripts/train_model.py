"""Train and save the XGBoost impact prediction model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.impact_predictor import load_restrictions, prepare_features
from packages.python.accessflow_ml.models import ImpactPredictor


def main():
    xml_path = list(Path("fixtures").glob("road-restrictions--resource-*.xml"))[0]
    print(f"Loading from {xml_path}")
    df = load_restrictions(xml_path)
    df = prepare_features(df)
    print(f"Loaded {len(df)} records")

    predictor = ImpactPredictor()
    meta = predictor.fit(df)
    print(f"Trained: {meta.training_samples} samples, F1={meta.f1_score}")

    model_dir = Path("data/models/impact")
    predictor.save(model_dir)
    print(f"Saved to {model_dir}")
    for f in model_dir.iterdir():
        print(f"  {f.name} ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
