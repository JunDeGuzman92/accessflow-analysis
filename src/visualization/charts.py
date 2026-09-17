"""Generate static charts for the analysis."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


OUTPUT_DIR = Path("output/charts")


def setup_style():
    """Set up matplotlib style."""
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "figure.figsize": (10, 6),
        "font.size": 12,
        "axes.titlesize": 14,
        "axes.labelsize": 12,
    })


def chart_impact_distribution(df: pd.DataFrame) -> Path:
    """Chart showing CurrImpact distribution."""
    setup_style()
    fig, ax = plt.subplots()

    colors = {"None": "#2ecc71", "Low": "#f39c12", "High": "#e74c3c"}
    counts = df["CurrImpact"].value_counts()
    counts.plot(kind="bar", ax=ax, color=[colors.get(x, "#95a5a6") for x in counts.index])

    ax.set_title("Accessibility Impact Distribution")
    ax.set_xlabel("Impact Level")
    ax.set_ylabel("Number of Closures")
    ax.tick_params(axis="x", rotation=0)

    for i, v in enumerate(counts.values):
        ax.text(i, v + 10, str(v), ha="center", fontweight="bold")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "impact_distribution.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_feature_importance(importance: dict, title: str = "Feature Importance") -> Path:
    """Chart showing feature importance."""
    setup_style()
    fig, ax = plt.subplots()

    sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
    features, values = zip(*sorted_imp)

    colors = ["#3498db" if v > 0.1 else "#95a5a6" for v in values]
    ax.barh(range(len(features)), values, color=colors)
    ax.set_yticks(range(len(features)))
    ax.set_yticklabels(features)
    ax.set_xlabel("Importance")
    ax.set_title(title)
    ax.invert_yaxis()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "feature_importance.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_model_comparison(results: list[dict]) -> Path:
    """Chart comparing model performances."""
    setup_style()
    fig, ax = plt.subplots()

    names = [r["name"] for r in results]
    f1s = [r["f1_score"] for r in results]

    colors = ["#95a5a6", "#3498db", "#2ecc71"]
    bars = ax.bar(names, f1s, color=colors[:len(names)])

    ax.set_ylabel("F1-Score (Macro)")
    ax.set_title("Model Performance Comparison")
    ax.set_ylim(0, 1.05)

    for bar, f1 in zip(bars, f1s):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                f"{f1:.4f}", ha="center", fontweight="bold")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "model_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_confusion_matrix(y_test, y_pred, labels: list[str]) -> Path:
    """Chart showing confusion matrix."""
    setup_style()
    fig, ax = plt.subplots()

    from sklearn.metrics import confusion_matrix
    cm = confusion_matrix(y_test, y_pred, labels=labels)

    im = ax.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    ax.set_title("Confusion Matrix")
    plt.colorbar(im, ax=ax)

    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")

    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "confusion_matrix.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_network_topology() -> Path:
    """Chart showing network topology validation."""
    setup_style()
    fig, ax = plt.subplots()

    categories = ["High", "Low", "None"]
    sidewalk_lengths = [1574, 1173, 1064]
    colors = ["#e74c3c", "#f39c12", "#2ecc71"]

    bars = ax.bar(categories, sidewalk_lengths, color=colors)
    ax.set_ylabel("Avg Nearby Sidewalk (m)")
    ax.set_title("Pedestrian Infrastructure by Impact Level")

    for bar, val in zip(bars, sidewalk_lengths):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 20,
                f"{val}m", ha="center", fontweight="bold")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "network_topology.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_all_charts(df: pd.DataFrame, results: list[dict]) -> list[Path]:
    """Generate all charts and return paths."""
    paths = []

    paths.append(chart_impact_distribution(df))

    for r in results:
        paths.append(chart_feature_importance(r["feature_importance"], f"Feature Importance: {r['name']}"))

    paths.append(chart_model_comparison(results))

    if results:
        best = max(results, key=lambda x: x["f1_score"])
        labels = list(set(best["y_test"]) | set(best["y_pred"]))
        paths.append(chart_confusion_matrix(best["y_test"], best["y_pred"], sorted(labels)))

    paths.append(chart_network_topology())

    return paths
