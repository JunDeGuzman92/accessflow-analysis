# AccessFlow Toronto — Pedestrian Impact Analysis

Machine learning analysis of Toronto road-restriction data and its impact on pedestrian network accessibility.

## Quick Start

```bash
pip install -r requirements.txt
python generate_report.py
open output/dashboard.html
```

## Project Structure

```
accessflow-analysis/
├── src/
│   ├── models/
│   │   └── impact_predictor.py    # XGBoost model training and evaluation
│   └── visualization/
│       ├── charts.py              # Static chart generation
│       └── dashboard.py           # HTML dashboard generator
├── notebooks/
│   └── accessflow_analysis.ipynb  # Interactive analysis notebook
├── fixtures/
│   └── *.xml                      # Toronto Open Data feed
├── docs/
│   └── adr/
│       └── ADR-003-*.md           # ML prediction target documentation
├── output/
│   ├── dashboard.html             # Interactive dashboard
│   └── charts/                    # Static PNG charts
├── generate_report.py             # Report generation script
└── requirements.txt               # Python dependencies
```

## Key Results

| Model | F1-Score | Accuracy |
|---|---|---|
| Baseline (always None) | 0.2955 | 80% |
| Logistic Regression | 0.8299 | 94% |
| **XGBoost** | **0.9761** | **99%** |

### Feature Importance

1. **WorkPeriod** (63%) — Schedule type is the strongest predictor
2. **RoadClass** (33%) — Road classification is the second strongest

### Pedestrian Network Validation

High-impact closures have **44% more pedestrian infrastructure** nearby:

| Impact Level | Nearby Sidewalk |
|---|---|
| High | 1,574m |
| Low | 1,173m |
| None | 1,064m |

## Dashboard

Open `output/dashboard.html` in a browser to view:
- Impact distribution charts
- Model performance comparison
- Feature importance analysis
- Confusion matrix
- Pedestrian network validation

## Data Sources

| Dataset | Source | Records |
|---|---|---|
| Road Restrictions | Toronto Open Data | 1,834 |
| Pedestrian Network | City of Toronto DAV | 87,105 edges |

## License

MIT
