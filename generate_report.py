"""Generate the full analysis report and dashboard."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from models.impact_predictor import (
    load_restrictions, prepare_features, train_evaluate,
    ORIGINAL_FEATURES, EXTENDED_FEATURES
)
from visualization.charts import (
    chart_impact_distribution, chart_feature_importance,
    chart_model_comparison, chart_confusion_matrix,
    chart_network_topology
)
from visualization.dashboard import generate_dashboard

OUTPUT_DIR = Path("output")


def main():
    print("=== Generating AccessFlow Analysis Report ===\n")

    # 1. Load and prepare data
    print("1. Loading road restrictions data...")
    xml_path = Path("fixtures/road-restrictions--resource-3afea38a-baad-4f39-b22f-d608875e1746.xml")
    df = load_restrictions(xml_path)
    df = prepare_features(df)
    print(f"   Loaded {len(df)} closures")

    # 2. Train models
    print("\n2. Training models...")
    results = []

    print("   Training original model (9 features)...")
    result_original = train_evaluate(df, ORIGINAL_FEATURES)
    result_original["name"] = "Original (9 features)"
    results.append(result_original)
    print(f"   F1-score: {result_original['f1_score']:.4f}")

    print("   Training extended model (16 features)...")
    result_extended = train_evaluate(df, EXTENDED_FEATURES)
    result_extended["name"] = "Extended (16 features)"
    results.append(result_extended)
    print(f"   F1-score: {result_extended['f1_score']:.4f}")

    # 3. Generate charts
    print("\n3. Generating charts...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    chart_paths = []
    chart_paths.append(chart_impact_distribution(df))
    print(f"   Impact distribution: {chart_paths[-1]}")

    chart_paths.append(chart_feature_importance(result_original["feature_importance"], "Feature Importance (Original)"))
    print(f"   Feature importance (original): {chart_paths[-1]}")

    chart_paths.append(chart_feature_importance(result_extended["feature_importance"], "Feature Importance (Extended)"))
    print(f"   Feature importance (extended): {chart_paths[-1]}")

    chart_paths.append(chart_model_comparison(results))
    print(f"   Model comparison: {chart_paths[-1]}")

    best = max(results, key=lambda x: x["f1_score"])
    labels = list(set(best["y_test"]) | set(best["y_pred"]))
    chart_paths.append(chart_confusion_matrix(best["y_test"], best["y_pred"], sorted(labels)))
    print(f"   Confusion matrix: {chart_paths[-1]}")

    chart_paths.append(chart_network_topology())
    print(f"   Network topology: {chart_paths[-1]}")

    # 4. Generate dashboard
    print("\n4. Generating HTML dashboard...")
    dashboard_path = generate_dashboard(df, results, chart_paths, OUTPUT_DIR / "dashboard.html")
    print(f"   Dashboard: {dashboard_path}")

    # 5. Summary
    print("\n" + "=" * 60)
    print("REPORT GENERATION COMPLETE")
    print("=" * 60)
    print(f"\nOutput files:")
    print(f"  - Dashboard: {dashboard_path}")
    print(f"  - Charts: {OUTPUT_DIR}/charts/")
    print(f"\nModel Results:")
    for r in results:
        print(f"  - {r['name']}: F1={r['f1_score']:.4f}")
    print(f"\nBest model: {best['name']} (F1={best['f1_score']:.4f})")


if __name__ == "__main__":
    main()
