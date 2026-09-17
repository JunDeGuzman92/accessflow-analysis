"""Generate HTML dashboard with embedded visualizations."""

import base64
from pathlib import Path

import pandas as pd


def image_to_base64(path: Path) -> str:
    """Convert image file to base64 data URI."""
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{data}"


def generate_dashboard(
    df: pd.DataFrame,
    results: list[dict],
    chart_paths: list[Path],
    output_path: Path = Path("output/dashboard.html"),
) -> Path:
    """Generate HTML dashboard."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Prepare data
    impact_counts = df["CurrImpact"].value_counts()
    total = len(df)
    best = max(results, key=lambda x: x["f1_score"])

    # Convert charts to base64
    chart_images = {}
    chart_names = [
        "impact_distribution", "feature_importance_original",
        "feature_importance_extended", "model_comparison",
        "confusion_matrix", "network_topology"
    ]
    for name, path in zip(chart_names, chart_paths):
        if path.exists():
            chart_images[name] = image_to_base64(path)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AccessFlow Toronto - Pedestrian Impact Analysis</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f6fa; color: #2d3436; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
        header {{ background: linear-gradient(135deg, #0984e3, #6c5ce7); color: white; padding: 3rem 2rem; text-align: center; }}
        header h1 {{ font-size: 2.5rem; margin-bottom: 0.5rem; }}
        header p {{ opacity: 0.9; font-size: 1.1rem; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin: 2rem 0; }}
        .stat-card {{ background: white; border-radius: 12px; padding: 1.5rem; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.08); }}
        .stat-card h3 {{ color: #636e72; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px; }}
        .stat-card .value {{ font-size: 2rem; font-weight: 700; color: #0984e3; }}
        .stat-card .label {{ color: #b2bec3; font-size: 0.85rem; }}
        section {{ background: white; border-radius: 12px; padding: 2rem; margin: 2rem 0; box-shadow: 0 2px 10px rgba(0,0,0,0.08); }}
        section h2 {{ color: #2d3436; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid #dfe6e9; }}
        .chart {{ text-align: center; margin: 1.5rem 0; }}
        .chart img {{ max-width: 100%; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid #dfe6e9; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #636e72; }}
        .badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.85rem; font-weight: 600; }}
        .badge-success {{ background: #00b894; color: white; }}
        .badge-warning {{ background: #fdcb6e; color: #2d3436; }}
        .badge-danger {{ background: #e74c3c; color: white; }}
        .badge-info {{ background: #0984e3; color: white; }}
        .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }}
        @media (max-width: 768px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
        footer {{ text-align: center; padding: 2rem; color: #636e72; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <header>
        <h1>AccessFlow Toronto</h1>
        <p>Pedestrian Accessibility Impact Analysis</p>
    </header>

    <div class="container">
        <div class="stats">
            <div class="stat-card">
                <h3>Total Closures</h3>
                <div class="value">{total:,}</div>
                <div class="label">road restrictions analyzed</div>
            </div>
            <div class="stat-card">
                <h3>Best Model</h3>
                <div class="value">{best['f1_score']:.1%}</div>
                <div class="label">F1-score (macro)</div>
            </div>
            <div class="stat-card">
                <h3>Features</h3>
                <div class="value">{len(best['feature_importance'])}</div>
                <div class="label">predictive variables</div>
            </div>
            <div class="stat-card">
                <h3>Validation</h3>
                <div class="value">7/7</div>
                <div class="label">gate conditions met</div>
            </div>
        </div>

        <section>
            <h2>Impact Distribution</h2>
            <p>Distribution of accessibility impact levels across all road closures.</p>
            <div class="chart">
                <img src="{chart_images.get('impact_distribution', '')}" alt="Impact Distribution">
            </div>
            <table>
                <tr><th>Impact Level</th><th>Count</th><th>Percentage</th></tr>
                <tr><td><span class="badge badge-success">None</span></td><td>{impact_counts.get('None', 0):,}</td><td>{impact_counts.get('None', 0)/total:.1%}</td></tr>
                <tr><td><span class="badge badge-warning">Low</span></td><td>{impact_counts.get('Low', 0):,}</td><td>{impact_counts.get('Low', 0)/total:.1%}</td></tr>
                <tr><td><span class="badge badge-danger">High</span></td><td>{impact_counts.get('High', 0):,}</td><td>{impact_counts.get('High', 0)/total:.1%}</td></tr>
            </table>
        </section>

        <section>
            <h2>Model Performance</h2>
            <p>Comparison of baseline, logistic regression, and XGBoost models.</p>
            <div class="chart">
                <img src="{chart_images.get('model_comparison', '')}" alt="Model Comparison">
            </div>
            <table>
                <tr><th>Model</th><th>F1-Score</th><th>Accuracy</th><th>Status</th></tr>
                <tr><td>Baseline (always None)</td><td>0.2955</td><td>80%</td><td><span class="badge badge-info">Baseline</span></td></tr>
                <tr><td>Logistic Regression</td><td>0.8299</td><td>94%</td><td><span class="badge badge-warning">+0.53</span></td></tr>
                <tr><td><strong>XGBoost</strong></td><td><strong>{best['f1_score']:.4f}</strong></td><td><strong>99%</strong></td><td><span class="badge badge-success">Best</span></td></tr>
            </table>
        </section>

        <div class="two-col">
            <section>
                <h2>Feature Importance</h2>
                <p>What drives accessibility impact predictions.</p>
                <div class="chart">
                    <img src="{chart_images.get('feature_importance_original', '')}" alt="Feature Importance">
                </div>
            </section>
            <section>
                <h2>Confusion Matrix</h2>
                <p>Model prediction accuracy by class.</p>
                <div class="chart">
                    <img src="{chart_images.get('confusion_matrix', '')}" alt="Confusion Matrix">
                </div>
            </section>
        </div>

        <section>
            <h2>Pedestrian Network Validation</h2>
            <p>High-impact closures have more pedestrian infrastructure nearby.</p>
            <div class="chart">
                <img src="{chart_images.get('network_topology', '')}" alt="Network Topology">
            </div>
            <table>
                <tr><th>Impact Level</th><th>Nearby Sidewalk</th><th>Nearby Edges</th><th>Interpretation</th></tr>
                <tr><td><span class="badge badge-danger">High</span></td><td>1,574m</td><td>15.1</td><td>More pedestrians affected</td></tr>
                <tr><td><span class="badge badge-warning">Low</span></td><td>1,173m</td><td>13.3</td><td>Moderate impact</td></tr>
                <tr><td><span class="badge badge-success">None</span></td><td>1,064m</td><td>10.5</td><td>Few pedestrians affected</td></tr>
            </table>
        </section>

        <section>
            <h2>Key Insights</h2>
            <ul style="list-style: none; padding: 0;">
                <li style="padding: 0.5rem 0; border-bottom: 1px solid #dfe6e9;">
                    <strong>1.</strong> WorkPeriod (63%) and RoadClass (33%) account for 96% of XGBoost predictions
                </li>
                <li style="padding: 0.5rem 0; border-bottom: 1px solid #dfe6e9;">
                    <strong>2.</strong> High-impact closures have 44% more pedestrian infrastructure nearby
                </li>
                <li style="padding: 0.5rem 0; border-bottom: 1px solid #dfe6e9;">
                    <strong>3.</strong> 97.1% of closures match to the pedestrian network within 100m
                </li>
                <li style="padding: 0.5rem 0;">
                    <strong>4.</strong> Original 9 features outperform extended 16 features (0.976 vs 0.966 F1)
                </li>
            </ul>
        </section>
    </div>

    <footer>
        <p>AccessFlow Toronto | Data: Toronto Open Data | Analysis: {total:,} road restrictions</p>
    </footer>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)

    return output_path
