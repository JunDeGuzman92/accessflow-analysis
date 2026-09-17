"""Impact prediction model for pedestrian accessibility."""

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import classification_report, f1_score
from xgboost import XGBClassifier


def load_restrictions(xml_path: Path) -> pd.DataFrame:
    """Load road restrictions from XML feed."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    records = []
    for closure in root.findall(".//Closure"):
        record = {}
        for field in closure:
            record[field.tag] = field.text
        records.append(record)
    return pd.DataFrame(records)


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare feature columns for modeling."""
    df = df.copy()

    # Target
    df["CurrImpact"] = df["CurrImpact"].replace("Medium", "Low")

    # Numeric features
    df["StartTime_num"] = pd.to_numeric(df["StartTime"], errors="coerce")
    df["EndTime_num"] = pd.to_numeric(df["EndTime"], errors="coerce")
    df["Duration_days"] = (df["EndTime_num"] - df["StartTime_num"]) / (1000 * 60 * 60 * 24)
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

    # Temporal features
    df["CreatedTime_num"] = pd.to_numeric(df["CreatedTime"], errors="coerce")
    df["CreatedDate"] = pd.to_datetime(df["CreatedTime_num"], unit="ms", errors="coerce")
    df["CreatedYear"] = df["CreatedDate"].dt.year
    df["DayOfWeek"] = df["CreatedDate"].dt.dayofweek
    df["Month"] = df["CreatedDate"].dt.month
    df["IsWeekend"] = (df["DayOfWeek"] >= 5).astype(int)

    # Spatial features
    downtown_lat, downtown_lon = 43.6532, -79.3832
    df["DistanceToDowntown_km"] = np.sqrt(
        ((df["Latitude"] - downtown_lat) * 111) ** 2 +
        ((df["Longitude"] - downtown_lon) * 111 * np.cos(np.radians(df["Latitude"]))) ** 2
    )

    return df


def train_evaluate(df: pd.DataFrame, feature_cols: list[str]) -> dict:
    """Train XGBoost model and return evaluation results."""
    # Drop rows with NaN
    valid = df[feature_cols + ["CurrImpact"]].dropna().index
    df_train = df.loc[valid].copy()

    # Encode categoricals
    label_encoders = {}
    for col in feature_cols:
        if df_train[col].dtype in ("object", "string"):
            le = LabelEncoder()
            df_train[col] = le.fit_transform(df_train[col].astype(str))
            label_encoders[col] = le

    # Encode target
    target_le = LabelEncoder()
    df_train["CurrImpact"] = target_le.fit_transform(df_train["CurrImpact"])

    # Split (temporal)
    train_mask = df_train["CreatedYear"] < 2026
    test_mask = df_train["CreatedYear"] >= 2026

    X_train = df_train.loc[train_mask, feature_cols].values.astype(float)
    y_train = df_train.loc[train_mask, "CurrImpact"].values
    X_test = df_train.loc[test_mask, feature_cols].values.astype(float)
    y_test = df_train.loc[test_mask, "CurrImpact"].values

    # Train
    model = XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        random_state=42, subsample=0.8, eval_metric="mlogloss",
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # Decode
    y_test_labels = target_le.inverse_transform(y_test.astype(int))
    y_pred_labels = target_le.inverse_transform(y_pred.astype(int))

    # Metrics
    f1 = f1_score(y_test_labels, y_pred_labels, average="macro", zero_division=0)
    report = classification_report(y_test_labels, y_pred_labels, output_dict=True)

    return {
        "model": model,
        "target_encoder": target_le,
        "label_encoders": label_encoders,
        "f1_score": f1,
        "report": report,
        "feature_importance": dict(zip(feature_cols, model.feature_importances_)),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "y_test": y_test_labels,
        "y_pred": y_pred_labels,
    }


# Feature sets
ORIGINAL_FEATURES = [
    "Type", "RoadClass", "DirectionsAffected", "WorkPeriod", "District",
    "Latitude", "Longitude", "Duration_days", "SpecialEvent"
]

EXTENDED_FEATURES = ORIGINAL_FEATURES + [
    "DayOfWeek", "Month", "IsWeekend", "DistanceToDowntown_km"
]
