import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import classification_report, f1_score
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

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
print(f'Parsed {len(df)} closures')

# 2. Clean target
df['CurrImpact'] = df['CurrImpact'].replace('Medium', 'Low')
print(f'Target: {df["CurrImpact"].value_counts().to_dict()}')

# 3. Numeric features
df['StartTime_num'] = pd.to_numeric(df['StartTime'], errors='coerce')
df['EndTime_num'] = pd.to_numeric(df['EndTime'], errors='coerce')
df['Duration_days'] = (df['EndTime_num'] - df['StartTime_num']) / (1000*60*60*24)
df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')

# 4. Drop missing target
df = df.dropna(subset=['CurrImpact'])

# 5. Create year column for split
df['CreatedTime_num'] = pd.to_numeric(df['CreatedTime'], errors='coerce')
df['CreatedYear'] = pd.to_datetime(df['CreatedTime_num'], unit='ms', errors='coerce').dt.year
year_dist = df['CreatedYear'].value_counts().sort_index()
print(f'\nYear distribution:')
for y, c in year_dist.items():
    print(f'  {int(y)}: {c}')

# 6. Use ALL data for encoding, then split
feature_cols = ['Type', 'RoadClass', 'DirectionsAffected', 'WorkPeriod', 'District',
                'Latitude', 'Longitude', 'Duration_days', 'SpecialEvent']

# Encode all categoricals
for col in feature_cols:
    if df[col].dtype == 'object' or df[col].dtype == 'string' or df[col].dtype.name == 'str':
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))

# Verify all features are numeric
print(f'\nFeature dtypes after encoding:')
for col in feature_cols:
    print(f'  {col}: {df[col].dtype}')

# 7. Temporal split
train_mask = df['CreatedYear'] < 2026
test_mask = df['CreatedYear'] >= 2026

print(f'\nTrain (before 2026): {train_mask.sum()}, Test (2026+): {test_mask.sum()}')

if train_mask.sum() < 10 or test_mask.sum() < 10:
    print('Too few samples for temporal split, using random 80/20')
    np.random.seed(42)
    idx = np.random.permutation(len(df))
    n_train = int(0.8 * len(df))
    train_idx = idx[:n_train]
    test_idx = idx[n_train:]
    train_mask = df.index.isin(df.index[train_idx])
    test_mask = df.index.isin(df.index[test_idx])

# Drop rows with NaN in features
valid = df[feature_cols + ['CurrImpact']].dropna().index
train_mask = train_mask & df.index.isin(valid)
test_mask = test_mask & df.index.isin(valid)

X_train = df.loc[train_mask, feature_cols].values.astype(float)
y_train = df.loc[train_mask, 'CurrImpact'].values
X_test = df.loc[test_mask, feature_cols].values.astype(float)
y_test = df.loc[test_mask, 'CurrImpact'].values
print(f'Final: Train {len(X_train)}, Test {len(X_test)}')

# 8. Scale
scaler = StandardScaler()
numeric_idx = [feature_cols.index(c) for c in ['Latitude', 'Longitude', 'Duration_days']]
X_train[:, numeric_idx] = scaler.fit_transform(X_train[:, numeric_idx])
X_test[:, numeric_idx] = scaler.transform(X_test[:, numeric_idx])

# 9. Baseline
baseline_pred = ['None'] * len(y_test)
baseline_f1 = f1_score(y_test, baseline_pred, average='macro', zero_division=0)
print(f'\n=== BASELINE (always predict None) ===')
print(f'F1-score (macro): {baseline_f1:.4f}')
print(classification_report(y_test, baseline_pred, zero_division=0))

# 10. Logistic Regression
model = LogisticRegression(max_iter=500, random_state=42, class_weight='balanced')
model.fit(X_train, y_train)
y_pred = model.predict(X_test)

lr_f1 = f1_score(y_test, y_pred, average='macro', zero_division=0)
print(f'=== LOGISTIC REGRESSION ===')
print(f'F1-score (macro): {lr_f1:.4f}')
print(classification_report(y_test, y_pred, zero_division=0))

# 11. Feature importance
print('=== FEATURE IMPORTANCE ===')
importance = pd.Series(np.abs(model.coef_).mean(axis=0), index=feature_cols)
importance = importance.sort_values(ascending=False)
for feat, imp in importance.items():
    print(f'  {feat}: {imp:.4f}')

# 12. Comparison
print(f'\n=== COMPARISON ===')
print(f'Baseline F1:           {baseline_f1:.4f}')
print(f'Logistic Regression F1: {lr_f1:.4f}')
print(f'Improvement:           {lr_f1 - baseline_f1:+.4f}')
if lr_f1 > baseline_f1:
    print('RESULT: Logistic regression beats baseline.')
else:
    print('RESULT: Logistic regression does NOT beat baseline.')
