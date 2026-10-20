"""
AEI — Prediction: Model Training
==================================
Trains a mean-prediction baseline and a Random Forest regressor on the
cleaned, engineered feature matrix.

Scientific-integrity rules enforced here
-----------------------------------------
* Preprocessing (CleaningStats, FeaturePipelineStats) is fitted ONLY on the
  training split and never re-fitted on test or inference data.
* The train/test split is index-based (shuffle=False for datasets with
  temporal/event ordering; shuffle=True with fixed seed for i.i.d. data like
  S4E5).  The split strategy is recorded in ModelMetadata.
* Metrics are computed on the held-out test split only.
* The dataset provenance label from df.attrs["_data_source"] is written into
  ModelMetadata so it travels with every saved artefact.
* Scores on SYNTHETIC data must not be described as real-world accuracy.

City-independence
-----------------
The training function accepts any DataFrame that satisfies the feature schema.
No city names or coordinates are hardcoded.

Usage
-----
    from prediction.train import run_training_pipeline
    result = run_training_pipeline(df, target_col="FloodProbability")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from data_pipeline.cleaning import (
    CleaningStats,
    apply_cleaning_pipeline,
    fit_cleaning_pipeline,
)
from data_pipeline.feature_engineering import (
    ALL_INDICATOR_COLS,
    FeaturePipelineStats,
    apply_feature_pipeline,
    build_model_feature_matrix,
    fit_feature_pipeline,
)
from prediction.evaluate import compute_regression_metrics, RegressionMetrics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_TEST_FRACTION = 0.20
DEFAULT_RF_PARAMS: Dict = {
    "n_estimators": 200,
    "max_depth": None,
    "min_samples_leaf": 4,
    "n_jobs": -1,
    "random_state": 42,
}
RANDOM_SEED = 42


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class TrainingResult:
    """
    Everything produced by one run of the training pipeline.

    Attributes
    ----------
    baseline_model : MeanBaselineRegressor
    rf_model : RandomForestRegressor
    cleaning_stats : CleaningStats  — fitted on training split only
    feature_stats : FeaturePipelineStats  — fitted on training split only
    feature_cols : list[str]  — ordered list of columns used as X
    target_col : str
    baseline_metrics : RegressionMetrics  — measured on test split
    rf_metrics : RegressionMetrics  — measured on test split
    train_rows : int
    test_rows : int
    data_source : str  — provenance label from df.attrs
    split_strategy : str
    training_duration_s : float
    """
    baseline_model: "MeanBaselineRegressor"
    rf_model: RandomForestRegressor
    cleaning_stats: CleaningStats
    feature_stats: FeaturePipelineStats
    feature_cols: List[str]
    target_col: str
    baseline_metrics: RegressionMetrics
    rf_metrics: RegressionMetrics
    train_rows: int
    test_rows: int
    data_source: str
    split_strategy: str
    training_duration_s: float
    notes: str = ""


# ---------------------------------------------------------------------------
# Mean baseline
# ---------------------------------------------------------------------------

class MeanBaselineRegressor:
    """
    Predicts the training-set mean for every input.

    This is the simplest non-trivial baseline.  Any useful model must beat
    this on the test set.

    Attributes
    ----------
    mean_ : float  — training-set mean of the target column
    """

    def __init__(self) -> None:
        self.mean_: Optional[float] = None

    def fit(self, y_train: pd.Series) -> "MeanBaselineRegressor":
        self.mean_ = float(y_train.mean())
        logger.info("MeanBaselineRegressor fitted: mean = %.6f", self.mean_)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.mean_ is None:
            raise RuntimeError("MeanBaselineRegressor has not been fitted.")
        return np.full(len(X), self.mean_)

    def __repr__(self) -> str:
        return f"MeanBaselineRegressor(mean_={self.mean_})"


# ---------------------------------------------------------------------------
# Train / test split
# ---------------------------------------------------------------------------

def split_dataframe(
    df: pd.DataFrame,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    shuffle: bool = True,
    seed: int = RANDOM_SEED,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split a DataFrame into train and test portions.

    Parameters
    ----------
    df : pd.DataFrame
    test_fraction : float
        Fraction of rows assigned to the test split.
    shuffle : bool
        True for i.i.d. datasets (e.g. S4E5 — no temporal ordering).
        False for time-ordered datasets where future data must not
        contaminate the training set.
    seed : int
        Used only when shuffle=True.

    Returns
    -------
    (df_train, df_test)
    """
    n = len(df)
    if n < 10:
        raise ValueError(f"DataFrame too small to split: {n} rows.")

    if shuffle:
        rng = np.random.default_rng(seed)
        idx = rng.permutation(n)
    else:
        idx = np.arange(n)

    n_test = max(1, int(np.round(n * test_fraction)))
    n_train = n - n_test

    if n_train < 5:
        raise ValueError(
            f"Training split has only {n_train} rows after "
            f"test_fraction={test_fraction:.2f}.  Provide more data."
        )

    train_idx = idx[:n_train]
    test_idx = idx[n_train:]

    df_train = df.iloc[train_idx].reset_index(drop=True)
    df_test  = df.iloc[test_idx].reset_index(drop=True)

    strategy = f"random_shuffle_seed{seed}" if shuffle else "temporal_ordered"
    logger.info(
        "Split: %d train / %d test  (strategy=%s)",
        len(df_train), len(df_test), strategy,
    )
    return df_train, df_test


