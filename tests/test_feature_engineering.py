"""
Tests for src/data_pipeline/feature_engineering.py
=====================================================
All fixtures are SYNTHETIC.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

from data_pipeline.cleaning import fit_cleaning_pipeline, apply_cleaning_pipeline
from data_pipeline.feature_engineering import (
    ALL_INDICATOR_COLS,
    FeaturePipelineStats,
    HYDRO_PRESSURE_COLS,
    apply_feature_pipeline,
    build_model_feature_matrix,
    feature_column_report,
    fit_feature_pipeline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleaned(df: pd.DataFrame) -> pd.DataFrame:
    stats = fit_cleaning_pipeline(df)
    return apply_cleaning_pipeline(df, stats, drop_target_nulls=True,
                                   target_column="FloodProbability")


# ---------------------------------------------------------------------------
# fit_feature_pipeline
# ---------------------------------------------------------------------------

class TestFitFeaturePipeline:
    def test_returns_feature_pipeline_stats(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        assert isinstance(stats, FeaturePipelineStats)

    def test_scaler_fitted(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        assert stats.scaler is not None
        assert hasattr(stats.scaler, "mean_")  # sklearn sets this after fit

    def test_fitted_on_rows_correct(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        assert stats.fitted_on_rows == len(clean_df)

    def test_scaled_columns_list_populated(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        assert len(stats.scaled_columns) > 0
        for col in stats.scaled_columns:
            assert col in clean_df.columns

    def test_custom_scale_cols(self, clean_df):
        subset = ["MonsoonIntensity", "Urbanization"]
        stats = fit_feature_pipeline(clean_df, scale_cols=subset)
        assert stats.scaled_columns == subset


# ---------------------------------------------------------------------------
# apply_feature_pipeline — composite features
# ---------------------------------------------------------------------------

class TestCompositeFeatures:
    def test_composite_risk_raw_added(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        out = apply_feature_pipeline(clean_df, stats)
        assert "composite_risk_raw" in out.columns

    def test_composite_risk_norm_in_range(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        out = apply_feature_pipeline(clean_df, stats)
        assert out["composite_risk_norm"].between(0.0, 1.0).all()

    def test_composite_risk_raw_equals_sum(self, minimal_df):
        stats = fit_feature_pipeline(minimal_df)
        out = apply_feature_pipeline(minimal_df, stats)
        present = [c for c in ALL_INDICATOR_COLS if c in minimal_df.columns]
        expected = minimal_df[present].sum(axis=1)
        pd.testing.assert_series_equal(
            out["composite_risk_raw"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_hydro_pressure_added(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        out = apply_feature_pipeline(clean_df, stats)
        assert "hydro_pressure" in out.columns

    def test_governance_deficit_added(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        out = apply_feature_pipeline(clean_df, stats)
        assert "governance_deficit" in out.columns

    def test_infrastructure_stress_added(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        out = apply_feature_pipeline(clean_df, stats)
        assert "infrastructure_stress" in out.columns

    def test_composite_norm_correct_formula(self, minimal_df):
        """composite_risk_norm should be raw / (n_cols * 10)."""
        n_cols = len([c for c in ALL_INDICATOR_COLS if c in minimal_df.columns])
        stats = fit_feature_pipeline(minimal_df)
        out = apply_feature_pipeline(minimal_df, stats)
        expected_norm = out["composite_risk_raw"] / (n_cols * 10.0)
        pd.testing.assert_series_equal(
            out["composite_risk_norm"].reset_index(drop=True),
            expected_norm.reset_index(drop=True),
            check_names=False,
        )


# ---------------------------------------------------------------------------
# apply_feature_pipeline — scaled columns
# ---------------------------------------------------------------------------

class TestScaledColumns:
    def test_scaled_columns_added(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        out = apply_feature_pipeline(clean_df, stats, add_scaled=True)
        for col in stats.scaled_columns:
            assert f"{col}_scaled" in out.columns

    def test_scaled_columns_approximately_zero_mean(self, clean_df):
        """StandardScaler should produce near-zero mean on training data."""
        stats = fit_feature_pipeline(clean_df)
        out = apply_feature_pipeline(clean_df, stats, add_scaled=True)
        for col in stats.scaled_columns[:3]:  # spot-check 3
            mean_val = out[f"{col}_scaled"].mean()
            assert abs(mean_val) < 0.1, (
                f"{col}_scaled mean {mean_val:.4f} not near zero — scaler may be misapplied."
            )

    def test_no_scaled_columns_when_disabled(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        out = apply_feature_pipeline(clean_df, stats, add_scaled=False)
        scaled = [c for c in out.columns if c.endswith("_scaled")]
        assert len(scaled) == 0

    def test_leakage_scaler_uses_training_params(self, clean_df):
        """
        Apply training scaler to a test set with known values and verify
        the output matches manual calculation.
        """
        # Fit on clean_df (training)
        stats = fit_feature_pipeline(clean_df)

        # Build a one-row test set with all features = 0
        test_row = {col: 0.0 for col in ALL_INDICATOR_COLS if col in clean_df.columns}
        test_df = pd.DataFrame([test_row])

        out = apply_feature_pipeline(test_df, stats, add_scaled=True)

        # For a StandardScaler: scaled = (x - mean) / std
        # With x=0: scaled = -mean / std
        col = stats.scaled_columns[0]
        expected = -stats.scaler.mean_[0] / stats.scaler.scale_[0]
        assert out.loc[0, f"{col}_scaled"] == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# build_model_feature_matrix
# ---------------------------------------------------------------------------

class TestBuildModelFeatureMatrix:
    def test_returns_X_and_y(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        engineered = apply_feature_pipeline(clean_df, stats)
        X, y = build_model_feature_matrix(engineered, target_col="FloodProbability")
        assert X is not None
        assert y is not None
        assert len(X) == len(clean_df)
        assert len(y) == len(clean_df)

    def test_y_is_none_when_target_missing(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        engineered = apply_feature_pipeline(clean_df, stats)
        X, y = build_model_feature_matrix(engineered, target_col=None)
        assert y is None

    def test_missing_feature_col_raises(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        engineered = apply_feature_pipeline(clean_df, stats)
        with pytest.raises(KeyError, match="Feature columns not found"):
            build_model_feature_matrix(
                engineered,
                feature_cols=["nonexistent_col"],
                target_col="FloodProbability",
            )

    def test_explicit_feature_cols_respected(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        engineered = apply_feature_pipeline(clean_df, stats)
        X, _ = build_model_feature_matrix(
            engineered,
            feature_cols=["composite_risk_raw", "composite_risk_norm"],
        )
        assert list(X.columns) == ["composite_risk_raw", "composite_risk_norm"]

    def test_X_has_no_nulls(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        engineered = apply_feature_pipeline(clean_df, stats)
        X, _ = build_model_feature_matrix(engineered, target_col="FloodProbability")
        assert X.isna().sum().sum() == 0


# ---------------------------------------------------------------------------
# Original columns not mutated
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_original_df_not_modified(self, clean_df):
        original_cols = list(clean_df.columns)
        stats = fit_feature_pipeline(clean_df)
        _ = apply_feature_pipeline(clean_df, stats)
        assert list(clean_df.columns) == original_cols


# ---------------------------------------------------------------------------
# feature_column_report
# ---------------------------------------------------------------------------

class TestFeatureColumnReport:
    def test_report_lists_engineered_columns(self, clean_df):
        stats = fit_feature_pipeline(clean_df)
        out = apply_feature_pipeline(clean_df, stats)
        report = feature_column_report(out)
        assert "composite_risk_raw" in report["column"].values

    def test_report_empty_when_no_engineered_cols(self, clean_df):
        report = feature_column_report(clean_df)  # raw df, no engineered cols
        assert len(report) == 0
