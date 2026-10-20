"""
Tests for src/data_pipeline/ingestion.py
==========================================
All fixtures are SYNTHETIC — results here are not real-world validation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from data_pipeline.ingestion import (
    DATA_SOURCE_LABELS,
    ColumnSpec,
    DatasetSchema,
    ValidationResult,
    load_csv,
    validate_dataframe,
    SCHEMA_REGISTRY,
    _check_source_label,
)


# ---------------------------------------------------------------------------
# Source-label validation
# ---------------------------------------------------------------------------

class TestSourceLabel:
    def test_valid_labels_accepted(self):
        for label in DATA_SOURCE_LABELS:
            _check_source_label(label)  # should not raise

    def test_invalid_label_raises(self):
        with pytest.raises(ValueError, match="data_source_label must be one of"):
            _check_source_label("MADE_UP")

    def test_empty_label_raises(self):
        with pytest.raises(ValueError):
            _check_source_label("")


# ---------------------------------------------------------------------------
# load_csv
# ---------------------------------------------------------------------------

class TestLoadCSV:
    def test_loads_clean_csv(self, clean_csv_path):
        df = load_csv(clean_csv_path, "SYNTHETIC")
        assert len(df) == 200
        assert df.attrs["_data_source"] == "SYNTHETIC"
        assert df.attrs["_source_file"] == str(clean_csv_path)

    def test_schema_name_stored_in_attrs(self, clean_csv_path):
        df = load_csv(clean_csv_path, "SYNTHETIC", schema_name="kaggle_s4e5")
        assert df.attrs["_schema_name"] == "kaggle_s4e5"

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_csv(tmp_path / "missing.csv", "SYNTHETIC")

    def test_invalid_source_label_raises(self, clean_csv_path):
        with pytest.raises(ValueError):
            load_csv(clean_csv_path, "FAKE_LABEL")

    def test_schema_validation_on_load(self, clean_csv_path):
        # Should not raise — clean fixture satisfies kaggle_s4e5 schema
        df = load_csv(clean_csv_path, "SYNTHETIC", schema_name="kaggle_s4e5")
        assert "FloodProbability" in df.columns

    def test_unknown_schema_raises(self, clean_csv_path):
        with pytest.raises(ValueError, match="Unknown schema"):
            load_csv(clean_csv_path, "SYNTHETIC", schema_name="does_not_exist")

    def test_missing_required_column_raises(self, tmp_path):
        # Write a CSV missing MonsoonIntensity
        import pandas as pd
        df = pd.DataFrame({"SomeCol": [1, 2, 3], "FloodProbability": [0.1, 0.2, 0.3]})
        p = tmp_path / "bad.csv"
        df.to_csv(p, index=False)
        with pytest.raises(ValueError, match="Required column 'MonsoonIntensity' is missing"):
            load_csv(p, "SYNTHETIC", schema_name="kaggle_s4e5")


# ---------------------------------------------------------------------------
# validate_dataframe
# ---------------------------------------------------------------------------

class TestValidateDataframe:
    def test_clean_df_valid(self, clean_df):
        result = validate_dataframe(clean_df, "kaggle_s4e5")
        assert result.valid, f"Expected valid but got errors: {result.errors}"

    def test_unknown_schema_returns_invalid(self, clean_df):
        result = validate_dataframe(clean_df, "nonexistent_schema")
        assert not result.valid
        assert any("Unknown schema" in e for e in result.errors)

    def test_empty_dataframe_warns(self):
        import pandas as pd
        from tests.fixtures.make_synthetic_fixture import FEATURE_COLS
        # Explicitly type all columns as float64 so dtype checks pass on empty frame
        dtypes = {col: "float64" for col in FEATURE_COLS}
        dtypes["FloodProbability"] = "float64"
        empty = pd.DataFrame(columns=FEATURE_COLS + ["FloodProbability"]).astype(dtypes)
        result = validate_dataframe(empty, "kaggle_s4e5")
        assert result.valid, f"Expected valid (no data errors) but got: {result.errors}"
        assert any("0 rows" in w for w in result.warnings)

    def test_out_of_range_column_fails(self, clean_df):
        df = clean_df.copy()
        df.loc[0, "MonsoonIntensity"] = 999.0  # above max of 10
        result = validate_dataframe(df, "kaggle_s4e5")
        assert not result.valid
        assert any("MonsoonIntensity" in e and "maximum" in e for e in result.errors)

    def test_below_range_column_fails(self, clean_df):
        df = clean_df.copy()
        df.loc[0, "MonsoonIntensity"] = -1.0  # below min of 0
        result = validate_dataframe(df, "kaggle_s4e5")
        assert not result.valid

    def test_flood_probability_out_of_range_fails(self, clean_df):
        df = clean_df.copy()
        df.loc[0, "FloodProbability"] = 1.5  # above max of 1
        result = validate_dataframe(df, "kaggle_s4e5")
        assert not result.valid

    def test_high_null_rate_warns(self, clean_df):
        df = clean_df.copy()
        # Set 50% of MonsoonIntensity to null — should warn
        df.loc[:99, "MonsoonIntensity"] = float("nan")
        result = validate_dataframe(df, "kaggle_s4e5")
        # Still valid (column is nullable) but should have a warning
        assert any("MonsoonIntensity" in w for w in result.warnings)

    def test_non_nullable_column_with_nulls_fails(self, clean_df):
        # FloodProbability is not nullable in optional spec; zone_id is not nullable
        # Test with imd_rainfall schema: latitude is not nullable
        import pandas as pd
        df = pd.DataFrame({
            "latitude": [None, 18.5],
            "longitude": [73.8, 73.8],
            "date": pd.to_datetime(["2023-06-01", "2023-06-02"]),
            "rainfall_mm": [10.0, 5.0],
        })
        result = validate_dataframe(df, "imd_rainfall")
        assert not result.valid
        assert any("latitude" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------

class TestSchemaRegistry:
    def test_required_schemas_present(self):
        for name in ("kaggle_s4e5", "imd_rainfall", "copernicus_dem", "aei_processed"):
            assert name in SCHEMA_REGISTRY, f"Schema '{name}' missing from registry"

    def test_kaggle_schema_has_target(self):
        assert SCHEMA_REGISTRY["kaggle_s4e5"].target_column == "FloodProbability"

    def test_imd_schema_notes_daily_resolution(self):
        notes = SCHEMA_REGISTRY["imd_rainfall"].notes.upper()
        assert "DAILY" in notes

    def test_kaggle_schema_notes_synthetic(self):
        notes = SCHEMA_REGISTRY["kaggle_s4e5"].notes.upper()
        assert "SYNTHETIC" in notes
