"""
Tests for src/risk_engine/scoring.py
======================================
All data is SYNTHETIC.  These tests verify scoring semantics, threshold
logic, error propagation and provenance labelling — NOT real-world accuracy.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from integration.schemas import (
    HazardPredictionRecord,
    PredictionStatus,
    RiskCategory,
    RiskStatus,
    make_valid_prediction,
    make_unavailable_prediction,
)
from risk_engine.scoring import (
    SCORING_METHOD_PROXY,
    SUPPORTED_TARGETS,
    CategoryThresholds,
    DEFAULT_THRESHOLDS,
    ScoredRiskRecord,
    extract_risk_records,
    score_batch,
    score_prediction,
    _compute_freshness,
    _map_prediction_status_to_risk_status,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_pred(
    zone_id: str = "Z1",
    predicted_value: float = 0.5,
    status: PredictionStatus = PredictionStatus.OK,
    target_name: str = "FloodProbability",
    target_unit: str = "dimensionless_0_to_1",
    model_version: str = "0.1.0",
    prediction_time: str = "2024-06-01T12:00:00Z",
    data_timestamp: str = "2024-06-01T06:00:00Z",
) -> HazardPredictionRecord:
    """Build a HazardPredictionRecord with controllable fields."""
    val = predicted_value if status == PredictionStatus.OK else None
    return HazardPredictionRecord(
        zone_id=zone_id,
        prediction_time=prediction_time,
        target_name=target_name,
        predicted_value=val,
        target_unit=target_unit,
        forecast_horizon="static_snapshot",
        model_version=model_version,
        data_timestamp=data_timestamp,
        prediction_status=status,
    )


# ---------------------------------------------------------------------------
# A. CategoryThresholds
# ---------------------------------------------------------------------------

class TestCategoryThresholds:
    def test_default_thresholds_values(self):
        t = DEFAULT_THRESHOLDS
        assert t.low_max == 0.25
        assert t.moderate_max == 0.50
        assert t.high_max == 0.75

    def test_custom_thresholds_stored(self):
        t = CategoryThresholds(low_max=0.1, moderate_max=0.4, high_max=0.8)
        assert t.low_max == 0.1
        assert t.moderate_max == 0.4
        assert t.high_max == 0.8

    def test_invalid_thresholds_raises(self):
        with pytest.raises(ValueError, match="must satisfy"):
            CategoryThresholds(low_max=0.5, moderate_max=0.3, high_max=0.75)

    def test_equal_thresholds_allowed(self):
        # Degenerate but not invalid: low=moderate=high=0.5
        t = CategoryThresholds(low_max=0.5, moderate_max=0.5, high_max=0.5)
        assert t.categorise(0.49) == RiskCategory.LOW
        assert t.categorise(0.50) == RiskCategory.CRITICAL

    def test_zero_thresholds_raises(self):
        with pytest.raises(ValueError):
            CategoryThresholds(low_max=-0.01, moderate_max=0.5, high_max=0.75)

    def test_above_one_raises(self):
        with pytest.raises(ValueError):
            CategoryThresholds(low_max=0.25, moderate_max=0.5, high_max=1.1)

    # Boundary values with DEFAULT_THRESHOLDS
    # low_max=0.25, moderate_max=0.50, high_max=0.75

    def test_score_zero_is_low(self):
        assert DEFAULT_THRESHOLDS.categorise(0.0) == RiskCategory.LOW

    def test_score_just_below_low_max_is_low(self):
        assert DEFAULT_THRESHOLDS.categorise(0.2499) == RiskCategory.LOW

    def test_score_at_low_max_is_moderate(self):
        # score < low_max → LOW; score >= low_max and < moderate_max → MODERATE
        assert DEFAULT_THRESHOLDS.categorise(0.25) == RiskCategory.MODERATE

    def test_score_just_below_moderate_max_is_moderate(self):
        assert DEFAULT_THRESHOLDS.categorise(0.4999) == RiskCategory.MODERATE

    def test_score_at_moderate_max_is_high(self):
        assert DEFAULT_THRESHOLDS.categorise(0.50) == RiskCategory.HIGH

    def test_score_just_below_high_max_is_high(self):
        assert DEFAULT_THRESHOLDS.categorise(0.7499) == RiskCategory.HIGH

    def test_score_at_high_max_is_critical(self):
        assert DEFAULT_THRESHOLDS.categorise(0.75) == RiskCategory.CRITICAL

    def test_score_one_is_critical(self):
        assert DEFAULT_THRESHOLDS.categorise(1.0) == RiskCategory.CRITICAL

    def test_custom_thresholds_categorise(self):
        t = CategoryThresholds(low_max=0.1, moderate_max=0.3, high_max=0.6)
        assert t.categorise(0.09)  == RiskCategory.LOW
        assert t.categorise(0.10)  == RiskCategory.MODERATE
        assert t.categorise(0.29)  == RiskCategory.MODERATE
        assert t.categorise(0.30)  == RiskCategory.HIGH
        assert t.categorise(0.60)  == RiskCategory.CRITICAL
        assert t.categorise(1.00)  == RiskCategory.CRITICAL


# ---------------------------------------------------------------------------
# B. score_prediction — successful scoring
# ---------------------------------------------------------------------------

class TestScorePredictionSuccess:
    def test_returns_scored_risk_record(self):
        result = score_prediction(_make_pred(predicted_value=0.4))
        assert isinstance(result, ScoredRiskRecord)

    def test_risk_status_ok_for_ok_prediction(self):
        r = score_prediction(_make_pred(predicted_value=0.4))
        assert r.risk_record.risk_status == RiskStatus.OK

    def test_risk_score_equals_predicted_value(self):
        r = score_prediction(_make_pred(predicted_value=0.4))
        assert r.risk_record.risk_score == pytest.approx(0.4)

    def test_scoring_method_is_proxy(self):
        r = score_prediction(_make_pred(predicted_value=0.4))
        assert r.scoring_method == SCORING_METHOD_PROXY

    def test_source_predicted_value_preserved(self):
        r = score_prediction(_make_pred(predicted_value=0.37))
        assert r.source_predicted_value == pytest.approx(0.37)

    def test_source_model_version_preserved(self):
        r = score_prediction(_make_pred(predicted_value=0.5, model_version="1.2.3"))
        assert r.source_model_version == "1.2.3"

    def test_source_target_name_preserved(self):
        r = score_prediction(_make_pred(predicted_value=0.5))
        assert r.source_target_name == "FloodProbability"

    def test_contributing_factors_present(self):
        r = score_prediction(_make_pred(predicted_value=0.5))
        assert len(r.risk_record.contributing_factors) > 0

    def test_scoring_note_mentions_proxy(self):
        r = score_prediction(_make_pred(predicted_value=0.5))
        assert "proxy" in r.scoring_note.lower() or "uncalibrated" in r.scoring_note.lower()

    def test_scoring_note_mentions_not_calibrated(self):
        r = score_prediction(_make_pred(predicted_value=0.5))
        note = r.scoring_note.upper()
        assert "UNCALIBRATED" in note or "NOT" in note

    def test_zone_id_propagated(self):
        r = score_prediction(_make_pred(zone_id="ZONE_XYZ", predicted_value=0.5))
        assert r.risk_record.zone_id == "ZONE_XYZ"

    def test_score_zero_produces_low(self):
        r = score_prediction(_make_pred(predicted_value=0.0))
        assert r.risk_record.risk_category == RiskCategory.LOW

    def test_score_one_produces_critical(self):
        r = score_prediction(_make_pred(predicted_value=1.0))
        assert r.risk_record.risk_category == RiskCategory.CRITICAL

    def test_score_at_low_boundary(self):
        r = score_prediction(_make_pred(predicted_value=0.25))
        assert r.risk_record.risk_category == RiskCategory.MODERATE

    def test_score_at_moderate_boundary(self):
        r = score_prediction(_make_pred(predicted_value=0.50))
        assert r.risk_record.risk_category == RiskCategory.HIGH

    def test_score_at_high_boundary(self):
        r = score_prediction(_make_pred(predicted_value=0.75))
        assert r.risk_record.risk_category == RiskCategory.CRITICAL

    def test_custom_thresholds_respected(self):
        t = CategoryThresholds(low_max=0.1, moderate_max=0.3, high_max=0.6)
        r = score_prediction(_make_pred(predicted_value=0.05), thresholds=t)
        assert r.risk_record.risk_category == RiskCategory.LOW
        r2 = score_prediction(_make_pred(predicted_value=0.55), thresholds=t)
        assert r2.risk_record.risk_category == RiskCategory.HIGH

    def test_data_freshness_computed(self):
        # data_timestamp 6h before prediction_time → PT21600S
        r = score_prediction(_make_pred(
            predicted_value=0.5,
            prediction_time="2024-06-01T12:00:00Z",
            data_timestamp="2024-06-01T06:00:00Z",
        ))
        assert r.risk_record.data_freshness == "PT21600S"

    def test_freshness_none_when_no_data_timestamp(self):
        pred = HazardPredictionRecord(
            zone_id="Z1",
            prediction_time="2024-06-01T12:00:00Z",
            target_name="FloodProbability",
            predicted_value=0.5,
            target_unit="dimensionless_0_to_1",
            forecast_horizon="static_snapshot",
            model_version="0.1.0",
            data_timestamp=None,
            prediction_status=PredictionStatus.OK,
        )
        r = score_prediction(pred)
        assert r.risk_record.data_freshness is None

    def test_deterministic_same_input_same_output(self):
        pred = _make_pred(predicted_value=0.63)
        r1 = score_prediction(pred)
        r2 = score_prediction(pred)
        assert r1.risk_record.risk_score == r2.risk_record.risk_score
        assert r1.risk_record.risk_category == r2.risk_record.risk_category
        assert r1.scoring_method == r2.scoring_method


# ---------------------------------------------------------------------------
# C. score_prediction — error cases: upstream non-OK status
# ---------------------------------------------------------------------------

class TestScorePredictionNonOkStatus:
    def test_no_data_maps_to_risk_no_data(self):
        pred = make_unavailable_prediction("Z1", PredictionStatus.NO_DATA)
        r = score_prediction(pred)
        assert r.risk_record.risk_status == RiskStatus.NO_DATA
        assert r.risk_record.risk_score is None

    def test_stale_data_maps_to_risk_stale_data(self):
        pred = make_unavailable_prediction("Z1", PredictionStatus.STALE_DATA)
        r = score_prediction(pred)
        assert r.risk_record.risk_status == RiskStatus.STALE_DATA
        assert r.risk_record.risk_score is None

    def test_model_error_maps_to_scoring_error(self):
        pred = make_unavailable_prediction("Z1", PredictionStatus.MODEL_ERROR)
        r = score_prediction(pred)
        assert r.risk_record.risk_status == RiskStatus.SCORING_ERROR
        assert r.risk_record.risk_score is None

    def test_invalid_input_maps_to_invalid_input(self):
        pred = make_unavailable_prediction("Z1", PredictionStatus.INVALID_INPUT)
        r = score_prediction(pred)
        assert r.risk_record.risk_status == RiskStatus.INVALID_INPUT
        assert r.risk_record.risk_score is None

    def test_non_ok_category_is_unknown(self):
        pred = make_unavailable_prediction("Z1", PredictionStatus.NO_DATA)
        r = score_prediction(pred)
        assert r.risk_record.risk_category == RiskCategory.UNKNOWN

    def test_stale_data_never_becomes_low_risk(self):
        """STALE_DATA must produce risk_status=STALE_DATA, not LOW or any score."""
        pred = make_unavailable_prediction("Z1", PredictionStatus.STALE_DATA)
        r = score_prediction(pred)
        assert r.risk_record.risk_score is None
        assert r.risk_record.risk_category == RiskCategory.UNKNOWN
        assert r.risk_record.risk_status == RiskStatus.STALE_DATA

    def test_no_data_never_becomes_low_risk(self):
        pred = make_unavailable_prediction("Z1", PredictionStatus.NO_DATA)
        r = score_prediction(pred)
        assert r.risk_record.risk_score is None
        assert r.risk_record.risk_category != RiskCategory.LOW

    def test_scoring_method_not_scored_for_non_ok(self):
        pred = make_unavailable_prediction("Z1", PredictionStatus.NO_DATA)
        r = score_prediction(pred)
        assert r.scoring_method == "not_scored"

    def test_note_explains_non_ok_status(self):
        pred = make_unavailable_prediction("Z1", PredictionStatus.NO_DATA)
        r = score_prediction(pred)
        assert "NO_DATA" in r.scoring_note or "not" in r.scoring_note.lower()


# ---------------------------------------------------------------------------
# D. score_prediction — unsupported target
# ---------------------------------------------------------------------------

class TestScorePredictionUnsupportedTarget:
    def test_unsupported_target_returns_scoring_error(self):
        # WaterLevelM is listed in predict.py but has no validated scoring formula
        pred = HazardPredictionRecord(
            zone_id="Z1",
            prediction_time="2024-06-01T12:00:00Z",
            target_name="WaterLevelM",
            predicted_value=2.5,
            target_unit="metres_above_sea_level",
            forecast_horizon="static_snapshot",
            model_version="0.1.0",
            prediction_status=PredictionStatus.OK,
        )
        r = score_prediction(pred)
        assert r.risk_record.risk_status == RiskStatus.SCORING_ERROR
        assert r.risk_record.risk_score is None
        assert r.risk_record.risk_category == RiskCategory.UNKNOWN

    def test_unsupported_target_note_explains(self):
        pred = HazardPredictionRecord(
            zone_id="Z1",
            prediction_time="2024-06-01T12:00:00Z",
            target_name="FloodDepthM",
            predicted_value=1.0,
            target_unit="metres",
            forecast_horizon="static_snapshot",
            model_version="0.1.0",
            prediction_status=PredictionStatus.OK,
        )
        r = score_prediction(pred)
        assert "FloodDepthM" in r.scoring_note or "not in SUPPORTED" in r.scoring_note

    def test_unsupported_target_scoring_method_not_scored(self):
        pred = HazardPredictionRecord(
            zone_id="Z1",
            prediction_time="2024-06-01T12:00:00Z",
            target_name="UNKNOWN_TARGET",
            predicted_value=0.5,
            target_unit="unknown",
            forecast_horizon="static_snapshot",
            model_version="0.1.0",
            prediction_status=PredictionStatus.OK,
        )
        r = score_prediction(pred)
        assert r.scoring_method == "not_scored"

    def test_supported_targets_set_contains_flood_probability(self):
        assert "FloodProbability" in SUPPORTED_TARGETS


# ---------------------------------------------------------------------------
# E. score_prediction — out-of-range / non-finite values
# ---------------------------------------------------------------------------

class TestScorePredictionInvalidValues:
    def _force_bad_value(self, value: float) -> HazardPredictionRecord:
        """Build a record that bypasses Pydantic's finite check for testing."""
        # We bypass the validator via model_construct to test scoring.py's own guard.
        return HazardPredictionRecord.model_construct(
            zone_id="Z1",
            prediction_time="2024-06-01T12:00:00Z",
            target_name="FloodProbability",
            predicted_value=value,
            target_unit="dimensionless_0_to_1",
            forecast_horizon="static_snapshot",
            model_version="0.1.0",
            data_timestamp=None,
            prediction_status=PredictionStatus.OK,
            contract_version="0.1.0",
        )

    def test_negative_value_returns_scoring_error(self):
        pred = self._force_bad_value(-0.01)
        r = score_prediction(pred)
        assert r.risk_record.risk_status == RiskStatus.SCORING_ERROR
        assert r.risk_record.risk_score is None

    def test_above_one_value_returns_scoring_error(self):
        pred = self._force_bad_value(1.0001)
        r = score_prediction(pred)
        assert r.risk_record.risk_status == RiskStatus.SCORING_ERROR

    def test_note_mentions_out_of_range(self):
        pred = self._force_bad_value(2.0)
        r = score_prediction(pred)
        assert "outside" in r.scoring_note or "0" in r.scoring_note

    def test_boundary_zero_is_valid(self):
        r = score_prediction(_make_pred(predicted_value=0.0))
        assert r.risk_record.risk_status == RiskStatus.OK

    def test_boundary_one_is_valid(self):
        r = score_prediction(_make_pred(predicted_value=1.0))
        assert r.risk_record.risk_status == RiskStatus.OK


