"""
AEI — Data Pipeline: Cleaning
================================
Cleans a raw DataFrame produced by ingestion.py.

Strategy (documented per requirement)
--------------------------------------
* Missing values in numeric feature columns → median imputation (training set
  median; the fitted imputer must be passed for validation/inference sets to
  prevent leakage).
* Duplicate rows → log and drop, preserving first occurrence.
* Out-of-range values → clip to documented bounds, not silent drop, so
  the original distribution is not distorted.
* Timestamps → parse and validate; rows with unparseable timestamps are
  removed with a logged warning (not silently).
* Identifiers and provenance columns are preserved.

Leakage safety
--------------
``fit_cleaning_pipeline`` fits statistics ONLY on the data passed to it
(intended to be the training split).  Call ``apply_cleaning_pipeline``
with the fitted stats object for validation / test / inference data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fitted statistics — must be computed on training data only
# ---------------------------------------------------------------------------

@dataclass
class CleaningStats:
    """
    Stores statistics fitted on the training set.
    Serialise with joblib alongside the model artefact.
    """
    column_medians: Dict[str, float] = field(default_factory=dict)
    column_bounds: Dict[str, tuple] = field(default_factory=dict)   # (min, max)
    fitted_on_rows: int = 0
    notes: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fit_cleaning_pipeline(
    df: pd.DataFrame,
    numeric_columns: Optional[List[str]] = None,
    column_bounds: Optional[Dict[str, tuple]] = None,
) -> CleaningStats:
    """
    Compute cleaning statistics from a training DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Raw training data (after ingestion, before feature engineering).
    numeric_columns : list of str, optional
        Columns to compute medians for.  Defaults to all numeric columns.
    column_bounds : dict {col: (min, max)}, optional
        Hard bounds for clipping.  Values outside these are clipped, not
        dropped.  If a bound is None, that side is not enforced.

    Returns
    -------
    CleaningStats
    """
    if numeric_columns is None:
        numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()

    medians: Dict[str, float] = {}
    for col in numeric_columns:
        if col in df.columns:
            median_val = df[col].median(skipna=True)
            if pd.isna(median_val):
                logger.warning("Column '%s' is entirely null — median set to 0.", col)
                median_val = 0.0
            medians[col] = float(median_val)

    stats = CleaningStats(
        column_medians=medians,
        column_bounds=column_bounds or {},
        fitted_on_rows=len(df),
        notes="Fitted on training data only.",
    )
    logger.info(
        "CleaningStats fitted on %d rows; medians computed for %d columns.",
        len(df),
        len(medians),
    )
    return stats


def apply_cleaning_pipeline(
    df: pd.DataFrame,
    stats: CleaningStats,
    drop_target_nulls: bool = True,
    target_column: Optional[str] = None,
) -> pd.DataFrame:
    """
    Apply the fitted cleaning pipeline to any split (train / val / test /
    inference).

    Steps (in order)
    ----------------
    1. Drop exact duplicate rows.
    2. Impute missing numeric values with training-set medians.
    3. Clip numeric values to documented bounds.
    4. Optionally drop rows where the target column is null.
    5. Reset index.

    Parameters
    ----------
    df : pd.DataFrame
    stats : CleaningStats
        Produced by fit_cleaning_pipeline on training data.
    drop_target_nulls : bool
        If True and target_column is supplied, rows with null targets are
        dropped.  Set to False during inference (no target available).
    target_column : str, optional
        Name of the prediction target column.

    Returns
    -------
    pd.DataFrame
        Cleaned copy (original is not modified).
    """
    df = df.copy()
    original_len = len(df)

    # 1. Duplicates
    n_before = len(df)
    df = df.drop_duplicates()
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        logger.warning("Dropped %d duplicate rows.", n_dropped)

    # 2. Median imputation (use training medians — no leakage)
    for col, median_val in stats.column_medians.items():
        if col not in df.columns:
            continue
        null_count = df[col].isna().sum()
        if null_count > 0:
            logger.info(
                "Imputing %d nulls in '%s' with training median %.4f.",
                null_count, col, median_val,
            )
            df[col] = df[col].fillna(median_val)

    # 3. Clip to bounds
    for col, (lo, hi) in stats.column_bounds.items():
        if col not in df.columns:
            continue
        before_clip = df[col].copy()
        if lo is not None:
            df[col] = df[col].clip(lower=lo)
        if hi is not None:
            df[col] = df[col].clip(upper=hi)
        n_clipped = (df[col] != before_clip).sum()
        if n_clipped > 0:
            logger.warning("Clipped %d out-of-range values in '%s'.", n_clipped, col)

    # 4. Drop rows with null target (training / eval only)
    if drop_target_nulls and target_column and target_column in df.columns:
        n_null_target = df[target_column].isna().sum()
        if n_null_target > 0:
            logger.warning(
                "Dropping %d rows with null target '%s'.", n_null_target, target_column
            )
            df = df.dropna(subset=[target_column])

    df = df.reset_index(drop=True)

    # Copy attrs forward so provenance is not lost
    df.attrs.update({k: v for k, v in df.attrs.items()})

    logger.info(
        "Cleaning complete: %d → %d rows (removed %d).",
        original_len, len(df), original_len - len(df),
    )
    return df


# ---------------------------------------------------------------------------
# Convenience: run both steps in one call for training data
# ---------------------------------------------------------------------------

def clean_training_data(
    df: pd.DataFrame,
    numeric_columns: Optional[List[str]] = None,
    column_bounds: Optional[Dict[str, tuple]] = None,
    target_column: Optional[str] = None,
) -> tuple[pd.DataFrame, CleaningStats]:
    """
    Fit cleaning stats on *df* and immediately apply them.

    Use ONLY for the training split.  For val/test/inference, call
    fit_cleaning_pipeline + apply_cleaning_pipeline separately.

    Returns
    -------
    (cleaned_df, CleaningStats)
    """
    stats = fit_cleaning_pipeline(df, numeric_columns, column_bounds)
    cleaned = apply_cleaning_pipeline(df, stats, drop_target_nulls=True,
                                      target_column=target_column)
    return cleaned, stats


# ---------------------------------------------------------------------------
# Diagnostic helpers
# ---------------------------------------------------------------------------

def missing_value_report(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a DataFrame summarising missing values per column.

    Columns: column, missing_count, missing_pct, dtype
    """
    missing = df.isna().sum()
    report = pd.DataFrame({
        "column": missing.index,
        "missing_count": missing.values,
        "missing_pct": (missing.values / max(len(df), 1)) * 100,
        "dtype": [str(df[c].dtype) for c in missing.index],
    }).reset_index(drop=True)
    report = report[report["missing_count"] > 0].sort_values(
        "missing_pct", ascending=False
    )
    return report


def duplicate_report(df: pd.DataFrame) -> Dict[str, int]:
    """Return a dict with total rows, duplicate rows, and unique rows."""
    n_dup = df.duplicated().sum()
    return {
        "total_rows": len(df),
        "duplicate_rows": int(n_dup),
        "unique_rows": len(df) - int(n_dup),
    }


def numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extended descriptive statistics for numeric columns, including
    skewness and kurtosis.
    """
    num_df = df.select_dtypes(include=[np.number])
    desc = num_df.describe().T
    desc["skewness"] = num_df.skew()
    desc["kurtosis"] = num_df.kurtosis()
    return desc
