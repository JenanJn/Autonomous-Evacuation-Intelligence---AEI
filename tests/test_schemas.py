"""
Tests for src/integration/schemas.py
======================================
Validates the AEI ↔ GIS integration contract.
All fixtures are SYNTHETIC.
"""

from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from integration.schemas import (
    CONTRACT_VERSION,
    HazardPredictionBatch,
    HazardPredictionRecord,
    PredictionStatus,
    RiskCategory,
    RiskOutputBatch,
    RiskOutputRecord,
    RiskStatus,
    make_unavailable_prediction,
    make_unavailable_risk,
    make_valid_prediction,
    make_valid_risk,
)


# ---------------------------------------------------------------------------
# HazardPredictionRecord — valid inputs
# ---------------------------------------------------------------------------

class TestHazardPredictionRecordValid:
    def test_factory_produces_valid_record(self):
        r = make_valid_prediction()
        assert r.prediction_status == PredictionStatus.OK
        assert r.predicted_value == pytest.approx(0.72)

    def test_different_zone_ids(self):
        for zone in ("Z001", "ZONE_A", "district-12"):
            r = make_valid_prediction(zone_id=zone)
            assert r.zone_id == zone

    def test_to_gis_dict_is_serialisable(self):
        r = make_valid_prediction()
        d = r.to_gis_dict()
        # Must be JSON serialisable (GIS module expects JSON)
        serialised = json.dumps(d)
        recovered = json.loads(serialised)
        assert recovered["zone_id"] == r.zone_id
        assert recovered["predicted_value"] == pytest.approx(0.72)

    def test_contract_version_present(self):
        r = make_valid_prediction()
        assert r.contract_version == CONTRACT_VERSION

    def test_all_prediction_status_values_accepted(self):
        for status in PredictionStatus:
            if status == PredictionStatus.OK:
                r = HazardPredictionRecord(
                    zone_id="Z1",
                    prediction_time="2024-01-01T00:00:00Z",
                    target_name="FloodProbability",
                    predicted_value=0.5,
                    target_unit="dimensionless_0_to_1",
                    forecast_horizon="static_snapshot",
                    model_version="0.1.0",
                    prediction_status=status,
                )
            else:
                r = make_unavailable_prediction("Z1", reason=status)
            assert r.prediction_status == status


# ---------------------------------------------------------------------------
# HazardPredictionRecord — invalid inputs
# ---------------------------------------------------------------------------

class TestHazardPredictionRecordInvalid:
    def test_empty_zone_id_raises(self):
        with pytest.raises(ValidationError):
            HazardPredictionRecord(
                zone_id="",  # empty string — not allowed
                prediction_time="2024-01-01T00:00:00Z",
                target_name="FloodProbability",
                predicted_value=0.5,
                target_unit="dimensionless_0_to_1",
                forecast_horizon="static_snapshot",
                model_version="0.1.0",
            )

    def test_nan_predicted_value_raises(self):
        with pytest.raises(ValidationError, match="finite"):
            HazardPredictionRecord(
                zone_id="Z1",
                prediction_time="2024-01-01T00:00:00Z",
                target_name="FloodProbability",
                predicted_value=float("nan"),
                target_unit="dimensionless_0_to_1",
                forecast_horizon="static_snapshot",
                model_version="0.1.0",
                prediction_status=PredictionStatus.OK,
            )

    def test_inf_predicted_value_raises(self):
        with pytest.raises(ValidationError, match="finite"):
            HazardPredictionRecord(
                zone_id="Z1",
                prediction_time="2024-01-01T00:00:00Z",
                target_name="FloodProbability",
                predicted_value=float("inf"),
                target_unit="dimensionless_0_to_1",
                forecast_horizon="static_snapshot",
                model_version="0.1.0",
                prediction_status=PredictionStatus.OK,
            )

    def test_ok_status_with_none_value_raises(self):
        with pytest.raises(ValidationError, match="predicted_value must be set"):
            HazardPredictionRecord(
                zone_id="Z1",
                prediction_time="2024-01-01T00:00:00Z",
                target_name="FloodProbability",
                predicted_value=None,          # None not allowed when status=OK
                target_unit="dimensionless_0_to_1",
                forecast_horizon="static_snapshot",
                model_version="0.1.0",
                prediction_status=PredictionStatus.OK,
            )

    def test_bad_model_version_raises(self):
        with pytest.raises(ValidationError):
            HazardPredictionRecord(
                zone_id="Z1",
                prediction_time="2024-01-01T00:00:00Z",
                target_name="FloodProbability",
                predicted_value=0.5,
                target_unit="dimensionless_0_to_1",
                forecast_horizon="static_snapshot",
                model_version="v1.0",          # must be X.Y.Z pattern
                prediction_status=PredictionStatus.OK,
            )

    def test_unavailable_record_has_none_value(self):
        r = make_unavailable_prediction("Z1", PredictionStatus.NO_DATA)
        assert r.predicted_value is None
        assert r.prediction_status == PredictionStatus.NO_DATA