# ---------------------------------------------------------------------------
# F. score_batch
# ---------------------------------------------------------------------------

class TestScoreBatch:
    def test_returns_one_record_per_input(self):
        preds = [_make_pred(zone_id=f"Z{i}", predicted_value=0.3) for i in range(5)]
        results = score_batch(preds)
        assert len(results) == 5

    def test_preserves_order(self):
        preds = [_make_pred(zone_id=f"Z{i}", predicted_value=i*0.1) for i in range(5)]
        results = score_batch(preds)
        for i, r in enumerate(results):
            assert r.risk_record.zone_id == f"Z{i}"

    def test_empty_batch_returns_empty(self):
        assert score_batch([]) == []

    def test_mixed_ok_and_non_ok(self):
        preds = [
            _make_pred(zone_id="OK", predicted_value=0.4),
            make_unavailable_prediction("STALE", PredictionStatus.STALE_DATA),
            _make_pred(zone_id="OK2", predicted_value=0.7),
        ]
        results = score_batch(preds)
        assert results[0].risk_record.risk_status == RiskStatus.OK
        assert results[1].risk_record.risk_status == RiskStatus.STALE_DATA
        assert results[2].risk_record.risk_status == RiskStatus.OK

    def test_batch_with_unsupported_target(self):
        preds = [
            _make_pred(zone_id="OK", predicted_value=0.5),
            HazardPredictionRecord(
                zone_id="BAD", prediction_time="2024-01-01T00:00:00Z",
                target_name="WaterLevelM", predicted_value=3.0,
                target_unit="metres_above_sea_level",
                forecast_horizon="static_snapshot", model_version="0.1.0",
                prediction_status=PredictionStatus.OK,
            ),
        ]
        results = score_batch(preds)
        assert results[0].risk_record.risk_status == RiskStatus.OK
        assert results[1].risk_record.risk_status == RiskStatus.SCORING_ERROR

    def test_custom_thresholds_applied_to_all(self):
        t = CategoryThresholds(low_max=0.1, moderate_max=0.3, high_max=0.6)
        preds = [
            _make_pred(zone_id="A", predicted_value=0.05),  # LOW
            _make_pred(zone_id="B", predicted_value=0.20),  # MODERATE
            _make_pred(zone_id="C", predicted_value=0.70),  # CRITICAL
        ]
        results = score_batch(preds, thresholds=t)
        assert results[0].risk_record.risk_category == RiskCategory.LOW
        assert results[1].risk_record.risk_category == RiskCategory.MODERATE
        assert results[2].risk_record.risk_category == RiskCategory.CRITICAL


