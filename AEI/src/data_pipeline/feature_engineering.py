"""
AEI — Data Pipeline: Feature Engineering
==========================================
Transforms cleaned tabular data into model-ready features.

Design rules
------------
* All statistics fitted here (e.g. scaler parameters) are computed on the
  training split only and then applied to validation/test/inference data.
  This prevents data leakage.
* Features are derived only from information genuinely available at the time
  of prediction.  No future observations are used.
* Every transformation is documented.  Assumptions are explicit.
* The output DataFrame retains zone_id / event_id identifiers so it can be
  joined to GIS outputs downstream.

Current feature set (Milestone 1 — Kaggle S4E5 synthetic benchmark)
--------------------------------------------------------------------
Input: 20 synthetic indicator columns (0-10 scale each).
Engineered features:
  * composite_risk_raw  — unweighted sum of all 20 indicators
  * composite_risk_norm — composite_risk_raw scaled to [0, 1]
  * hydro_pressure      — sum of directly water-related indicators
  * governance_deficit  — sum of governance/planning indicators
  * infrastructure_stress — sum of infrastructure indicators
  * StandardScaler normalisation of each original feature

When real IMD rainfall + DEM data become available, add:
  * rainfall_3d_accumulation_mm
  * rainfall_anomaly_vs_30yr_mean
  * slope_deg (from DEM)
  * elevation_category (low / medium / high)
  * topographic_wetness_index (TWI) approximation

Leakage notes
-------------
* fit_feature_pipeline fits the scaler on training data.
* apply_feature_pipeline uses the fitted scaler for all other splits.
* The composite sums are purely additive and do not require fitting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column groups (Kaggle S4E5 schema)
# ---------------------------------------------------------------------------

# All 20 feature columns in the S4E5 dataset
ALL_INDICATOR_COLS: List[str] = [
    "MonsoonIntensity",
    "TopographyDrainage",
    "RiverManagement",
    "Deforestation",
    "Urbanization",
    "ClimateChange",
    "DamsQuality",
    "Siltation",
    "AgriculturalPractices",
    "Encroachments",
    "IneffectiveDisasterPrep",
    "WaterBodyChanges",
    "DeterioratingInfrastructure",
    "PopulationScore",
    "WetlandLoss",
    "InadequatePlanning",
    "PoliticalFactors",
    "DrainageSystems",
    "CoastalVulnerability",
    "Landslides",
]

# Thematic sub-groups — rationale documented for interpretability
HYDRO_PRESSURE_COLS: List[str] = [
    "MonsoonIntensity",
    "RiverManagement",
    "Siltation",
    "WaterBodyChanges",
    "WetlandLoss",
    "DrainageSystems",
    "CoastalVulnerability",
]

GOVERNANCE_DEFICIT_COLS: List[str] = [
    "IneffectiveDisasterPrep",
    "InadequatePlanning",
    "PoliticalFactors",
    "RiverManagement",
    "DamsQuality",
]

INFRASTRUCTURE_STRESS_COLS: List[str] = [
    "DeterioratingInfrastructure",
    "DrainageSystems",
    "Encroachments",
    "Urbanization",
    "TopographyDrainage",
]

# Columns that should be scaled (all numeric indicators)
SCALE_COLS: List[str] = ALL_INDICATOR_COLS

# Columns preserved as identifiers (never scaled)
ID_COLS: List[str] = ["zone_id", "event_id", "id", "latitude", "longitude",
                       "date", "data_source"]


# ---------------------------------------------------------------------------
# Fitted pipeline state
# ---------------------------------------------------------------------------

@dataclass
class FeaturePipelineStats:
    """
    Statistics fitted on the training set.
    Serialise alongside the model artefact (joblib).
    """
    scaler: Optional[StandardScaler] = None
    scaled_columns: List[str] = field(default_factory=list)
    fitted_on_rows: int = 0
    feature_columns_out: List[str] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fit_feature_pipeline(
    df: pd.DataFrame,
    scale_cols: Optional[List[str]] = None,
    indicator_cols: Optional[List[str]] = None,
) -> FeaturePipelineStats:
    """
    Fit feature-engineering statistics on the TRAINING DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Cleaned training data (output of cleaning.py).
    scale_cols : list of str, optional
        Columns to apply StandardScaler to.  Defaults to SCALE_COLS that
        are present in df.
    indicator_cols : list of str, optional
        Columns used for composite features.  Defaults to ALL_INDICATOR_COLS
        that are present in df.

    Returns
    -------
    FeaturePipelineStats
    """
    scale_cols = _present_cols(df, scale_cols or SCALE_COLS)
    indicator_cols = _present_cols(df, indicator_cols or ALL_INDICATOR_COLS)

    scaler = StandardScaler()
    if scale_cols:
        scaler.fit(df[scale_cols].values)
        logger.info("StandardScaler fitted on %d columns (%d rows).",
                    len(scale_cols), len(df))
    else:
        logger.warning("No scalable columns found in DataFrame.")

    # Determine output feature column names (filled in apply step)
    stats = FeaturePipelineStats(
        scaler=scaler,
        scaled_columns=scale_cols,
        fitted_on_rows=len(df),
        notes="Fitted on training data only — do not refit on val/test/inference.",
    )
    return stats


def apply_feature_pipeline(
    df: pd.DataFrame,
    stats: FeaturePipelineStats,
    indicator_cols: Optional[List[str]] = None,
    add_scaled: bool = True,
) -> pd.DataFrame:
    """
    Apply the fitted feature pipeline to any split.

    Engineered columns added
    ------------------------
    * composite_risk_raw       — sum of all indicator columns
    * composite_risk_norm      — composite_risk_raw / (n_cols * max_val)
    * hydro_pressure           — sum of HYDRO_PRESSURE_COLS
    * governance_deficit       — sum of GOVERNANCE_DEFICIT_COLS
    * infrastructure_stress    — sum of INFRASTRUCTURE_STRESS_COLS
    * <col>_scaled             — StandardScaler output (if add_scaled=True)

    Parameters
    ----------
    df : pd.DataFrame
        Cleaned data for any split.
    stats : FeaturePipelineStats
        From fit_feature_pipeline.
    indicator_cols : list of str, optional
    add_scaled : bool
        Whether to append <col>_scaled columns.

    Returns
    -------
    pd.DataFrame
        Original columns + engineered columns.  Original is not modified.
    """
    df = df.copy()
    indicator_cols = _present_cols(df, indicator_cols or ALL_INDICATOR_COLS)

    # ------------------------------------------------------------------ #
    # Composite features (no fitting needed — purely additive)
    # ------------------------------------------------------------------ #
    if indicator_cols:
        n = len(indicator_cols)
        max_val = 10.0  # documented scale of S4E5 indicators

        df["composite_risk_raw"] = df[indicator_cols].sum(axis=1)
        df["composite_risk_norm"] = df["composite_risk_raw"] / (n * max_val)

        # Thematic sub-scores
        hydro_cols     = _present_cols(df, HYDRO_PRESSURE_COLS)
        gov_cols       = _present_cols(df, GOVERNANCE_DEFICIT_COLS)
        infra_cols     = _present_cols(df, INFRASTRUCTURE_STRESS_COLS)

        df["hydro_pressure"]      = df[hydro_cols].sum(axis=1) if hydro_cols else 0.0
        df["governance_deficit"]  = df[gov_cols].sum(axis=1) if gov_cols else 0.0
        df["infrastructure_stress"] = df[infra_cols].sum(axis=1) if infra_cols else 0.0

        logger.info(
            "Composite features added: composite_risk_raw, composite_risk_norm, "
            "hydro_pressure, governance_deficit, infrastructure_stress."
        )
    else:
        logger.warning("No indicator columns found — composite features skipped.")

    # ------------------------------------------------------------------ #
    # Scaled features (use TRAINING scaler — no leakage)
    # ------------------------------------------------------------------ #
    if add_scaled and stats.scaler is not None and stats.scaled_columns:
        present = _present_cols(df, stats.scaled_columns)
        if present:
            scaled_values = stats.scaler.transform(df[present].values)
            for i, col in enumerate(present):
                df[f"{col}_scaled"] = scaled_values[:, i]
            logger.info("Scaled %d columns using fitted StandardScaler.", len(present))

    stats.feature_columns_out = [c for c in df.columns]
    return df


def build_model_feature_matrix(
    df: pd.DataFrame,
    feature_cols: Optional[List[str]] = None,
    target_col: Optional[str] = None,
) -> tuple[pd.DataFrame, Optional[pd.Series]]:
    """
    Extract the final feature matrix X and optional target y from an
    engineered DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Output of apply_feature_pipeline.
    feature_cols : list of str, optional
        Explicit list of columns to use as features.  Defaults to
        scaled indicator columns + composite features.
    target_col : str, optional
        Target column name.

    Returns
    -------
    (X, y)  where y is None if target_col is not present.
    """
    if feature_cols is None:
        # Prefer scaled columns; fall back to originals if scaling was skipped
        scaled = [f"{c}_scaled" for c in ALL_INDICATOR_COLS if f"{c}_scaled" in df.columns]
        composites = [c for c in ["composite_risk_raw", "composite_risk_norm",
                                   "hydro_pressure", "governance_deficit",
                                   "infrastructure_stress"] if c in df.columns]
        feature_cols = scaled + composites if scaled else (
            _present_cols(df, ALL_INDICATOR_COLS) + composites
        )

    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise KeyError(f"Feature columns not found in DataFrame: {missing}")

    X = df[feature_cols].copy()

    y = None
    if target_col and target_col in df.columns:
        y = df[target_col].copy()

    logger.info(
        "Feature matrix: %d rows × %d features. Target: %s",
        len(X), len(feature_cols), target_col or "none",
    )
    return X, y


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _present_cols(df: pd.DataFrame, cols: List[str]) -> List[str]:
    """Return only columns that exist in df, in order."""
    return [c for c in cols if c in df.columns]


def feature_column_report(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a summary of all engineered columns: name, dtype, null count,
    mean, std.
    """
    engineered = [c for c in df.columns
                  if c.endswith("_scaled") or c in
                  ["composite_risk_raw", "composite_risk_norm",
                   "hydro_pressure", "governance_deficit",
                   "infrastructure_stress"]]
    if not engineered:
        return pd.DataFrame(columns=["column", "dtype", "null_count", "mean", "std"])

    rows = []
    for col in engineered:
        s = df[col]
        rows.append({
            "column": col,
            "dtype": str(s.dtype),
            "null_count": int(s.isna().sum()),
            "mean": float(s.mean()) if s.dtype.kind in ("f", "i") else None,
            "std": float(s.std()) if s.dtype.kind in ("f", "i") else None,
        })
    return pd.DataFrame(rows)
