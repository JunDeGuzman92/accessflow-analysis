"""CLI for training and managing ML models."""

import xml.etree.ElementTree as ET
from pathlib import Path

import click
import pandas as pd


@click.group()
def cli() -> None:
    """AccessFlow ML model management."""
    pass


@cli.command()
@click.option("--xml-path", type=click.Path(exists=True), required=True, help="Path to road-restrictions XML")
@click.option("--model-dir", type=click.Path(), default="data/models/impact", help="Directory to save model")
def train(xml_path: str, model_dir: str) -> None:
    """Train the impact prediction model."""
    from .models import ImpactPredictor

    # Parse XML
    click.echo(f"Parsing XML: {xml_path}")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    records = []
    for closure in root.findall(".//Closure"):
        record = {}
        for field in closure:
            record[field.tag] = field.text
        records.append(record)
    df = pd.DataFrame(records)
    click.echo(f"Loaded {len(df)} closures")

    # Compute Duration_days
    df["StartTime_num"] = pd.to_numeric(df["StartTime"], errors="coerce")
    df["EndTime_num"] = pd.to_numeric(df["EndTime"], errors="coerce")
    df["Duration_days"] = (df["EndTime_num"] - df["StartTime_num"]) / (1000 * 60 * 60 * 24)

    # Drop missing target
    df = df.dropna(subset=["CurrImpact"])

    # Train
    click.echo("Training model...")
    predictor = ImpactPredictor()
    metadata = predictor.fit(df)

    # Save
    model_path = Path(model_dir)
    predictor.save(model_path)
    click.echo(f"Model saved to {model_path}")
    click.echo(f"  Version: {metadata.version}")
    click.echo(f"  Features: {len(metadata.features)}")
    click.echo(f"  Training samples: {metadata.training_samples}")
    click.echo(f"  F1-score: {metadata.f1_score:.4f}")


@cli.command()
@click.option("--model-dir", type=click.Path(exists=True), default="data/models/impact", help="Model directory")
def info(model_dir: str) -> None:
    """Show model information."""
    from .models import ImpactPredictor

    predictor = ImpactPredictor.load(Path(model_dir))
    click.echo(f"Model fitted: {predictor.is_fitted}")
    click.echo(f"Features: {predictor.feature_cols}")
    click.echo(f"Numeric features: {predictor.numeric_cols}")
    click.echo(f"Categorical features: {predictor.categorical_cols}")


if __name__ == "__main__":
    cli()
