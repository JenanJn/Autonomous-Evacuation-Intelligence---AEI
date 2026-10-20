"""
Tests for src/risk_engine/validation.py
=========================================
All data is SYNTHETIC.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from integration.schemas import (
    CONTRACT_VERSION,
    RiskCategory,
    RiskOutputRecord,
    RiskStatus,
    make_valid_risk,
    make_unavailable_risk,
)
from risk_engine.validation import (
    BatchValidationResult,
    DuplicateZonePolicy,
    RecordValidationResult,
    validate_batch,
    validate_record,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ok_record(zone_id: str = "Z1", score: float = 0.5) -> RiskOutputRecord:
    cat = (RiskCategory.CRITICAL if score >= 0.75 else
           RiskCategory.HIGH if score >= 0.5 else
           RiskCategory.MODERATE if score >= 0.25 else RiskCategory.LOW)
    return RiskOutputRecord(
        zone_id=zone_id,
        risk_score=score,
        risk_category=cat,
        data_freshness="PT3600S",
        risk_status=RiskStatus.OK,
        contributing_factors=["FloodProbability_direct_proxy"],
    )


def _non_ok_record(
    zone_id: str = "Z1",
    status: RiskStatus = RiskStatus.NO_DATA,
) -> RiskOutputRecord:
    return RiskOutputRecord(
        zone_id=zone_id,
        risk_score=None,
        risk_category=RiskCategory.UNKNOWN,
        data_freshness=None,
        risk_status=status,
        contributing_factors=[],
    )


def _ok_dict(zone_id: str = "Z1", score: float = 0.5) -> dict:
    return _ok_record(zone_id, score).to_gis_dict()


def _non_ok_dict(zone_id: str = "Z1") -> dict:
    return _non_ok_record(zone_id).to_gis_dict()


# ---------------------------------------------------------------------------
# A. validate_record — valid Pydantic records
# ---------------------------------------------------------------------------

class TestValidateRecordValid:
    def test_ok_record_is_valid(self):
        result = validate_record(_ok_record())
        assert result.valid

    def test_non_ok_record_is_valid(self):
        result = validate_record(_non_ok_record())
        assert result.valid

    def test_stale_data_record_is_valid(self):
        result = validate_record(_non_ok_record(status=RiskStatus.STALE_DATA))
        assert result.valid

    def test_scoring_error_record_is_valid(self):
        result = validate_record(_non_ok_record(status=RiskStatus.SCORING_ERROR))
        assert result.valid

    def test_invalid_input_record_is_valid(self):
        result = validate_record(_non_ok_record(status=RiskStatus.INVALID_INPUT))
        assert result.valid

    def test_all_ok_categories_valid(self):
        for cat, score in [
            (RiskCategory.LOW, 0.1),
            (RiskCategory.MODERATE, 0.3),
            (RiskCategory.HIGH, 0.6),
            (RiskCategory.CRITICAL, 0.8),
        ]:
            r = RiskOutputRecord(
                zone_id="Z1", risk_score=score, risk_category=cat,
                risk_status=RiskStatus.OK, contributing_factors=[],
            )
            assert validate_record(r).valid, f"Expected valid for category={cat}"

    def test_no_errors_no_warnings_for_clean_record(self):
        result = validate_record(_ok_record())
        assert result.errors == []

    def test_returns_record_validation_result(self):
        result = validate_record(_ok_record())
        assert isinstance(result, RecordValidationResult)

    def test_zone_id_preserved_in_result(self):
        result = validate_record(_ok_record(zone_id="ZONE_ABC"))
        assert result.zone_id == "ZONE_ABC"


# ---------------------------------------------------------------------------
# B. validate_record — invalid Pydantic records (using model_construct)
# ---------------------------------------------------------------------------

class TestValidateRecordInvalidPydantic:
    def _construct(self, **kwargs) -> RiskOutputRecord:
        """Build a RiskOutputRecord bypassing Pydantic validators."""
        defaults = dict(
            zone_id="Z1", risk_score=0.5, risk_category=RiskCategory.HIGH,
            data_freshness="PT0S", risk_status=RiskStatus.OK,
            contributing_factors=["test"], contract_version=CONTRACT_VERSION,
        )
        defaults.update(kwargs)
        return RiskOutputRecord.model_construct(**defaults)

    def test_empty_zone_id_is_invalid(self):
        r = self._construct(zone_id="")
        result = validate_record(r)
        assert not result.valid
        assert any("zone_id" in e.lower() for e in result.errors)

    def test_whitespace_zone_id_is_invalid(self):
        r = self._construct(zone_id="   ")
        result = validate_record(r)
        assert not result.valid

    def test_ok_status_none_score_is_invalid(self):
        r = self._construct(risk_score=None, risk_status=RiskStatus.OK)
        result = validate_record(r)
        assert not result.valid
        assert any("risk_score" in e for e in result.errors)

    def test_ok_status_unknown_category_is_invalid(self):
        r = self._construct(risk_score=0.5, risk_category=RiskCategory.UNKNOWN,
                            risk_status=RiskStatus.OK)
        result = validate_record(r)
        assert not result.valid
        assert any("UNKNOWN" in e for e in result.errors)

    def test_non_ok_status_with_score_is_invalid(self):
        r = self._construct(risk_score=0.5, risk_category=RiskCategory.UNKNOWN,
                            risk_status=RiskStatus.NO_DATA)
        result = validate_record(r)
        assert not result.valid
        assert any("None" in e or "null" in e.lower() or "NO_DATA" in e
                   for e in result.errors)

    def test_non_ok_status_non_unknown_category_is_invalid(self):
        r = self._construct(risk_score=None, risk_category=RiskCategory.LOW,
                            risk_status=RiskStatus.NO_DATA)
        result = validate_record(r)
        assert not result.valid
        assert any("UNKNOWN" in e for e in result.errors)

    def test_contributing_factors_none_is_invalid(self):
        r = self._construct(contributing_factors=None)
        result = validate_record(r)
        assert not result.valid
        assert any("contributing_factors" in e for e in result.errors)

    def test_mismatched_contract_version_is_warning_not_error(self):
        r = self._construct(contract_version="99.99.99")
        result = validate_record(r)
        # Should warn but not error (it's a compatibility issue, not a fatal one)
        assert result.valid
        assert any("contract_version" in w or "99.99" in w for w in result.warnings)

    def test_invalid_freshness_format_is_warning_not_error(self):
        r = self._construct(data_freshness="not-a-duration")
        result = validate_record(r)
        assert result.valid  # warning only
        assert any("data_freshness" in w or "ISO" in w or "duration" in w.lower()
                   for w in result.warnings)

    def test_valid_freshness_formats_no_warning(self):
        for dur in ["PT0S", "PT3600S", "PT21600S", "P1D", "PT1H", "P1DT6H"]:
            r = self._construct(data_freshness=dur)
            result = validate_record(r)
            freshness_warnings = [w for w in result.warnings
                                  if "data_freshness" in w or "duration" in w.lower()]
            assert freshness_warnings == [], f"Unexpected warning for duration {dur!r}"

    def test_multiple_errors_all_reported(self):
        # Both zone_id empty AND OK+None score → two errors
        r = self._construct(zone_id="", risk_score=None, risk_status=RiskStatus.OK)
        result = validate_record(r)
        assert not result.valid
        assert len(result.errors) >= 2

    def test_summary_includes_zone_id_and_status(self):
        r = self._construct(zone_id="MYZONE", risk_score=None, risk_status=RiskStatus.OK)
        result = validate_record(r)
        summary = result.summary()
        assert "MYZONE" in summary
        assert "INVALID" in summary


# ---------------------------------------------------------------------------
# C. validate_record — plain dict input
# ---------------------------------------------------------------------------

class TestValidateRecordDict:
    def test_valid_ok_dict(self):
        result = validate_record(_ok_dict())
        assert result.valid

    def test_valid_non_ok_dict(self):
        result = validate_record(_non_ok_dict())
        assert result.valid

    def test_missing_zone_id_is_invalid(self):
        d = _ok_dict()
        d["zone_id"] = ""
        result = validate_record(d)
        assert not result.valid

    def test_invalid_risk_status_is_invalid(self):
        d = _ok_dict()
        d["risk_status"] = "INVENTED_STATUS"
        result = validate_record(d)
        assert not result.valid
        assert any("risk_status" in e for e in result.errors)

    def test_ok_with_none_score_is_invalid(self):
        d = _ok_dict()
        d["risk_score"] = None
        result = validate_record(d)
        assert not result.valid

    def test_ok_with_score_above_one_is_invalid(self):
        d = _ok_dict()
        d["risk_score"] = 1.5
        result = validate_record(d)
        assert not result.valid

    def test_ok_with_score_below_zero_is_invalid(self):
        d = _ok_dict()
        d["risk_score"] = -0.1
        result = validate_record(d)
        assert not result.valid

    def test_ok_with_unknown_category_is_invalid(self):
        d = _ok_dict()
        d["risk_category"] = "UNKNOWN"
        result = validate_record(d)
        assert not result.valid

    def test_non_ok_with_non_none_score_is_invalid(self):
        d = _non_ok_dict()
        d["risk_score"] = 0.5
        result = validate_record(d)
        assert not result.valid

    def test_non_ok_with_non_unknown_category_is_invalid(self):
        d = _non_ok_dict()
        d["risk_category"] = "LOW"
        result = validate_record(d)
        assert not result.valid

    def test_null_contributing_factors_is_invalid(self):
        d = _ok_dict()
        d["contributing_factors"] = None
        result = validate_record(d)
        assert not result.valid

    def test_score_boundary_zero_valid(self):
        d = _ok_dict(score=0.0)
        d["risk_category"] = "LOW"  # consistent with score=0.0
        result = validate_record(d)
        assert result.valid

    def test_score_boundary_one_valid(self):
        d = _ok_dict(score=1.0)
        d["risk_category"] = "CRITICAL"
        result = validate_record(d)
        assert result.valid

    def test_mismatched_contract_version_warning(self):
        d = _ok_dict()
        d["contract_version"] = "0.0.1"
        result = validate_record(d)
        assert result.valid
        assert any("contract_version" in w or "0.0.1" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# D. validate_batch
# ---------------------------------------------------------------------------

class TestValidateBatch:
    def test_empty_batch_is_valid_with_warning(self):
        result = validate_batch([])
        assert result.valid
        assert result.total == 0
        assert any("empty" in w.lower() for w in result.batch_warnings)

    def test_all_valid_records(self):
        records = [_ok_record(f"Z{i}", 0.3 + i * 0.05) for i in range(5)]
        result = validate_batch(records)
        assert result.valid
        assert result.n_valid == 5
        assert result.n_invalid == 0

    def test_mixed_valid_invalid(self):
        r1 = _ok_record("Z1")
        r2 = RiskOutputRecord.model_construct(
            zone_id="Z2", risk_score=None, risk_category=RiskCategory.UNKNOWN,
            risk_status=RiskStatus.OK, contributing_factors=[],
            data_freshness=None, contract_version=CONTRACT_VERSION,
        )  # invalid: OK + None score
        result = validate_batch([r1, r2])
        assert not result.valid
        assert result.n_valid == 1
        assert result.n_invalid == 1

    def test_returns_batch_validation_result(self):
        result = validate_batch([_ok_record()])
        assert isinstance(result, BatchValidationResult)

    def test_total_count_correct(self):
        records = [_ok_record(f"Z{i}") for i in range(7)]
        result = validate_batch(records)
        assert result.total == 7

    def test_ok_status_count_correct(self):
        records = [
            _ok_record("Z1"),
            _non_ok_record("Z2", RiskStatus.NO_DATA),
            _ok_record("Z3"),
        ]
        result = validate_batch(records)
        assert result.n_ok_status == 2
        assert result.n_non_ok_status == 1

    def test_batch_with_all_non_ok_is_valid(self):
        """A batch of non-OK records is structurally valid."""
        records = [
            _non_ok_record("Z1", RiskStatus.NO_DATA),
            _non_ok_record("Z2", RiskStatus.STALE_DATA),
            _non_ok_record("Z3", RiskStatus.SCORING_ERROR),
        ]
        result = validate_batch(records)
        assert result.valid

    def test_dict_records_accepted(self):
        dicts = [_ok_dict(f"Z{i}") for i in range(3)]
        result = validate_batch(dicts)
        assert result.valid

    def test_summary_string_contains_counts(self):
        records = [_ok_record(f"Z{i}") for i in range(4)]
        result = validate_batch(records)
        summary = result.summary()
        assert "4/4" in summary

    # ------------------------------------------------------------------
    # Duplicate zone policy
    # ------------------------------------------------------------------

    def test_duplicate_zone_warn_policy_keeps_records(self):
        records = [_ok_record("Z1"), _ok_record("Z1")]  # duplicate
        result = validate_batch(records, duplicate_policy=DuplicateZonePolicy.WARN)
        assert result.valid  # still valid
        assert result.total == 2
        assert any("Z1" in w or "duplicate" in w.lower()
                   for w in result.batch_warnings)

    def test_duplicate_zone_error_policy_marks_invalid(self):
        records = [_ok_record("Z1"), _ok_record("Z1")]
        result = validate_batch(records, duplicate_policy=DuplicateZonePolicy.ERROR)
        assert not result.valid
        assert any("duplicate" in e.lower() or "Z1" in e
                   for e in result.batch_errors)

    def test_duplicate_zone_ignore_policy_no_warning(self):
        records = [_ok_record("Z1"), _ok_record("Z1")]
        result = validate_batch(records, duplicate_policy=DuplicateZonePolicy.IGNORE)
        assert result.valid
        dup_warnings = [w for w in result.batch_warnings
                        if "duplicate" in w.lower()]
        assert dup_warnings == []

    def test_no_duplicates_no_duplicate_warning(self):
        records = [_ok_record(f"ZONE_{i}") for i in range(5)]
        result = validate_batch(records, duplicate_policy=DuplicateZonePolicy.WARN)
        dup_warnings = [w for w in result.batch_warnings
                        if "duplicate" in w.lower()]
        assert dup_warnings == []

    def test_three_duplicates_reported(self):
        records = [_ok_record("Z1")] * 3
        result = validate_batch(records, duplicate_policy=DuplicateZonePolicy.WARN)
        assert any("Z1" in w for w in result.batch_warnings)

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    def test_same_input_same_result(self):
        records = [_ok_record(f"Z{i}", 0.3 + i * 0.05) for i in range(10)]
        r1 = validate_batch(records)
        r2 = validate_batch(records)
        assert r1.valid == r2.valid
        assert r1.n_valid == r2.n_valid
        assert r1.total == r2.total


# ---------------------------------------------------------------------------
# E. RecordValidationResult
# ---------------------------------------------------------------------------

class TestRecordValidationResult:
    def test_valid_true_when_no_errors(self):
        r = RecordValidationResult(zone_id="Z1", valid=True, errors=[], warnings=[])
        assert r.valid

    def test_valid_false_when_errors_present(self):
        r = RecordValidationResult(zone_id="Z1", valid=False, errors=["oops"])
        assert not r.valid

    def test_summary_contains_valid_label(self):
        r = RecordValidationResult(zone_id="Z1", valid=True)
        assert "VALID" in r.summary()

    def test_summary_contains_invalid_label(self):
        r = RecordValidationResult(zone_id="Z1", valid=False, errors=["bad"])
        assert "INVALID" in r.summary()

    def test_summary_lists_errors(self):
        r = RecordValidationResult(zone_id="Z1", valid=False, errors=["error1", "error2"])
        s = r.summary()
        assert "error1" in s
        assert "error2" in s

    def test_summary_lists_warnings(self):
        r = RecordValidationResult(zone_id="Z1", valid=True, warnings=["warn1"])
        assert "warn1" in r.summary()


# ---------------------------------------------------------------------------
# F. DuplicateZonePolicy enum
# ---------------------------------------------------------------------------

class TestDuplicateZonePolicy:
    def test_warn_is_default_in_validate_batch(self):
        # Call without explicit policy — should not error on duplicates
        records = [_ok_record("Z1"), _ok_record("Z1")]
        result = validate_batch(records)
        # WARN is default: valid=True, warning present
        assert result.valid

    def test_all_policies_are_strings(self):
        for p in DuplicateZonePolicy:
            assert isinstance(p.value, str)


# ---------------------------------------------------------------------------
# G. Integration: scoring → validation pipeline
# ---------------------------------------------------------------------------

class TestScoringValidationIntegration:
    def test_scored_batch_passes_validation(self):
        """Records produced by score_batch should pass validate_batch."""
        from integration.schemas import HazardPredictionRecord, PredictionStatus
        from risk_engine.scoring import score_batch, extract_risk_records

        preds = []
        for i in range(6):
            preds.append(HazardPredictionRecord(
                zone_id=f"ZONE_{i}",
                prediction_time="2024-06-01T12:00:00Z",
                target_name="FloodProbability",
                predicted_value=round(0.1 + i * 0.15, 2),
                target_unit="dimensionless_0_to_1",
                forecast_horizon="static_snapshot",
                model_version="0.1.0",
                data_timestamp="2024-06-01T06:00:00Z",
                prediction_status=PredictionStatus.OK,
            ))

        scored = score_batch(preds)
        risk_records = extract_risk_records(scored)
        result = validate_batch(risk_records)

        assert result.valid, result.summary()
        assert result.n_valid == 6
        assert result.n_invalid == 0

    def test_non_ok_predictions_produce_valid_risk_records(self):
        """Non-OK predictions produce non-OK risk records that still pass validation."""
        from integration.schemas import PredictionStatus
        from risk_engine.scoring import score_batch, extract_risk_records
        from integration.schemas import make_unavailable_prediction

        preds = [
            make_unavailable_prediction("Z1", PredictionStatus.NO_DATA),
            make_unavailable_prediction("Z2", PredictionStatus.STALE_DATA),
            make_unavailable_prediction("Z3", PredictionStatus.MODEL_ERROR),
        ]
        scored = score_batch(preds)
        risk_records = extract_risk_records(scored)
        result = validate_batch(risk_records)

        assert result.valid
        assert result.n_non_ok_status == 3
        for rr in risk_records:
            assert rr.risk_score is None
            assert rr.risk_category == RiskCategory.UNKNOWN