# ---------------------------------------------------------------------------
# G. extract_risk_records
# ---------------------------------------------------------------------------

class TestExtractRiskRecords:
    def test_returns_list_of_risk_output_records(self):
        from integration.schemas import RiskOutputRecord
        preds = [_make_pred(zone_id=f"Z{i}", predicted_value=0.4) for i in range(3)]
        scored = score_batch(preds)
        records = extract_risk_records(scored)
        assert len(records) == 3
        for r in records:
            assert isinstance(r, RiskOutputRecord)

    def test_zone_ids_preserved(self):
        preds = [_make_pred(zone_id=f"ZONE_{i}", predicted_value=0.4) for i in range(4)]
        scored = score_batch(preds)
        records = extract_risk_records(scored)
        assert [r.zone_id for r in records] == [f"ZONE_{i}" for i in range(4)]

    def test_empty_input_returns_empty(self):
        assert extract_risk_records([]) == []


# ---------------------------------------------------------------------------
# H. _compute_freshness helper
# ---------------------------------------------------------------------------

class TestComputeFreshness:
    def test_six_hour_gap_produces_correct_duration(self):
        pred = _make_pred(
            prediction_time="2024-06-01T12:00:00Z",
            data_timestamp="2024-06-01T06:00:00Z",
        )
        assert _compute_freshness(pred) == "PT21600S"

    def test_zero_gap_produces_pt0s(self):
        pred = _make_pred(
            prediction_time="2024-06-01T12:00:00Z",
            data_timestamp="2024-06-01T12:00:00Z",
        )
        assert _compute_freshness(pred) == "PT0S"

    def test_missing_data_timestamp_returns_none(self):
        pred = HazardPredictionRecord(
            zone_id="Z1", prediction_time="2024-06-01T12:00:00Z",
            target_name="FloodProbability", predicted_value=0.5,
            target_unit="dimensionless_0_to_1", forecast_horizon="static_snapshot",
            model_version="0.1.0", data_timestamp=None,
            prediction_status=PredictionStatus.OK,
        )
        assert _compute_freshness(pred) is None

    def test_negative_gap_clamped_to_zero(self):
        # data_timestamp AFTER prediction_time — unusual, should return PT0S
        pred = _make_pred(
            prediction_time="2024-06-01T06:00:00Z",
            data_timestamp="2024-06-01T12:00:00Z",
        )
        assert _compute_freshness(pred) == "PT0S"

    def test_unparseable_timestamp_returns_none(self):
        pred = HazardPredictionRecord(
            zone_id="Z1", prediction_time="not-a-timestamp",
            target_name="FloodProbability", predicted_value=0.5,
            target_unit="dimensionless_0_to_1", forecast_horizon="static_snapshot",
            model_version="0.1.0", data_timestamp="2024-06-01T06:00:00Z",
            prediction_status=PredictionStatus.OK,
        )
        assert _compute_freshness(pred) is None


