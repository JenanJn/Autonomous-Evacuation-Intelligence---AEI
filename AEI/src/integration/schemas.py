"""
AEI — Integration: Output Schemas
====================================
Defines the data contracts between the AEI Python AI component and the
GIS / routing engine built by the teammate.

These schemas are implemented with Pydantic v2 for automatic validation,
clear error messages, and easy JSON serialisation.

Design notes
------------
* Every output record carries a ``prediction_status`` or ``risk_status``
  field so the GIS engine can distinguish valid predictions from
  unavailable / error states without parsing the numeric fields.
* ``zone_id`` is the stable geographic identifier linking AEI outputs to
  road segments and shelter records in the GIS module.
* Units are explicit on every numeric field (documented in field descriptions
  and the ``target_unit`` field of HazardPredictionRecord).
* Timestamps use ISO-8601 strings so the GIS module can parse them without
  needing to share Python datetime objects.

Integration contract version
-----------------------------
CONTRACT_VERSION = "0.1.0"
Both components must agree on this version string.  Bump the minor version
for additive changes; bump the major version for breaking changes.

Refinement note
---------------
These schemas are PROPOSED for Milestone 1.  Review with teammate after
initial implementation.  The final schema may differ based on the GIS
module's requirements.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

CONTRACT_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Shared enumerations
# ---------------------------------------------------------------------------

class PredictionStatus(str, Enum):
    """Indicates whether a prediction was successfully produced."""
    OK            = "OK"             # Valid prediction available
    NO_DATA       = "NO_DATA"        # Required input data missing
    STALE_DATA    = "STALE_DATA"     # Data exists but is too old
    MODEL_ERROR   = "MODEL_ERROR"    # Inference failed
    INVALID_INPUT = "INVALID_INPUT"  # Input failed schema validation


class RiskStatus(str, Enum):
    """Indicates whether a risk score was successfully produced."""
    OK            = "OK"
    NO_DATA       = "NO_DATA"
    STALE_DATA    = "STALE_DATA"
    SCORING_ERROR = "SCORING_ERROR"
    INVALID_INPUT = "INVALID_INPUT"


class RiskCategory(str, Enum):
    """
    Ordinal risk category for human-readable display and routing cost
    assignment.

    WARNING: These categories are DECISION-SUPPORT outputs based on
    configurable thresholds.  They are NOT calibrated probabilities.
    Document thresholds in risk_engine/scoring.py.
    """
    LOW      = "LOW"
    MODERATE = "MODERATE"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN  = "UNKNOWN"


# ---------------------------------------------------------------------------
# Hazard prediction record
# ---------------------------------------------------------------------------

class HazardPredictionRecord(BaseModel):
    """
    One hazard prediction for a single geographic zone at a single point
    in time.

    This record is produced by the AEI prediction module and consumed by
    the GIS routing engine to assign hazard costs to road segments.

    Fields
    ------
    zone_id : str
        Stable identifier for the geographic zone.  Must match the zone
        identifier used in the GIS road-network layer.  No hardcoded city
        names.

    prediction_time : str
        ISO-8601 UTC timestamp when the prediction was generated.
        Format: "YYYY-MM-DDTHH:MM:SSZ"

    target_name : str
        Name of the predicted quantity (e.g. "FloodProbability",
        "WaterLevelM", "FloodDepthM").

    predicted_value : float or None
        The predicted value.  None when prediction_status != OK.

    target_unit : str
        Physical unit of predicted_value (e.g. "dimensionless_0_to_1",
        "metres", "metres_above_sea_level").  Must be set explicitly.

    forecast_horizon : str
        Temporal scope of the prediction (e.g. "static_snapshot",
        "6h_ahead", "24h_ahead").  Required to prevent misuse.

    model_version : str
        Semantic version of the trained model artefact that produced this
        prediction (e.g. "1.0.0").

    data_timestamp : str or None
        ISO-8601 timestamp of the most recent input observation used.

    prediction_status : PredictionStatus
        Machine-readable status.  The GIS engine must check this before
        trusting predicted_value.
    """

    model_config = {"protected_namespaces": ()}

    zone_id: str = Field(..., min_length=1, description="Stable geographic zone ID")
    prediction_time: str = Field(
        ..., description="ISO-8601 UTC timestamp of prediction generation"
    )
    target_name: str = Field(
        ..., description="Name of the predicted quantity"
    )
    predicted_value: Optional[float] = Field(
        None, description="Predicted value; None if prediction_status != OK"
    )
    target_unit: str = Field(
        ..., description="Unit of predicted_value (e.g. 'dimensionless_0_to_1')"
    )
    forecast_horizon: str = Field(
        ..., description="Temporal scope (e.g. 'static_snapshot', '6h_ahead')"
    )
    model_version: str = Field(
        ..., pattern=r"^\d+\.\d+\.\d+$", description="Semantic version of model artefact"
    )
    data_timestamp: Optional[str] = Field(
        None, description="ISO-8601 timestamp of most recent input observation"
    )
    prediction_status: PredictionStatus = Field(
        PredictionStatus.OK, description="Status of this prediction record"
    )
    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="Integration contract version"
    )

    @field_validator("predicted_value")
    @classmethod
    def value_must_be_finite(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v != v or abs(v) == float("inf")):  # NaN or Inf check
            raise ValueError("predicted_value must be finite (not NaN or Inf).")
        return v

    @model_validator(mode="after")
    def value_required_when_ok(self) -> "HazardPredictionRecord":
        if self.prediction_status == PredictionStatus.OK and self.predicted_value is None:
            raise ValueError(
                "predicted_value must be set when prediction_status is OK."
            )
        return self

    def to_gis_dict(self) -> dict:
        """Return a plain dict suitable for JSON export to the GIS module."""
        return self.model_dump()


# ---------------------------------------------------------------------------
# Risk output record
# ---------------------------------------------------------------------------

class RiskOutputRecord(BaseModel):
    """
    Hazard-risk score for a single geographic zone.

    Produced by the AEI risk engine and consumed by the GIS routing engine
    to weight road traversal costs and prioritise evacuation areas.

    IMPORTANT: risk_score is a DECISION-SUPPORT score, not a calibrated
    probability.  It is derived from model predictions, terrain features,
    and data-freshness factors as described in risk_engine/scoring.py.
    Document thresholds when converting to risk_category.

    Fields
    ------
    zone_id : str
        Must match GIS layer zone identifiers.

    risk_score : float or None
        Normalised risk score in [0, 1].  Higher = greater hazard.
        None when risk_status != OK.

    risk_category : RiskCategory
        Ordinal category derived from risk_score using configurable
        thresholds.  UNKNOWN when risk_status != OK.

    data_freshness : str
        ISO-8601 duration string indicating how old the most recent input
        is (e.g. "PT1H" = 1 hour old, "P1D" = 1 day old).

    risk_status : RiskStatus
        Machine-readable status.

    contributing_factors : list of str
        Descriptive list of which inputs contributed to the score.
        Aids interpretability and debugging.
    """

    zone_id: str = Field(..., min_length=1)
    risk_score: Optional[float] = Field(
        None,
        ge=0.0, le=1.0,
        description="Normalised risk score [0, 1]. None when unavailable."
    )
    risk_category: RiskCategory = Field(
        RiskCategory.UNKNOWN,
        description="Ordinal risk category — NOT a calibrated probability"
    )
    data_freshness: Optional[str] = Field(
        None,
        description="ISO-8601 duration string (e.g. 'PT1H', 'P1D')"
    )
    risk_status: RiskStatus = Field(RiskStatus.OK)
    contributing_factors: List[str] = Field(
        default_factory=list,
        description="Which input signals contributed to this score"
    )
    contract_version: str = Field(default=CONTRACT_VERSION)

    @model_validator(mode="after")
    def score_required_when_ok(self) -> "RiskOutputRecord":
        if self.risk_status == RiskStatus.OK and self.risk_score is None:
            raise ValueError(
                "risk_score must be set when risk_status is OK."
            )
        return self

    @model_validator(mode="after")
    def category_must_match_status(self) -> "RiskOutputRecord":
        if self.risk_status != RiskStatus.OK and self.risk_category != RiskCategory.UNKNOWN:
            raise ValueError(
                "risk_category must be UNKNOWN when risk_status is not OK."
            )
        return self

    def to_gis_dict(self) -> dict:
        return self.model_dump()


# ---------------------------------------------------------------------------
# Batch wrappers
# ---------------------------------------------------------------------------

class HazardPredictionBatch(BaseModel):
    """A batch of hazard predictions for export to the GIS engine."""
    records: List[HazardPredictionRecord] = Field(default_factory=list)
    generated_at: str = Field(..., description="ISO-8601 UTC batch generation time")
    scenario_id: Optional[str] = Field(None, description="Optional scenario identifier")
    contract_version: str = Field(default=CONTRACT_VERSION)

    def to_csv_records(self) -> List[dict]:
        return [r.to_gis_dict() for r in self.records]


class RiskOutputBatch(BaseModel):
    """A batch of risk scores for export to the GIS engine."""
    records: List[RiskOutputRecord] = Field(default_factory=list)
    generated_at: str = Field(..., description="ISO-8601 UTC batch generation time")
    scenario_id: Optional[str] = Field(None, description="Optional scenario identifier")
    contract_version: str = Field(default=CONTRACT_VERSION)

    def to_csv_records(self) -> List[dict]:
        return [r.to_gis_dict() for r in self.records]


# ---------------------------------------------------------------------------
# Example factory helpers (used in tests and documentation)
# ---------------------------------------------------------------------------

def make_valid_prediction(zone_id: str = "ZONE_001") -> HazardPredictionRecord:
    """Return a minimal valid HazardPredictionRecord for testing."""
    return HazardPredictionRecord(
        zone_id=zone_id,
        prediction_time="2024-06-01T12:00:00Z",
        target_name="FloodProbability",
        predicted_value=0.72,
        target_unit="dimensionless_0_to_1",
        forecast_horizon="static_snapshot",
        model_version="0.1.0",
        data_timestamp="2024-06-01T06:00:00Z",
        prediction_status=PredictionStatus.OK,
    )


def make_unavailable_prediction(
    zone_id: str,
    reason: PredictionStatus = PredictionStatus.NO_DATA,
) -> HazardPredictionRecord:
    """Return an unavailable HazardPredictionRecord for zones with missing data."""
    return HazardPredictionRecord(
        zone_id=zone_id,
        prediction_time="2024-06-01T12:00:00Z",
        target_name="FloodProbability",
        predicted_value=None,
        target_unit="dimensionless_0_to_1",
        forecast_horizon="static_snapshot",
        model_version="0.1.0",
        data_timestamp=None,
        prediction_status=reason,
    )


def make_valid_risk(zone_id: str = "ZONE_001", score: float = 0.65) -> RiskOutputRecord:
    """Return a minimal valid RiskOutputRecord for testing."""
    return RiskOutputRecord(
        zone_id=zone_id,
        risk_score=score,
        risk_category=RiskCategory.HIGH if score >= 0.6 else RiskCategory.MODERATE,
        data_freshness="PT2H",
        risk_status=RiskStatus.OK,
        contributing_factors=["FloodProbability", "composite_risk_norm"],
    )


def make_unavailable_risk(
    zone_id: str,
    reason: RiskStatus = RiskStatus.NO_DATA,
) -> RiskOutputRecord:
    """Return an unavailable RiskOutputRecord."""
    return RiskOutputRecord(
        zone_id=zone_id,
        risk_score=None,
        risk_category=RiskCategory.UNKNOWN,
        data_freshness=None,
        risk_status=reason,
        contributing_factors=[],
    )
