# AccessFlow Toronto — Pedestrian Restriction Analysis

Machine learning analysis of Toronto road-restriction data and its impact on pedestrian network accessibility.

## What's in this repo

- **Notebook:** `notebooks/accessflow_analysis.ipynb` — Exploratory data analysis, visualizations, and ML models
- **Fixtures:** `fixtures/road-restrictions--resource-3afea38a-*.xml` — Toronto Open Data feed (1,834 closures)
- **Pedestrian Network:** `fixtures/pedestrian-network-data-4326.csv` — Toronto Pedestrian Network (87,105 edges)
- **Models:** `run_baseline.py`, `run_gradient_boosting.py` — Reproducible ML scripts
- **Validation:** `validate_topology.py` — Network topology analysis

## Key Findings

### Data

- **1,834 road closures** from Toronto Open Data (road-restrictions feed)
- **Target:** `CurrImpact` (None: 1,440, Low: 237, High: 157)
- **Features:** Type, RoadClass, DirectionsAffected, WorkPeriod, District, Latitude, Longitude, Duration_days, SpecialEvent

### Models

| Model | F1-score (macro) | Accuracy |
|---|---|---|
| Baseline (always None) | 0.2955 | 80% |
| Logistic Regression | 0.8299 | 94% |
| **XGBoost** | **0.9761** | **99%** |

### Feature Importance (XGBoost)

1. **WorkPeriod** (63%) — Schedule type is the strongest predictor
2. **RoadClass** (33%) — Road classification is the second strongest

### Network Topology Validation

High-impact closures have **44% more pedestrian infrastructure** nearby:

| CurrImpact | Nearby Sidewalk Length |
|---|---|
| High | 1,574m |
| Low | 1,173m |
| None | 1,064m |

## ML Gate Status

All 7 conditions from ADR-003 are met:

| # | Condition | Status |
|---|---|---|
| 1 | Prediction target documented | ✅ |
| 2 | Label source identified | ✅ |
| 3 | Leakage controls documented | ✅ |
| 4 | Validation strategy defined | ✅ |
| 5 | Baseline model achieved | ✅ |
| 6 | Model exceeds baseline | ✅ |
| 7 | External validation | ✅ |

## Getting started

```bash
pip install -r requirements.txt
jupyter notebook notebooks/accessflow_analysis.ipynb
```

## Visualizations

1. Restriction types distribution
2. Work periods distribution
3. Temporal patterns (month/year)
4. Road classes distribution
5. Geographic scatter plot
6. Contractor analysis
7. ML model comparison
8. Feature importance

## Data provenance

| Dataset | Source | Records | License |
|---|---|---|---|
| Road Restrictions | Toronto Open Data | 1,834 | Open Government Licence - Toronto |
| Pedestrian Network | City of Toronto DAV | 87,105 edges | Not specified |

## License

MIT
