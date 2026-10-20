"""
Tests for src/data_pipeline/cleaning.py
=========================================
All fixtures are SYNTHETIC.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data_pipeline.cleaning import (
    CleaningStats,
    apply_cleaning_pipeline,
    clean_training_data,
    duplicate_report,
    fit_cleaning_pipeline,
    missing_value_report,
    numeric_summary,
)
from tests.fixtures.make_synthetic_fixture import FEATURE_COLS


# ---------------------------------------------------------------------------
# fit_cleaning_pipeline
# ---------------------------------------------------------------------------

class TestFitCleaningPipeline:
    def test_returns_cleaning_stats(self, clean_df):
        stats = fit_cleaning_pipeline(clean_df)
        assert isinstance(stats, CleaningStats)

    def test_medians_computed_for_numeric_cols(self, clean_df):
        stats = fit_cleaning_pipeline(clean_df)
        for col in FEATURE_COLS:
            assert col in stats.column_medians
            assert isinstance(stats.column_medians[col], float)

    def test_fitted_on_rows_matches(self, clean_df):
        stats = fit_cleaning_pipeline(clean_df)
        assert stats.fitted_on_rows == len(clean_df)

    def test_explicit_column_subset(self, clean_df):
        subset = ["MonsoonIntensity", "Urbanization"]
        stats = fit_cleaning_pipeline(clean_df, numeric_columns=subset)
        assert set(stats.column_medians.keys()) == set(subset)

    def test_all_null_column_gets_zero_median(self):
        df = pd.DataFrame({"A": [np.nan, np.nan, np.nan], "B": [1.0, 2.0, 3.0]})
        stats = fit_cleaning_pipeline(df, numeric_columns=["A"])
        assert stats.column_medians["A"] == 0.0


# ---------------------------------------------------------------------------
# apply_cleaning_pipeline — imputation
# ---------------------------------------------------------------------------

class TestApplyCleaningImputation:
    def test_nulls_filled_with_training_median(self, dirty_df):
        stats = fit_cleaning_pipeline(dirty_df)
        cleaned = apply_cleaning_pipeline(dirty_df, stats, drop_target_nulls=False)
        # MonsoonIntensity had nulls injected — should now have none
        assert cleaned["MonsoonIntensity"].isna().sum() == 0

    def test_imputed_value_equals_training_median(self):
        train = pd.DataFrame({"X": [2.0, 4.0, 6.0, 8.0]})
        stats = fit_cleaning_pipeline(train, numeric_columns=["X"])
        test_df = pd.DataFrame({"X": [np.nan, 5.0]})
        cleaned = apply_cleaning_pipeline(test_df, stats, drop_target_nulls=False)
        expected_median = 5.0  # median of [2, 4, 6, 8]
        assert cleaned.loc[0, "X"] == pytest.approx(expected_median)

    def test_non_null_values_unchanged(self, clean_df):
        stats = fit_cleaning_pipeline(clean_df)
        cleaned = apply_cleaning_pipeline(clean_df, stats, drop_target_nulls=False)
        pd.testing.assert_series_equal(
            clean_df["MonsoonIntensity"].reset_index(drop=True),
            cleaned["MonsoonIntensity"].reset_index(drop=True),
        )


# ---------------------------------------------------------------------------
# apply_cleaning_pipeline — deduplication
# ---------------------------------------------------------------------------

class TestApplyCleaningDeduplication:
    def test_duplicate_rows_removed(self, dirty_df):
        stats = fit_cleaning_pipeline(dirty_df)
        cleaned = apply_cleaning_pipeline(dirty_df, stats, drop_target_nulls=False)
        assert cleaned.duplicated().sum() == 0

    def test_unique_rows_preserved(self, clean_df):
        stats = fit_cleaning_pipeline(clean_df)
        cleaned = apply_cleaning_pipeline(clean_df, stats, drop_target_nulls=False)
        # clean_df has no duplicates — row count should be the same
        assert len(cleaned) == len(clean_df)


# ---------------------------------------------------------------------------
# apply_cleaning_pipeline — clipping
# ---------------------------------------------------------------------------

class TestApplyCleaningClipping:
    def test_out_of_range_values_clipped(self, dirty_df):
        bounds = {"Urbanization": (0.0, 10.0)}
        stats = fit_cleaning_pipeline(dirty_df, column_bounds=bounds)
        cleaned = apply_cleaning_pipeline(dirty_df, stats, drop_target_nulls=False)
        assert (cleaned["Urbanization"] <= 10.0).all()
        assert (cleaned["Urbanization"] >= 0.0).all()

    def test_in_range_values_unchanged(self):
        df = pd.DataFrame({"X": [1.0, 5.0, 9.0]})
        bounds = {"X": (0.0, 10.0)}
        stats = fit_cleaning_pipeline(df, column_bounds=bounds)
        cleaned = apply_cleaning_pipeline(df, stats, drop_target_nulls=False)
        pd.testing.assert_series_equal(df["X"], cleaned["X"])


# ---------------------------------------------------------------------------
# apply_cleaning_pipeline — target null dropping
# ---------------------------------------------------------------------------

class TestTargetNullDropping:
    def test_null_targets_dropped_when_requested(self, dirty_df):
        stats = fit_cleaning_pipeline(dirty_df)
        cleaned = apply_cleaning_pipeline(
            dirty_df, stats,
            drop_target_nulls=True,
            target_column="FloodProbability",
        )
        assert cleaned["FloodProbability"].isna().sum() == 0

    def test_null_targets_kept_when_not_requested(self):
        """
        When drop_target_nulls=False, nulls in the target column must survive
        cleaning.  Build a minimal controlled DataFrame with distinct feature
        rows (no duplicates) so deduplication does not remove any nulls.
        """
        from tests.fixtures.make_synthetic_fixture import FEATURE_COLS
        import pandas as pd, numpy as np

        # Each row has a unique value in MonsoonIntensity so no row is a duplicate
        rows = [{col: float(i) for col in FEATURE_COLS} for i in range(5)]
        df = pd.DataFrame(rows)
        df["FloodProbability"] = [0.5, np.nan, 0.3, np.nan, 0.8]

        stats = fit_cleaning_pipeline(df, numeric_columns=FEATURE_COLS)
        cleaned = apply_cleaning_pipeline(
            df, stats,
            drop_target_nulls=False,
            target_column="FloodProbability",
        )
        # Both null target rows must still be present
        assert cleaned["FloodProbability"].isna().sum() == 2

    def test_no_target_column_no_error(self, clean_df):
        stats = fit_cleaning_pipeline(clean_df)
        cleaned = apply_cleaning_pipeline(
            clean_df, stats,
            drop_target_nulls=True,
            target_column=None,
        )
        assert len(cleaned) == len(clean_df)


# ---------------------------------------------------------------------------
# Leakage safety — stats must come from training data
# ---------------------------------------------------------------------------

class TestLeakageSafety:
    def test_test_set_uses_training_median(self):
        """Median from training set must be used on test set, not test set median."""
        train = pd.DataFrame({"X": [0.0, 0.0, 0.0, 0.0]})   # training median = 0.0
        test  = pd.DataFrame({"X": [np.nan, 10.0]})           # test median would be 10.0

        stats = fit_cleaning_pipeline(train, numeric_columns=["X"])
        cleaned = apply_cleaning_pipeline(test, stats, drop_target_nulls=False)

        # Null must be filled with TRAINING median (0.0), not test median (10.0)
        assert cleaned.loc[0, "X"] == pytest.approx(0.0)

    def test_refit_on_test_would_give_different_result(self):
        """
        Control test: confirm that refitting on the test set would have given
        a different imputed value.  This documents the leakage risk.
        """
        test = pd.DataFrame({"X": [np.nan, 10.0]})
        wrong_stats = fit_cleaning_pipeline(test, numeric_columns=["X"])
        # median of [NaN, 10.0] = 10.0
        assert wrong_stats.column_medians["X"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# clean_training_data (convenience wrapper)
# ---------------------------------------------------------------------------

class TestCleanTrainingData:
    def test_returns_tuple(self, clean_df):
        result = clean_training_data(clean_df, target_column="FloodProbability")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_cleaned_df_no_nulls_in_features(self, dirty_df):
        cleaned, _ = clean_training_data(
            dirty_df,
            column_bounds={"Urbanization": (0.0, 10.0)},
            target_column="FloodProbability",
        )
        for col in FEATURE_COLS:
            assert cleaned[col].isna().sum() == 0, f"Nulls in {col} after cleaning"


# ---------------------------------------------------------------------------
# Diagnostic helpers
# ---------------------------------------------------------------------------

class TestDiagnosticHelpers:
    def test_missing_value_report_finds_nulls(self, dirty_df):
        report = missing_value_report(dirty_df)
        assert "MonsoonIntensity" in report["column"].values

    def test_missing_value_report_empty_when_clean(self, clean_df):
        report = missing_value_report(clean_df)
        assert len(report) == 0

    def test_duplicate_report_counts(self, dirty_df):
        report = duplicate_report(dirty_df)
        assert report["duplicate_rows"] > 0
        assert report["total_rows"] == report["duplicate_rows"] + report["unique_rows"]

    def test_numeric_summary_shape(self, clean_df):
        summary = numeric_summary(clean_df)
        assert "skewness" in summary.columns
        assert "kurtosis" in summary.columns
        # Should have a row per numeric column
        numeric_cols = clean_df.select_dtypes(include=[np.number]).columns
        assert len(summary) == len(numeric_cols)