# ---------------------------------------------------------------------------
# Main training pipeline
# ---------------------------------------------------------------------------

def run_training_pipeline(
    df: pd.DataFrame,
    target_col: str = "FloodProbability",
    test_fraction: float = DEFAULT_TEST_FRACTION,
    shuffle: bool = True,
    rf_params: Optional[Dict] = None,
    feature_cols: Optional[List[str]] = None,
    column_bounds: Optional[Dict[str, tuple]] = None,
) -> TrainingResult:
    """
    End-to-end training pipeline.

    Steps
    -----
    1. Split raw DataFrame into train / test (no preprocessing applied yet).
    2. Fit CleaningStats on train split only.
    3. Clean both splits using training stats.
    4. Fit FeaturePipelineStats on cleaned train split only.
    5. Engineer features for both splits using training stats.
    6. Build feature matrices X_train, y_train, X_test, y_test.
    7. Fit MeanBaselineRegressor on y_train.
    8. Fit RandomForestRegressor on X_train, y_train.
    9. Evaluate both models on X_test, y_test.
    10. Return TrainingResult with all artefacts.

    Parameters
    ----------
    df : pd.DataFrame
        Raw input data.  Must contain target_col and the feature columns.
        df.attrs["_data_source"] should be set by the caller.
    target_col : str
    test_fraction : float
    shuffle : bool
        Set False for time-ordered data.
    rf_params : dict, optional
        Keyword args forwarded to RandomForestRegressor.
    feature_cols : list[str], optional
        Override the default feature column selection.
    column_bounds : dict, optional
        Per-column (min, max) bounds for clipping during cleaning.

    Returns
    -------
    TrainingResult
    """
    t_start = time.perf_counter()

    data_source = df.attrs.get("_data_source", "UNKNOWN")
    if data_source == "UNKNOWN":
        logger.warning(
            "df.attrs['_data_source'] is not set. "
            "Call load_csv with an explicit data_source_label."
        )

    rf_params = {**DEFAULT_RF_PARAMS, **(rf_params or {})}
    split_strategy = (
        f"random_shuffle_seed{rf_params.get('random_state', RANDOM_SEED)}"
        if shuffle else "temporal_ordered"
    )

    # ------------------------------------------------------------------
    # 1. Raw split — no preprocessing before split to prevent leakage
    # ------------------------------------------------------------------
    df_train_raw, df_test_raw = split_dataframe(
        df, test_fraction=test_fraction, shuffle=shuffle, seed=RANDOM_SEED
    )

    # ------------------------------------------------------------------
    # 2-3. Cleaning — fit on train, apply to both
    # ------------------------------------------------------------------
    indicator_cols = _resolve_indicator_cols(df)
    bounds = column_bounds or {col: (0.0, 10.0) for col in indicator_cols}

    cleaning_stats = fit_cleaning_pipeline(
        df_train_raw,
        numeric_columns=indicator_cols,
        column_bounds=bounds,
    )
    df_train_clean = apply_cleaning_pipeline(
        df_train_raw, cleaning_stats,
        drop_target_nulls=True, target_column=target_col,
    )
    df_test_clean = apply_cleaning_pipeline(
        df_test_raw, cleaning_stats,
        drop_target_nulls=False, target_column=target_col,
    )

    # ------------------------------------------------------------------
    # 4-5. Feature engineering — fit on train, apply to both
    # ------------------------------------------------------------------
    feature_stats = fit_feature_pipeline(df_train_clean)
    df_train_eng = apply_feature_pipeline(df_train_clean, feature_stats)
    df_test_eng  = apply_feature_pipeline(df_test_clean,  feature_stats)

    # ------------------------------------------------------------------
    # 6. Build feature matrices
    # ------------------------------------------------------------------
    X_train, y_train = build_model_feature_matrix(
        df_train_eng, feature_cols=feature_cols, target_col=target_col
    )
    X_test, y_test = build_model_feature_matrix(
        df_test_eng, feature_cols=feature_cols, target_col=target_col
    )

    # Drop test rows where target is null (they can't be evaluated)
    if y_test is not None:
        valid_mask = y_test.notna()
        X_test = X_test[valid_mask].reset_index(drop=True)
        y_test  = y_test[valid_mask].reset_index(drop=True)

    if y_train is None or len(y_train) == 0:
        raise ValueError(f"No training rows with non-null target '{target_col}'.")
    if y_test is None or len(y_test) == 0:
        raise ValueError(f"No test rows with non-null target '{target_col}'.")

    # ------------------------------------------------------------------
    # 7. Baseline
    # ------------------------------------------------------------------
    baseline = MeanBaselineRegressor()
    baseline.fit(y_train)

    # ------------------------------------------------------------------
    # 8. Random Forest
    # ------------------------------------------------------------------
    rf = RandomForestRegressor(**rf_params)
    logger.info(
        "Training RandomForestRegressor on %d rows × %d features ...",
        len(X_train), len(X_train.columns),
    )
    rf.fit(X_train, y_train)

    # ------------------------------------------------------------------
    # 9. Evaluation
    # ------------------------------------------------------------------
    baseline_preds = baseline.predict(X_test)
    rf_preds       = rf.predict(X_test)

    baseline_metrics = compute_regression_metrics(y_test.values, baseline_preds,
                                                  model_name="MeanBaseline")
    rf_metrics       = compute_regression_metrics(y_test.values, rf_preds,
                                                  model_name="RandomForest")

    t_elapsed = time.perf_counter() - t_start

    logger.info("Training complete in %.2f s", t_elapsed)
    logger.info("Baseline — MAE: %.6f  RMSE: %.6f",
                baseline_metrics.mae, baseline_metrics.rmse)
    logger.info("RF       — MAE: %.6f  RMSE: %.6f",
                rf_metrics.mae, rf_metrics.rmse)

    actual_feature_cols = list(X_train.columns)

    return TrainingResult(
        baseline_model=baseline,
        rf_model=rf,
        cleaning_stats=cleaning_stats,
        feature_stats=feature_stats,
        feature_cols=actual_feature_cols,
        target_col=target_col,
        baseline_metrics=baseline_metrics,
        rf_metrics=rf_metrics,
        train_rows=len(X_train),
        test_rows=len(X_test),
        data_source=data_source,
        split_strategy=split_strategy,
        training_duration_s=t_elapsed,
        notes=(
            f"Dataset provenance: {data_source}. "
            "Metrics on SYNTHETIC data are NOT evidence of real-world accuracy."
            if data_source in ("SYNTHETIC", "SIMULATED")
            else f"Dataset provenance: {data_source}."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_indicator_cols(df: pd.DataFrame) -> List[str]:
    """Return ALL_INDICATOR_COLS that are present in df."""
    return [c for c in ALL_INDICATOR_COLS if c in df.columns]
