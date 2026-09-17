import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import classification_report, f1_score, confusion_matrix
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
df = df.dropna(subset=['CurrImpact'])

# 4. Create year column for split
df['CreatedTime_num'] = pd.to_numeric(df['CreatedTime'], errors='coerce')
df['CreatedYear'] = pd.to_datetime(df['CreatedTime_num'], unit='ms', errors='coerce').dt.year

# 5. Features
feature_cols = ['Type', 'RoadClass', 'DirectionsAffected', 'WorkPeriod', 'District',
                'Latitude', 'Longitude', 'Duration_days', 'SpecialEvent']

# Encode all categoricals
for col in feature_cols:
    if df[col].dtype == 'object' or df[col].dtype == 'string' or df[col].dtype.name == 'str':
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))

# 6. Split
train_mask = df['CreatedYear'] < 2026
test_mask = df['CreatedYear'] >= 2026
print(f'\nTrain (before 2026): {train_mask.sum()}, Test (2026+): {test_mask.sum()}')

# Drop NaN
valid = df[feature_cols + ['CurrImpact']].dropna().index
train_mask = train_mask & df.index.isin(valid)
test_mask = test_mask & df.index.isin(valid)

X_train = df.loc[train_mask, feature_cols].values.astype(float)
y_train = df.loc[train_mask, 'CurrImpact'].values
X_test = df.loc[test_mask, feature_cols].values.astype(float)
y_test = df.loc[test_mask, 'CurrImpact'].values
print(f'Final: Train {len(X_train)}, Test {len(X_test)}')

# 7. Scale
scaler = StandardScaler()
numeric_idx = [feature_cols.index(c) for c in ['Latitude', 'Longitude', 'Duration_days']]
X_train_scaled = X_train.copy()
X_test_scaled = X_test.copy()
X_train_scaled[:, numeric_idx] = scaler.fit_transform(X_train[:, numeric_idx])
X_test_scaled[:, numeric_idx] = scaler.transform(X_test[:, numeric_idx])

# 8. Baseline
baseline_pred = ['None'] * len(y_test)
baseline_f1 = f1_score(y_test, baseline_pred, average='macro', zero_division=0)
print(f'\n=== BASELINE (always predict None) ===')
print(f'F1-score (macro): {baseline_f1:.4f}')

# 9. Logistic Regression
lr_model = LogisticRegression(max_iter=500, random_state=42, class_weight='balanced')
lr_model.fit(X_train_scaled, y_train)
lr_pred = lr_model.predict(X_test_scaled)
lr_f1 = f1_score(y_test, lr_pred, average='macro', zero_division=0)
print(f'\n=== LOGISTIC REGRESSION ===')
print(f'F1-score (macro): {lr_f1:.4f}')
print(classification_report(y_test, lr_pred, zero_division=0))

# 10. XGBoost
print(f'\n=== XGBOOST ===')
xgb_model = GradientBoostingClassifier(
    n_estimators=100,
    max_depth=4,
    learning_rate=0.1,
    random_state=42,
    subsample=0.8
)
xgb_model.fit(X_train, y_train)  # XGBoost doesn't need scaling
xgb_pred = xgb_model.predict(X_test)
xgb_f1 = f1_score(y_test, xgb_pred, average='macro', zero_division=0)
print(f'F1-score (macro): {xgb_f1:.4f}')
print(classification_report(y_test, xgb_pred, zero_division=0))

# 11. Feature importance comparison
print('\n=== FEATURE IMPORTANCE ===')

lr_importance = pd.Series(np.abs(lr_model.coef_).mean(axis=0), index=feature_cols)
lr_importance = lr_importance.sort_values(ascending=False)
print('Logistic Regression:')
for feat, imp in lr_importance.items():
    print(f'  {feat}: {imp:.4f}')

xgb_importance = pd.Series(xgb_model.feature_importances_, index=feature_cols)
xgb_importance = xgb_importance.sort_values(ascending=False)
print('\nXGBoost:')
for feat, imp in xgb_importance.items():
    print(f'  {feat}: {imp:.4f}')

# 12. Confusion matrices
print('\n=== CONFUSION MATRICES ===')
print('Logistic Regression:')
print(pd.DataFrame(
    confusion_matrix(y_test, lr_pred, labels=['None', 'Low', 'High']),
    index=['True None', 'True Low', 'True High'],
    columns=['Pred None', 'Pred Low', 'Pred High']
))
print('\nXGBoost:')
print(pd.DataFrame(
    confusion_matrix(y_test, xgb_pred, labels=['None', 'Low', 'High']),
    index=['True None', 'True Low', 'True High'],
    columns=['Pred None', 'Pred Low', 'Pred High']
))

# 13. Comparison
print(f'\n=== FINAL COMPARISON ===')
print(f'Baseline F1:           {baseline_f1:.4f}')
print(f'Logistic Regression F1: {lr_f1:.4f}')
print(f'XGBoost F1:             {xgb_f1:.4f}')
print(f'\nLR improvement:  {lr_f1 - baseline_f1:+.4f}')
print(f'XGB improvement: {xgb_f1 - baseline_f1:+.4f}')
print(f'XGB vs LR:       {xgb_f1 - lr_f1:+.4f}')

best = 'XGBoost' if xgb_f1 > lr_f1 else 'Logistic Regression'
print(f'\nBEST MODEL: {best} (F1={max(lr_f1, xgb_f1):.4f})')