# ---------------------------------------------------------------------------
# RiskOutputRecord — valid inputs
# ---------------------------------------------------------------------------

class TestRiskOutputRecordValid:
    def test_factory_produces_valid_record(self):
        r = make_valid_risk()
        assert r.risk_status == RiskStatus.OK
        assert 0.0 <= r.risk_score <= 1.0

    def test_high_score_maps_to_high_category(self):
        r = make_valid_risk(score=0.8)
        assert r.risk_category in (RiskCategory.HIGH, RiskCategory.CRITICAL)

    def test_moderate_score_maps_correctly(self):
        r = make_valid_risk(score=0.4)
        assert r.risk_category in (RiskCategory.LOW, RiskCategory.MODERATE)

    def test_to_gis_dict_is_serialisable(self):
        r = make_valid_risk()
        d = r.to_gis_dict()
        serialised = json.dumps(d)
        recovered = json.loads(serialised)
        assert recovered["zone_id"] == r.zone_id

    def test_contributing_factors_preserved(self):
        r = make_valid_risk()
        assert "FloodProbability" in r.contributing_factors


# ---------------------------------------------------------------------------
# RiskOutputRecord — invalid inputs
# ---------------------------------------------------------------------------

class TestRiskOutputRecordInvalid:
    def test_score_above_one_raises(self):
        with pytest.raises(ValidationError):
            RiskOutputRecord(
                zone_id="Z1",
                risk_score=1.5,   # above maximum
                risk_category=RiskCategory.HIGH,
                risk_status=RiskStatus.OK,
            )

    def test_negative_score_raises(self):
        with pytest.raises(ValidationError):
            RiskOutputRecord(
                zone_id="Z1",
                risk_score=-0.1,  # below minimum
                risk_category=RiskCategory.LOW,
                risk_status=RiskStatus.OK,
            )

    def test_ok_status_with_none_score_raises(self):
        with pytest.raises(ValidationError, match="risk_score must be set"):
            RiskOutputRecord(
                zone_id="Z1",
                risk_score=None,  # None not allowed when status=OK
                risk_category=RiskCategory.HIGH,
                risk_status=RiskStatus.OK,
            )

    def test_non_ok_status_must_have_unknown_category(self):
        with pytest.raises(ValidationError, match="risk_category must be UNKNOWN"):
            RiskOutputRecord(
                zone_id="Z1",
                risk_score=None,
                risk_category=RiskCategory.HIGH,  # should be UNKNOWN
                risk_status=RiskStatus.NO_DATA,
            )

    def test_unavailable_record_ok(self):
        r = make_unavailable_risk("Z1", RiskStatus.NO_DATA)
        assert r.risk_score is None
        assert r.risk_category == RiskCategory.UNKNOWN


# ---------------------------------------------------------------------------
# Batch wrappers
# ---------------------------------------------------------------------------

class TestBatchWrappers:
    def test_hazard_batch_serialises(self):
        batch = HazardPredictionBatch(
            records=[make_valid_prediction("Z1"), make_valid_prediction("Z2")],
            generated_at="2024-06-01T12:00:00Z",
        )
        records = batch.to_csv_records()
        assert len(records) == 2
        assert all("zone_id" in r for r in records)

    def test_risk_batch_serialises(self):
        batch = RiskOutputBatch(
            records=[make_valid_risk("Z1"), make_valid_risk("Z2")],
            generated_at="2024-06-01T12:00:00Z",
        )
        records = batch.to_csv_records()
        assert len(records) == 2
        assert all("risk_score" in r for r in records)

    def test_empty_batch_allowed(self):
        batch = HazardPredictionBatch(
            records=[],
            generated_at="2024-06-01T12:00:00Z",
        )
        assert batch.to_csv_records() == []

    def test_batch_contract_version_matches(self):
        batch = HazardPredictionBatch(
            records=[],
            generated_at="2024-06-01T12:00:00Z",
        )
        assert batch.contract_version == CONTRACT_VERSION


# ---------------------------------------------------------------------------
# Missing / malformed inputs (integration boundary tests)
# ---------------------------------------------------------------------------

class TestMalformedInputs:
    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            HazardPredictionRecord(
                # zone_id is missing
                prediction_time="2024-01-01T00:00:00Z",
                target_name="FloodProbability",
                target_unit="dimensionless_0_to_1",
                forecast_horizon="static_snapshot",
                model_version="0.1.0",
            )

    def test_wrong_type_coerced_or_rejected(self):
        # Pydantic v2 coerces numeric strings to float
        r = HazardPredictionRecord(
            zone_id="Z1",
            prediction_time="2024-01-01T00:00:00Z",
            target_name="FloodProbability",
            predicted_value="0.5",   # string — pydantic v2 coerces to float
            target_unit="dimensionless_0_to_1",
            forecast_horizon="static_snapshot",
            model_version="0.1.0",
            prediction_status=PredictionStatus.OK,
        )
        assert r.predicted_value == pytest.approx(0.5)
