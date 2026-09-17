# AccessFlow Toronto — Pedestrian Restriction Analysis

Data analysis and visualization of Toronto road-restriction data and its impact on pedestrian network accessibility.

## What's in this repo

- **Notebook:** `notebooks/accessflow_analysis.ipynb` — Exploratory data analysis, feature engineering, and visualization of the 1,834 road restrictions from Toronto Open Data
- **Fixtures:** `fixtures/phase25/` — Committed CSVs (75 / 213 / 150 rows) from the pipeline project
- **Spatial artifact:** `fixtures/phase22-spatial.json` — Deterministic spatial data (SHA-256 `55ee52d3…`)

## Visualizations produced

1. Cohort overview (evaluation status + impact severity distributions)
2. Numeric feature histograms and box plots
3. Correlation heatmap
4. Edge replacement metric distributions + scatter
5. Restriction impact distributions
6. Spatial artifact structure analysis
7. Folium map of Toronto restrictions
8. Categorical feature distributions

## Getting started

```bash
pip install -r requirements.txt
jupyter notebook notebooks/accessflow_analysis.ipynb
```

## Data provenance

| Dataset | Source | Rows | Hash |
|---|---|---|---|
| `phase14-evaluation-cohort.csv` | Toronto Open Data road-restrictions feed | 75 | Verified fixture |
| `phase15-edge-replacement.csv` | Phase 15 replacement analysis | 213 | Verified fixture |
| `phase15-restriction-impact.csv` | Phase 15 replacement analysis | 150 | Verified fixture |
| `phase22-spatial.json` | Deterministic spatial artifact | 75 features | `55ee52d3…` |

## License

MIT