# ---------------------------------------------------------------------------
# I. Status mapping helper
# ---------------------------------------------------------------------------

class TestMapPredictionStatusToRiskStatus:
    def test_no_data_maps_correctly(self):
        assert _map_prediction_status_to_risk_status(
            PredictionStatus.NO_DATA) == RiskStatus.NO_DATA

    def test_stale_data_maps_correctly(self):
        assert _map_prediction_status_to_risk_status(
            PredictionStatus.STALE_DATA) == RiskStatus.STALE_DATA

    def test_model_error_maps_to_scoring_error(self):
        assert _map_prediction_status_to_risk_status(
            PredictionStatus.MODEL_ERROR) == RiskStatus.SCORING_ERROR

    def test_invalid_input_maps_correctly(self):
        assert _map_prediction_status_to_risk_status(
            PredictionStatus.INVALID_INPUT) == RiskStatus.INVALID_INPUT


# ---------------------------------------------------------------------------
# J. Integration: score_batch output is valid RiskOutputRecord input
# ---------------------------------------------------------------------------

class TestScoredOutputSchemaCompatibility:
    def test_ok_records_pass_pydantic_validation(self):
        """RiskOutputRecord constructed by scorer must satisfy all Pydantic validators."""
        preds = [_make_pred(zone_id=f"Z{i}", predicted_value=i * 0.1) for i in range(11)]
        scored = score_batch(preds)
        for sr in scored:
            rr = sr.risk_record
            # Re-validate by reconstructing from dict
            from integration.schemas import RiskOutputRecord
            reconstructed = RiskOutputRecord(**rr.model_dump())
            assert reconstructed.zone_id == rr.zone_id

    def test_non_ok_records_pass_pydantic_validation(self):
        preds = [
            make_unavailable_prediction("Z1", PredictionStatus.NO_DATA),
            make_unavailable_prediction("Z2", PredictionStatus.STALE_DATA),
            make_unavailable_prediction("Z3", PredictionStatus.MODEL_ERROR),
            make_unavailable_prediction("Z4", PredictionStatus.INVALID_INPUT),
        ]
        from integration.schemas import RiskOutputRecord
        scored = score_batch(preds)
        for sr in scored:
            rr = sr.risk_record
            reconstructed = RiskOutputRecord(**rr.model_dump())
            assert reconstructed.risk_score is None
            assert reconstructed.risk_category.value == "UNKNOWN"

    def test_to_gis_dict_is_json_serialisable(self):
        import json
        preds = [
            _make_pred(zone_id="Z1", predicted_value=0.6),
            make_unavailable_prediction("Z2", PredictionStatus.STALE_DATA),
        ]
        scored = score_batch(preds)
        for sr in scored:
            json.dumps(sr.risk_record.to_gis_dict())  # must not raise

    def test_contract_version_consistent(self):
        from integration.schemas import CONTRACT_VERSION
        r = score_prediction(_make_pred(predicted_value=0.5))
        assert r.risk_record.contract_version == CONTRACT_VERSION
