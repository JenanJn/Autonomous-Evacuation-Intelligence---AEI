"""
AEI — Training Script
======================
Trains and saves the baseline and Random Forest models.

DATA SOURCE: SYNTHETIC (200-row generated fixture).
No real Kaggle S4E5 CSV was available at the time of execution.
Metrics printed here are NOT evidence of real-world flood-prediction accuracy.

Run from AEI/:
    python scripts/run_training.py
"""
from __future__ import annotations

import logging
import pathlib
import sys
import time

_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests"))

logging.basicConfig(level=logging.WARNING)   # suppress INFO noise during training run

from data_pipeline.ingestion import load_csv
from fixtures.make_synthetic_fixture import save_fixtures, SIMULATED_DIR
from prediction.evaluate import compare_models
from prediction.model_loader import (
    load_model_bundle,
    metadata_from_training_result,
    save_model_bundle,
)
from prediction.train import run_training_pipeline

MODELS_DIR = _ROOT / "models"


def main() -> None:
    print("=" * 60)
    print("AEI — Milestone 2 Training Run")
    print("DATA SOURCE : SYNTHETIC (generated fixture)")
    print("WARNING     : Metrics below are NOT real-world accuracy.")
    print("=" * 60)

    # 1. Generate / refresh synthetic fixture
    save_fixtures()
    csv_path = SIMULATED_DIR / "synthetic_clean_200.csv"

    # 2. Load
    df = load_csv(csv_path, "SYNTHETIC", schema_name="kaggle_s4e5")
    print(f"\nLoaded  : {len(df)} rows x {len(df.columns)} cols")
    print(f"Source  : {df.attrs['_data_source']}")
    print(f"Schema  : {df.attrs['_schema_name']}")
    print(f"Target  : FloodProbability (synthetic, normalised sum + noise)")

    # 3. Train
    print("\nTraining ...")
    t0 = time.perf_counter()
    result = run_training_pipeline(
        df,
        target_col="FloodProbability",
        test_fraction=0.20,
        shuffle=True,
    )
    elapsed = time.perf_counter() - t0

    print(f"  Train rows : {result.train_rows}")
    print(f"  Test rows  : {result.test_rows}")
    print(f"  Wall clock : {elapsed:.3f} s")

    # 4. Metrics
    print()
    print("--- Baseline ---")
    print(result.baseline_metrics.summary())
    print()
    print("--- Random Forest ---")
    print(result.rf_metrics.summary())
    print()
    print(compare_models(result.baseline_metrics, result.rf_metrics))

    # 5. Save artefacts
    meta_baseline = metadata_from_training_result(result, "MeanBaseline", "0.1.0")
    meta_rf       = metadata_from_training_result(result, "RandomForest",  "0.1.0")

    dir_b  = save_model_bundle(result.baseline_model, result.cleaning_stats,
                               result.feature_stats, meta_baseline,
                               MODELS_DIR, overwrite=True)
    dir_rf = save_model_bundle(result.rf_model,       result.cleaning_stats,
                               result.feature_stats, meta_rf,
                               MODELS_DIR, overwrite=True)

    print(f"\nArtefacts saved:")
    print(f"  Baseline     : {dir_b}")
    print(f"  RandomForest : {dir_rf}")

    # 6. Round-trip verify
    bundle = load_model_bundle(dir_rf)
    assert bundle.metadata.model_name == "RandomForest"
    assert bundle.metadata.data_source == "SYNTHETIC"
    print("\nRound-trip load verified OK")
    print("\nDONE — proceed to benchmark_inference.py")


if __name__ == "__main__":
    main()
