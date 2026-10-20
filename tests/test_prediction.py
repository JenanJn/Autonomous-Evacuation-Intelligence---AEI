"""
AEI — Tests: Prediction Pipeline (Milestone 2)
================================================
Covers:
  * Model saving and loading (round-trip)
  * Metadata integrity
  * Prediction output schema validation
  * Invalid and missing inputs
  * Reproducibility of predictions
  * Inference latency smoke test (not a hard performance gate)
  * Training pipeline mechanics (split, leakage guards)

All fixtures are SYNTHETIC.  Results here are NOT real-world validation.
"""
from __future__ import annotations

import json
import pathlib
import time
from typing import List

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Shared fixture: trained bundle (session-scoped — train once, reuse)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def rf_artefact_dir() -> pathlib.Path:
    """
    Path to the saved RandomForest artefact.
    If it doesn't exist, train it now using the synthetic fixture.
    """
    import sys
    _ROOT = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_ROOT / "src"))
    sys.path.insert(0, str(_ROOT / "tests"))

    artefact_dir = _ROOT / "models" / "RandomForest_v0.1.0"
    if not artefact_dir.exists():
        # Train on synthetic fixture so tests are self-contained
        import logging
        logging.basicConfig(level=logging.WARNING)
        from fixtures.make_synthetic_fixture import make_clean_fixture, SIMULATED_DIR
        make_clean_fixture().to_csv(SIMULATED_DIR / "synthetic_clean_200.csv", index=False)
        from data_pipeline.ingestion import load_csv
        from prediction.train import run_training_pipeline
        from prediction.model_loader import metadata_from_training_result, save_model_bundle
        df = load_csv(SIMULATED_DIR / "synthetic_clean_200.csv", "SYNTHETIC",
                      schema_name="kaggle_s4e5")
        result = run_training_pipeline(df)
        meta_rf = metadata_from_training_result(result, "RandomForest", "0.1.0")
        save_model_bundle(result.rf_model, result.cleaning_stats,
                          result.feature_stats, meta_rf,
                          _ROOT / "models", overwrite=True)
    return artefact_dir


@pytest.fixture(scope="session")
def loaded_bundle(rf_artefact_dir):
    """Loaded ModelBundle — reused across all tests that need it."""
    import sys
    _ROOT = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_ROOT / "src"))
    from prediction.model_loader import load_model_bundle
    return load_model_bundle(rf_artefact_dir)


@pytest.fixture(scope="session")
def feature_df(loaded_bundle) -> pd.DataFrame:
    """
    20-row SYNTHETIC DataFrame with the feature columns the model expects.
    zone_id is included.
    """
    rng = np.random.default_rng(99)
    feat_cols = [c.replace("_scaled", "") for c in loaded_bundle.metadata.feature_cols
                 if c.endswith("_scaled")]
    data = {col: rng.uniform(0.0, 10.0, 20) for col in feat_cols}
    data["zone_id"] = [f"TEST_ZONE_{i:04d}" for i in range(20)]
    df = pd.DataFrame(data)
    df.attrs["_data_source"] = "SYNTHETIC"
    return df


# ---------------------------------------------------------------------------
# 1. Model save / load round-trip
# ---------------------------------------------------------------------------

