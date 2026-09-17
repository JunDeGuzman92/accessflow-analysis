"""Extended analysis with additional features."""

import xml.etree.ElementTree as ET
import json
import csv
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import classification_report, f1_score
from xgboost import XGBClassifier
from scipy.spatial import cKDTree
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

print('=== Extended Feature Analysis ===')
print()

# 1. Parse XML
xml_path = Path('fixtures/road-restrictions--resource-3afea38a-baad-4f39-b22f-d608875e1746.xml')
tree = ET.parse(xml_path)
root = tree.getroot()
records = []
for closure in root.findall('.//Closure'):
    record = {}
    for field in closure:
        record[field.tag] = field.text
    records.append(record)
df = pd.DataFrame(records)
print(f'1. Parsed {len(df)} closures')

# 2. Clean target
df['CurrImpact'] = df['CurrImpact'].replace('Medium', 'Low')
print(f'   Target: {df["CurrImpact"].value_counts().to_dict()}')

# 3. Numeric features
df['StartTime_num'] = pd.to_numeric(df['StartTime'], errors='coerce')
df['EndTime_num'] = pd.to_numeric(df['EndTime'], errors='coerce')
df['Duration_days'] = (df['EndTime_num'] - df['StartTime_num']) / (1000*60*60*24)
df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
df = df.dropna(subset=['CurrImpact'])

# 4. Create year column for split
df['CreatedTime_num'] = pd.to_numeric(df['CreatedTime'], errors='coerce')
df['CreatedYear'] = pd.to_datetime(df['CreatedTime_num'], unit='ms', errors='coerce').dt.year

# 5. Add temporal features
print('2. Adding temporal features')
df['CreatedDate'] = pd.to_datetime(df['CreatedTime_num'], unit='ms', errors='coerce')
df['DayOfWeek'] = df['CreatedDate'].dt.dayofweek  # 0=Monday, 6=Sunday
df['Month'] = df['CreatedDate'].dt.month
df['Season'] = df['Month'].map({
    12: 'Winter', 1: 'Winter', 2: 'Winter',
    3: 'Spring', 4: 'Spring', 5: 'Spring',
    6: 'Summer', 7: 'Summer', 8: 'Summer',
    9: 'Fall', 10: 'Fall', 11: 'Fall'
})
df['IsWeekend'] = (df['DayOfWeek'] >= 5).astype(int)
print(f'   Day of week: {df["DayOfWeek"].value_counts().sort_index().to_dict()}')
print(f'   Season: {df["Season"].value_counts().to_dict()}')

# 6. Add spatial features
print()
print('3. Adding spatial features')
# Distance to downtown Toronto (City Hall: 43.6532, -79.3832)
downtown_lat, downtown_lon = 43.6532, -79.3832
df['DistanceToDowntown_km'] = np.sqrt(
    ((df['Latitude'] - downtown_lat) * 111) ** 2 +
    ((df['Longitude'] - downtown_lon) * 111 * np.cos(np.radians(df['Latitude']))) ** 2
)
print(f'   Distance to downtown: mean={df["DistanceToDowntown_km"].mean():.2f}km, std={df["DistanceToDowntown_km"].std():.2f}km')

# 7. Add pedestrian network features
print()
print('4. Adding pedestrian network features')
csv_path = Path('fixtures/pedestrian-network-data-4326.csv')
if csv_path.exists():
    pednet = pd.read_csv(csv_path)

    # Extract coordinates
    pednet_coords = []
    for idx, row in pednet.iterrows():
        try:
            geom = json.loads(row['geometry'])
            coords = geom['coordinates'][0]
            for coord in coords:
                pednet_coords.append([coord[0], coord[1], idx])
        except:
            pass

    pednet_coords = np.array(pednet_coords)
    tree_pednet = cKDTree(pednet_coords[:, :2])

    # For each closure, find nearby pedestrian network features
    df['NearbyPednetEdges'] = 0
    df['NearbySidewalkLength_m'] = 0.0
    df['NearbyCrosswalks'] = 0

    threshold = 0.001  # ~100m
    for idx, row in df.iterrows():
        if pd.isna(row['Latitude']) or pd.isna(row['Longitude']):
            continue

        closure_point = [row['Longitude'], row['Latitude']]
        nearby_dists, nearby_idx = tree_pednet.query(closure_point, k=50)
        nearby_mask = nearby_dists < threshold
        nearby_edge_indices = np.unique(pednet_coords[nearby_idx[nearby_mask], 2].astype(int))
        nearby_edges = pednet.loc[nearby_edge_indices]

        df.at[idx, 'NearbyPednetEdges'] = len(nearby_edges)
        df.at[idx, 'NearbySidewalkLength_m'] = nearby_edges['LENGTH'].sum()
        df.at[idx, 'NearbyCrosswalks'] = (nearby_edges['CROSSWALK'] == 1.0).sum()

    print(f'   Nearby edges: mean={df["NearbyPednetEdges"].mean():.1f}')
    print(f'   Nearby sidewalk: mean={df["NearbySidewalkLength_m"].mean():.1f}m')
    print(f'   Nearby crosswalks: mean={df["NearbyCrosswalks"].mean():.1f}')