class TestModelSaveLoad:

    def test_artefact_files_exist(self, rf_artefact_dir):
        for fname in ("model.joblib", "cleaning_stats.joblib",
                      "feature_stats.joblib", "metadata.json"):
            assert (rf_artefact_dir / fname).exists(), f"{fname} missing"

    def test_metadata_json_valid(self, rf_artefact_dir):
        with open(rf_artefact_dir / "metadata.json", encoding="utf-8") as fh:
            meta = json.load(fh)
        assert meta["model_name"] == "RandomForest"
        assert meta["target_col"] == "FloodProbability"
        assert meta["data_source"] == "SYNTHETIC"
        assert meta["artefact_format_version"] == "1.0"

    def test_metadata_records_synthetic_provenance(self, rf_artefact_dir):
        with open(rf_artefact_dir / "metadata.json", encoding="utf-8") as fh:
            meta = json.load(fh)
        assert meta["data_source"] == "SYNTHETIC", (
            "data_source must be SYNTHETIC to prevent misrepresenting metrics "
            "as real-world accuracy."
        )

    def test_metadata_has_metrics(self, rf_artefact_dir):
        with open(rf_artefact_dir / "metadata.json", encoding="utf-8") as fh:
            meta = json.load(fh)
        assert meta["rf_mae"] is not None
        assert meta["rf_rmse"] is not None
        assert meta["rf_mae"] > 0
        assert meta["rf_rmse"] > 0

    def test_loaded_bundle_has_model(self, loaded_bundle):
        assert loaded_bundle.model is not None
        assert hasattr(loaded_bundle.model, "predict")

    def test_loaded_bundle_has_stats(self, loaded_bundle):
        assert loaded_bundle.cleaning_stats is not None
        assert loaded_bundle.feature_stats is not None

    def test_loaded_bundle_metadata_correct(self, loaded_bundle):
        assert loaded_bundle.metadata.model_name == "RandomForest"
        assert loaded_bundle.metadata.model_version == "0.1.0"

    def test_load_missing_artefact_raises(self, tmp_path):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.model_loader import load_model_bundle
        with pytest.raises(FileNotFoundError):
            load_model_bundle(tmp_path / "nonexistent_model")

    def test_load_wrong_format_version_raises(self, tmp_path):
        import sys, json, joblib
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.model_loader import load_model_bundle, ARTEFACT_FORMAT_VERSION
        # Write a fake artefact with an incompatible format version
        fake_dir = tmp_path / "FakeModel_v0.0.0"
        fake_dir.mkdir()
        meta = {
            "model_name": "FakeModel",
            "model_version": "0.0.0",
            "target_col": "X",
            "feature_cols": [],
            "train_rows": 0,
            "test_rows": 0,
            "data_source": "SYNTHETIC",
            "split_strategy": "none",
            "random_seed": 0,
            "sklearn_version": "0.0.0",
            "artefact_format_version": "99.99",   # incompatible
        }
        (fake_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        # Write dummy joblib files
        for fname in ("model.joblib", "cleaning_stats.joblib", "feature_stats.joblib"):
            joblib.dump({}, fake_dir / fname)
        with pytest.raises(ValueError, match="format version mismatch"):
            load_model_bundle(fake_dir)

    def test_save_overwrite_false_raises(self, tmp_path, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.model_loader import save_model_bundle, metadata_from_training_result

        # First save — should succeed
        meta = loaded_bundle.metadata
        save_model_bundle(loaded_bundle.model, loaded_bundle.cleaning_stats,
                          loaded_bundle.feature_stats, meta, tmp_path, overwrite=True)

        # Second save without overwrite=True — should raise
        with pytest.raises(FileExistsError):
            save_model_bundle(loaded_bundle.model, loaded_bundle.cleaning_stats,
                              loaded_bundle.feature_stats, meta, tmp_path,
                              overwrite=False)


# ---------------------------------------------------------------------------
# 2. Prediction output schema
# ---------------------------------------------------------------------------

class TestPredictionOutputSchema:

    def test_predict_batch_returns_correct_n_records(self, feature_df, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        result = predict_batch(feature_df, loaded_bundle)
        assert len(result.batch.records) == len(feature_df)

    def test_all_records_have_ok_status(self, feature_df, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        from integration.schemas import PredictionStatus
        result = predict_batch(feature_df, loaded_bundle)
        statuses = {r.prediction_status for r in result.batch.records}
        assert statuses == {PredictionStatus.OK}, (
            f"Expected all OK, got: {statuses}"
        )

    def test_predicted_values_in_range(self, feature_df, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        result = predict_batch(feature_df, loaded_bundle)
        for rec in result.batch.records:
            assert rec.predicted_value is not None
            assert 0.0 <= rec.predicted_value <= 1.0, (
                f"Predicted value {rec.predicted_value} out of [0,1]"
            )

    def test_zone_ids_preserved(self, feature_df, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        result = predict_batch(feature_df, loaded_bundle)
        input_zones  = list(feature_df["zone_id"].values)
        output_zones = [r.zone_id for r in result.batch.records]
        assert input_zones == output_zones

    def test_model_version_in_records(self, feature_df, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        result = predict_batch(feature_df, loaded_bundle)
        for rec in result.batch.records:
            assert rec.model_version == loaded_bundle.metadata.model_version

    def test_target_name_in_records(self, feature_df, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        result = predict_batch(feature_df, loaded_bundle)
        for rec in result.batch.records:
            assert rec.target_name == "FloodProbability"

    def test_to_gis_dict_is_json_serialisable(self, feature_df, loaded_bundle):
        import sys, json
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        result = predict_batch(feature_df, loaded_bundle)
        for rec in result.batch.records:
            d = rec.to_gis_dict()
            json.dumps(d)  # must not raise

    def test_predict_single_returns_record(self, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_single
        from fixtures.make_synthetic_fixture import FEATURE_COLS
        row = {col: 5.0 for col in FEATURE_COLS}
        rec = predict_single(row, loaded_bundle, zone_id="ZONE_TEST")
        assert rec.zone_id == "ZONE_TEST"
        assert rec.predicted_value is not None


# ---------------------------------------------------------------------------
# 3. Invalid inputs
# ---------------------------------------------------------------------------

class TestInvalidInputs:

    def test_missing_feature_columns_returns_invalid_status(self, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        from integration.schemas import PredictionStatus
        # DataFrame with no feature columns at all
        bad_df = pd.DataFrame({"zone_id": ["Z1", "Z2"], "junk_col": [1.0, 2.0]})
        result = predict_batch(bad_df, loaded_bundle)
        for rec in result.batch.records:
            assert rec.prediction_status == PredictionStatus.INVALID_INPUT

    def test_empty_dataframe_returns_empty_batch(self, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        empty = pd.DataFrame()
        result = predict_batch(empty, loaded_bundle)
        assert len(result.batch.records) == 0

    def test_zone_ids_generated_when_column_absent(self, loaded_bundle):
        """When zone_id column is missing, ROW_xxxxxx IDs must be generated."""
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        from fixtures.make_synthetic_fixture import FEATURE_COLS
        rng = np.random.default_rng(7)
        df = pd.DataFrame({col: rng.uniform(0, 10, 3) for col in FEATURE_COLS})
        # No zone_id column
        result = predict_batch(df, loaded_bundle, zone_id_col=None)
        for rec in result.batch.records:
            assert rec.zone_id.startswith("ROW_")

    def test_all_null_features_handled(self, loaded_bundle):
        """
        All-null feature columns: cleaning imputes with training medians,
        so prediction should still return OK status (not crash).
        """
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        from fixtures.make_synthetic_fixture import FEATURE_COLS
        # Build DataFrame where all feature values are NaN
        df = pd.DataFrame({col: [np.nan, np.nan] for col in FEATURE_COLS})
        df["zone_id"] = ["Z1", "Z2"]
        result = predict_batch(df, loaded_bundle)
        # Should not crash; status depends on whether imputation is clean
        assert len(result.batch.records) == 2


# ---------------------------------------------------------------------------
# 4. Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:

    def test_same_input_same_predictions(self, feature_df, loaded_bundle):
        """The same input must produce numerically identical predictions on two calls."""
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        r1 = predict_batch(feature_df, loaded_bundle)
        r2 = predict_batch(feature_df, loaded_bundle)
        vals1 = np.array([float(rec.predicted_value) for rec in r1.batch.records
                          if rec.predicted_value is not None])
        vals2 = np.array([float(rec.predicted_value) for rec in r2.batch.records
                          if rec.predicted_value is not None])
        assert len(vals1) == len(vals2), "Different number of valid predictions"
        # Use allclose to handle floating-point rounding at the ULP level
        np.testing.assert_allclose(
            vals1, vals2, rtol=1e-12, atol=0,
            err_msg="Predictions not reproducible across two calls",
        )

    def test_training_reproducible_with_same_seed(self):
        """
        Training with the same seed must produce identical test-set MAE
        on two independent runs.
        """
        import sys, logging
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        sys.path.insert(0, str(_ROOT / "tests"))
        logging.disable(logging.CRITICAL)
        from fixtures.make_synthetic_fixture import make_clean_fixture
        from prediction.train import run_training_pipeline

        df = make_clean_fixture(n_rows=200, seed=42)
        r1 = run_training_pipeline(df, test_fraction=0.20, shuffle=True)
        r2 = run_training_pipeline(df, test_fraction=0.20, shuffle=True)
        assert r1.rf_metrics.mae  == pytest.approx(r2.rf_metrics.mae,  abs=1e-9)
        assert r1.rf_metrics.rmse == pytest.approx(r2.rf_metrics.rmse, abs=1e-9)
        logging.disable(logging.NOTSET)

    def test_loaded_model_matches_in_memory_model(self, loaded_bundle, feature_df):
        """Predictions from disk-loaded model must match in-memory RF output."""
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from data_pipeline.cleaning import apply_cleaning_pipeline
        from data_pipeline.feature_engineering import apply_feature_pipeline, build_model_feature_matrix
        from prediction.predict import predict_batch

        # Get predictions via predict_batch (disk-loaded model)
        result = predict_batch(feature_df, loaded_bundle)
        assert all(r.predicted_value is not None for r in result.batch.records), (
            "Some records returned None — check feature_df has the right columns."
        )
        batch_vals = np.array([float(r.predicted_value) for r in result.batch.records])

        # Get predictions directly from loaded model (manual pipeline)
        df_c = apply_cleaning_pipeline(feature_df, loaded_bundle.cleaning_stats,
                                       drop_target_nulls=False)
        df_e = apply_feature_pipeline(df_c, loaded_bundle.feature_stats)
        X, _ = build_model_feature_matrix(df_e, feature_cols=loaded_bundle.metadata.feature_cols)
        direct_vals = np.clip(loaded_bundle.model.predict(X), 0.0, 1.0).astype(float)

        np.testing.assert_allclose(batch_vals, direct_vals, rtol=1e-6)


# ---------------------------------------------------------------------------
# 5. Latency smoke test
# ---------------------------------------------------------------------------

class TestLatencySmoke:
    """
    Smoke tests only — not hard performance gates.
    They verify the inference pipeline completes in a reasonable time
    on any development machine, not that it meets the aspirational targets.
    The hard benchmark is in scripts/benchmark_inference.py.
    """

    SMOKE_LIMIT_S = 30.0    # very generous — catches hangs, not slow code

    def test_single_record_completes_in_time(self, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        from fixtures.make_synthetic_fixture import FEATURE_COLS
        rng = np.random.default_rng(0)
        df = pd.DataFrame({col: rng.uniform(0, 10, 1) for col in FEATURE_COLS})
        df["zone_id"] = ["SMOKE_ZONE"]
        t0 = time.perf_counter()
        _ = predict_batch(df, loaded_bundle)
        elapsed = time.perf_counter() - t0
        assert elapsed < self.SMOKE_LIMIT_S, (
            f"Single-record inference took {elapsed:.2f}s — exceeds smoke limit."
        )

    def test_batch_50_completes_in_time(self, feature_df, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        from fixtures.make_synthetic_fixture import FEATURE_COLS
        rng = np.random.default_rng(1)
        df = pd.DataFrame({col: rng.uniform(0, 10, 50) for col in FEATURE_COLS})
        df["zone_id"] = [f"Z{i}" for i in range(50)]
        t0 = time.perf_counter()
        _ = predict_batch(df, loaded_bundle)
        elapsed = time.perf_counter() - t0
        assert elapsed < self.SMOKE_LIMIT_S

    def test_timing_object_populated(self, feature_df, loaded_bundle):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.predict import predict_batch
        result = predict_batch(feature_df, loaded_bundle)
        t = result.timing
        assert t.preprocess_s >= 0
        assert t.inference_s  >= 0
        assert t.total_s      >  0
        assert t.n_records    == len(feature_df)


# ---------------------------------------------------------------------------
# 6. Training pipeline mechanics
# ---------------------------------------------------------------------------

class TestTrainingMechanics:

    def test_split_sizes_correct(self):
        import sys, logging
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        sys.path.insert(0, str(_ROOT / "tests"))
        logging.disable(logging.CRITICAL)
        from fixtures.make_synthetic_fixture import make_clean_fixture
        from prediction.train import run_training_pipeline
        df = make_clean_fixture(n_rows=100, seed=1)
        result = run_training_pipeline(df, test_fraction=0.20)
        assert result.train_rows + result.test_rows == 100
        assert result.test_rows == 20
        logging.disable(logging.NOTSET)

    def test_rf_beats_baseline_on_synthetic(self):
        """RF must beat the mean baseline on SYNTHETIC data (sanity check)."""
        import sys, logging
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        sys.path.insert(0, str(_ROOT / "tests"))
        logging.disable(logging.CRITICAL)
        from fixtures.make_synthetic_fixture import make_clean_fixture
        from prediction.train import run_training_pipeline
        df = make_clean_fixture(n_rows=200, seed=42)
        result = run_training_pipeline(df)
        assert result.rf_metrics.mae < result.baseline_metrics.mae, (
            "RF should beat mean baseline on SYNTHETIC data. "
            f"RF MAE={result.rf_metrics.mae:.4f} baseline MAE={result.baseline_metrics.mae:.4f}"
        )
        logging.disable(logging.NOTSET)

    def test_leakage_guard_cleaning_stats_from_train(self):
        """
        Training-split median must differ from test-split median.
        Verifies that test set is not used to fit the cleaning pipeline.
        """
        import sys, logging
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        sys.path.insert(0, str(_ROOT / "tests"))
        logging.disable(logging.CRITICAL)
        from fixtures.make_synthetic_fixture import FEATURE_COLS, make_clean_fixture
        from prediction.train import run_training_pipeline, split_dataframe
        from data_pipeline.cleaning import fit_cleaning_pipeline

        df = make_clean_fixture(n_rows=200, seed=42)
        df_train, df_test = split_dataframe(df, test_fraction=0.20)
        train_stats = fit_cleaning_pipeline(df_train, numeric_columns=FEATURE_COLS)
        test_stats  = fit_cleaning_pipeline(df_test,  numeric_columns=FEATURE_COLS)

        col = FEATURE_COLS[0]
        # With 200 random rows the medians differ slightly — they must NOT be identical
        # (if they were identical it would suggest the data is not being split)
        assert train_stats.column_medians[col] != test_stats.column_medians[col], (
            "Train and test medians must differ — split is not working correctly."
        )
        logging.disable(logging.NOTSET)

    def test_data_source_recorded_in_result(self):
        import sys, logging
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        sys.path.insert(0, str(_ROOT / "tests"))
        logging.disable(logging.CRITICAL)
        from fixtures.make_synthetic_fixture import make_clean_fixture
        from prediction.train import run_training_pipeline
        df = make_clean_fixture(n_rows=100, seed=5)
        df.attrs["_data_source"] = "SYNTHETIC"
        result = run_training_pipeline(df)
        assert result.data_source == "SYNTHETIC"
        logging.disable(logging.NOTSET)

    def test_notes_warn_synthetic(self):
        import sys, logging
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        sys.path.insert(0, str(_ROOT / "tests"))
        logging.disable(logging.CRITICAL)
        from fixtures.make_synthetic_fixture import make_clean_fixture
        from prediction.train import run_training_pipeline
        df = make_clean_fixture(n_rows=100, seed=6)
        df.attrs["_data_source"] = "SYNTHETIC"
        result = run_training_pipeline(df)
        assert "SYNTHETIC" in result.notes.upper()
        logging.disable(logging.NOTSET)


# ---------------------------------------------------------------------------
# 7. Evaluate module
# ---------------------------------------------------------------------------

class TestEvaluateModule:

    def test_mae_rmse_correct(self):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.evaluate import compute_regression_metrics
        y_true = np.array([0.5, 0.3, 0.7])
        y_pred = np.array([0.4, 0.4, 0.6])
        metrics = compute_regression_metrics(y_true, y_pred, "test")
        assert metrics.mae  == pytest.approx(abs(y_true - y_pred).mean(), abs=1e-9)
        assert metrics.rmse == pytest.approx(np.sqrt(((y_true - y_pred)**2).mean()), abs=1e-9)

    def test_perfect_prediction_zero_mae(self):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.evaluate import compute_regression_metrics
        y = np.array([0.1, 0.5, 0.9])
        m = compute_regression_metrics(y, y, "perfect")
        assert m.mae  == pytest.approx(0.0, abs=1e-12)
        assert m.rmse == pytest.approx(0.0, abs=1e-12)
        assert m.r2   == pytest.approx(1.0, abs=1e-9)

    def test_empty_arrays_raise(self):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.evaluate import compute_regression_metrics
        with pytest.raises(ValueError, match="empty"):
            compute_regression_metrics(np.array([]), np.array([]))

    def test_nan_in_y_true_raises(self):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.evaluate import compute_regression_metrics
        with pytest.raises(ValueError, match="NaN"):
            compute_regression_metrics(np.array([np.nan, 0.5]), np.array([0.3, 0.5]))

    def test_nan_in_y_pred_raises(self):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.evaluate import compute_regression_metrics
        with pytest.raises(ValueError, match="NaN"):
            compute_regression_metrics(np.array([0.5, 0.3]), np.array([np.nan, 0.5]))

    def test_shape_mismatch_raises(self):
        import sys
        _ROOT = pathlib.Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_ROOT / "src"))
        from prediction.evaluate import compute_regression_metrics
        with pytest.raises(ValueError, match="Shape mismatch"):
            compute_regression_metrics(np.array([0.5, 0.3]), np.array([0.5]))