# 8. Extended features
print()
print('5. Extended feature set')
original_features = ['Type', 'RoadClass', 'DirectionsAffected', 'WorkPeriod', 'District',
                     'Latitude', 'Longitude', 'Duration_days', 'SpecialEvent']
extended_features = original_features + ['DayOfWeek', 'Month', 'IsWeekend', 'DistanceToDowntown_km',
                                         'NearbyPednetEdges', 'NearbySidewalkLength_m', 'NearbyCrosswalks']
print(f'   Original features: {len(original_features)}')
print(f'   Extended features: {len(extended_features)}')

# 9. Train models
print()
print('6. Training models')

def train_model(df, feature_cols, name):
    """Train XGBoost model and return results."""
    # Drop rows with NaN in features
    valid = df[feature_cols + ['CurrImpact']].dropna().index
    df_train = df.loc[valid].copy()

    # Encode categoricals
    label_encoders = {}
    for col in feature_cols:
        if df_train[col].dtype in ('object', 'string'):
            le = LabelEncoder()
            df_train[col] = le.fit_transform(df_train[col].astype(str))
            label_encoders[col] = le

    # Encode target
    target_le = LabelEncoder()
    df_train['CurrImpact'] = target_le.fit_transform(df_train['CurrImpact'])
    label_encoders['__target__'] = target_le

    # Split
    train_mask = df_train['CreatedYear'] < 2026
    test_mask = df_train['CreatedYear'] >= 2026

    X_train = df_train.loc[train_mask, feature_cols].values.astype(float)
    y_train = df_train.loc[train_mask, 'CurrImpact'].values
    X_test = df_train.loc[test_mask, feature_cols].values.astype(float)
    y_test = df_train.loc[test_mask, 'CurrImpact'].values

    # Train
    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
        subsample=0.8,
        eval_metric='mlogloss',
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # Decode predictions
    y_test_labels = target_le.inverse_transform(y_test.astype(int))
    y_pred_labels = target_le.inverse_transform(y_pred.astype(int))

    f1 = f1_score(y_test_labels, y_pred_labels, average='macro', zero_division=0)

    return {
        'name': name,
        'f1': f1,
        'feature_importance': dict(zip(feature_cols, model.feature_importances_)),
        'n_features': len(feature_cols),
        'n_train': len(X_train),
        'n_test': len(X_test),
    }

# Train original model
result_original = train_model(df, original_features, 'Original (9 features)')

# Train extended model
result_extended = train_model(df, extended_features, 'Extended (16 features)')

# 10. Compare results
print()
print('7. Model Comparison')
print(f'{"Model":<30} {"Features":<10} {"F1-score":<10} {"Train":<8} {"Test":<8}')
print('-' * 66)
print(f'{result_original["name"]:<30} {result_original["n_features"]:<10} {result_original["f1"]:<10.4f} {result_original["n_train"]:<8} {result_original["n_test"]:<8}')
print(f'{result_extended["name"]:<30} {result_extended["n_features"]:<10} {result_extended["f1"]:<10.4f} {result_extended["n_train"]:<8} {result_extended["n_test"]:<8}')

improvement = result_extended['f1'] - result_original['f1']
print(f'\nImprovement: {improvement:+.4f}')

# 11. Feature importance comparison
print()
print('8. Feature Importance (Extended Model)')
sorted_features = sorted(result_extended['feature_importance'].items(), key=lambda x: x[1], reverse=True)
for feat, imp in sorted_features:
    marker = ' (NEW)' if feat not in original_features else ''
    print(f'   {feat}: {imp:.4f}{marker}')

print()
print('=== Extended Analysis Complete ===')
