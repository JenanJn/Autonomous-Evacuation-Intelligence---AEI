"""
AEI — Risk Engine: Hazard Scoring
===================================
Converts ``HazardPredictionRecord`` objects into ``RiskOutputRecord`` objects
for consumption by the GIS routing module.

Scoring semantics — read this before using
-------------------------------------------
The AEI model is trained on the Kaggle Playground S4E5 *synthetic* dataset.
Its target, ``FloodProbability``, is approximately a normalised weighted sum
of 20 synthetic indicators.  It is **not** a calibrated exceedance probability
derived from observational hydrology.

Therefore this module makes **no claim** that the derived ``risk_score``
represents a real-world flood risk.  Instead it:

1. Accepts a ``HazardPredictionRecord`` and inspects its ``prediction_status``
   and ``target_name`` before doing anything numeric.
2. Applies a documented, configurable proxy transformation if and only if
   the target is ``FloodProbability`` (the only currently supported target).
3. Labels the output ``risk_status = SCORING_ERROR`` for unsupported targets
   or numeric anomalies rather than silently substituting a made-up value.
4. Labels the output ``risk_status = STALE_DATA`` or ``NO_DATA`` when the
   upstream prediction carries those statuses — these are **never** promoted
   to a LOW risk score.
5. Attaches a ``scoring_method`` label to every record so callers can
   distinguish properly-scored records from provisional proxies.

Proxy transformation for FloodProbability
------------------------------------------
Because no calibrated scoring formula exists yet, the only defensible
transformation is the identity:

    risk_score = predicted_value       (already in [0, 1] by predict.py)

This is recorded as ``scoring_method = "direct_proxy_uncalibrated"`` on
every output record.  The GIS routing module must not interpret this as a
calibrated probability.

When calibration data become available, replace this with a domain-validated
scoring function and change ``scoring_method`` to ``"calibrated_<method>"``.

Category thresholds (configurable, not calibrated)
----------------------------------------------------
The four ordinal categories are assigned by configurable thresholds.
The defaults below are **illustrative placeholders** that must be
calibrated against real flood events before operational use.

    score < LOW_MAX      → LOW
    score < MODERATE_MAX → MODERATE
    score < HIGH_MAX     → HIGH
    score >= HIGH_MAX    → CRITICAL

Default values (provisional):
    LOW_MAX      = 0.25
    MODERATE_MAX = 0.50
    HIGH_MAX     = 0.75

Pass a ``CategoryThresholds`` instance to override these.

Supported targets
-----------------
Only ``FloodProbability`` with unit ``dimensionless_0_to_1`` is supported
in Milestone 2.  Other targets (``WaterLevelM``, ``FloodDepthM``) are
rejected with ``SCORING_ERROR`` until a validated transformation is defined.
Supporting a new target requires:
  * A defensible normalisation formula (documented with its assumptions).
  * A domain-reviewed set of category thresholds.
  * An appropriate ``scoring_method`` label.

Freshness handling
------------------
``data_freshness`` is an ISO-8601 duration string attached to each output
record.  This module computes it from the time elapsed between
``data_timestamp`` (most recent input observation) and ``prediction_time``.
When either timestamp is absent the freshness is left as ``None``.
Staleness detection is the caller's responsibility — this module preserves
the upstream ``STALE_DATA`` status and does not re-evaluate staleness.

City-independence
-----------------
No city names, coordinates or region-specific thresholds are hardcoded.
All configurable values are supplied at call time.

Limitations
-----------
* ``scoring_method = "direct_proxy_uncalibrated"`` is an explicit signal
  that no calibration has been performed.  Do not remove this label without
  replacing it with a validated scoring formula.
* Thresholds assigned here are provisional and not validated.
* The resulting ``risk_category`` must not be displayed as a probability
  in any user-facing UI without further calibration.
* This module does not perform temporal forecasting.  All scores are
  static snapshots.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from integration.schemas import (
    HazardPredictionRecord,
    PredictionStatus,
    RiskCategory,
    RiskOutputRecord,
    RiskStatus,
    CONTRACT_VERSION,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Targets whose predicted_value lies in [0, 1] and can be used directly
# as a proxy risk score.  Anything outside this set is UNSUPPORTED.
SUPPORTED_TARGETS: frozenset[str] = frozenset({"FloodProbability"})

# The scoring method label attached to all records produced by this module.
# Change this when a validated calibration replaces the direct proxy.
SCORING_METHOD_PROXY = "direct_proxy_uncalibrated"

# Contribution factor label added to every output record.
CONTRIBUTION_LABEL = "FloodProbability_direct_proxy"


# ---------------------------------------------------------------------------
# Configurable category thresholds
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CategoryThresholds:
    """
    Configurable ordinal category boundaries.

    All values are in [0, 1].  Constraints (enforced on construction):
        0 <= low_max <= moderate_max <= high_max <= 1

    Assignment rule:
        score < low_max      → LOW
        score < moderate_max → MODERATE
        score < high_max     → HIGH
        score >= high_max    → CRITICAL

    Defaults (provisional — NOT calibrated):
        low_max      = 0.25
        moderate_max = 0.50
        high_max     = 0.75

    IMPORTANT: These defaults are illustrative placeholders.  They were
    not derived from real flood data and must not be treated as validated
    operational thresholds.
    """
    low_max: float      = 0.25
    moderate_max: float = 0.50
    high_max: float     = 0.75

    def __post_init__(self) -> None:
        if not (0.0 <= self.low_max <= self.moderate_max <= self.high_max <= 1.0):
            raise ValueError(
                f"Thresholds must satisfy 0 <= low_max <= moderate_max <= "
                f"high_max <= 1.  Got: low={self.low_max}, "
                f"moderate={self.moderate_max}, high={self.high_max}."
            )

    def categorise(self, score: float) -> RiskCategory:
        """Return the RiskCategory for a finite score in [0, 1]."""
        if score < self.low_max:
            return RiskCategory.LOW
        if score < self.moderate_max:
            return RiskCategory.MODERATE
        if score < self.high_max:
            return RiskCategory.HIGH
        return RiskCategory.CRITICAL


# Default thresholds — callers can override by passing a custom instance.
DEFAULT_THRESHOLDS = CategoryThresholds()


# ---------------------------------------------------------------------------
# Scoring result (extends RiskOutputRecord with provenance fields)
# ---------------------------------------------------------------------------

@dataclass
class ScoredRiskRecord:
    """
    The output of the scoring pipeline for one zone.

    Wraps a ``RiskOutputRecord`` (the GIS-facing contract object) and
    attaches internal provenance fields that are not part of the
    public contract but are needed for auditing and debugging.

    Attributes
    ----------
    risk_record : RiskOutputRecord
        The Pydantic-validated record for GIS consumption.
    scoring_method : str
        Label identifying how risk_score was derived.
        ``"direct_proxy_uncalibrated"`` until a validated formula exists.
    source_prediction_status : PredictionStatus
        Status of the upstream HazardPredictionRecord.
    source_target_name : str
        Target name from the upstream record (e.g. "FloodProbability").
    source_predicted_value : float or None
        Raw predicted_value from the upstream record.
    source_model_version : str
        Model version from the upstream record.
    scoring_note : str
        Human-readable explanation of what was done (or why scoring failed).
    """
    risk_record: RiskOutputRecord
    scoring_method: str
    source_prediction_status: PredictionStatus
    source_target_name: str
    source_predicted_value: Optional[float]
    source_model_version: str
    scoring_note: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_prediction(
    prediction: HazardPredictionRecord,
    thresholds: CategoryThresholds = DEFAULT_THRESHOLDS,
) -> ScoredRiskRecord:
    """
    Convert one ``HazardPredictionRecord`` into a ``ScoredRiskRecord``.

    Scoring rules (in order of evaluation)
    ----------------------------------------
    1. If ``prediction_status`` is not OK → pass the non-OK status through
       as the corresponding ``risk_status``.  risk_score is None.
       The non-OK statuses map as follows:
           NO_DATA       → RiskStatus.NO_DATA
           STALE_DATA    → RiskStatus.STALE_DATA
           MODEL_ERROR   → RiskStatus.SCORING_ERROR
           INVALID_INPUT → RiskStatus.INVALID_INPUT
       Missing or stale predictions are NEVER converted to LOW risk.

    2. If ``target_name`` is not in SUPPORTED_TARGETS → SCORING_ERROR.
       risk_score is None.

    3. If ``predicted_value`` is None (despite OK status) → SCORING_ERROR.

    4. If ``predicted_value`` is not finite or outside [0, 1] → SCORING_ERROR.
       (predict.py already clamps FloodProbability but we guard defensively.)

    5. Apply the proxy transformation:
           risk_score = predicted_value
       Attach scoring_method = SCORING_METHOD_PROXY.

    Parameters
    ----------
    prediction : HazardPredictionRecord
    thresholds : CategoryThresholds
        Configurable category boundaries.  Defaults to DEFAULT_THRESHOLDS.

    Returns
    -------
    ScoredRiskRecord
    """
    zone_id       = prediction.zone_id
    pred_status   = prediction.prediction_status
    target_name   = prediction.target_name
    pred_value    = prediction.predicted_value
    model_version = prediction.model_version

    # ------------------------------------------------------------------
    # Rule 1: upstream prediction not OK
    # ------------------------------------------------------------------
    if pred_status != PredictionStatus.OK:
        risk_status = _map_prediction_status_to_risk_status(pred_status)
        note = (
            f"Upstream prediction_status={pred_status.value}. "
            f"risk_score set to None. This is NOT treated as LOW risk."
        )
        return _make_non_ok_record(
            zone_id=zone_id,
            risk_status=risk_status,
            scoring_method="not_scored",
            pred_status=pred_status,
            target_name=target_name,
            pred_value=pred_value,
            model_version=model_version,
            note=note,
            data_freshness=_compute_freshness(prediction),
        )

    # ------------------------------------------------------------------
    # Rule 2: unsupported target
    # ------------------------------------------------------------------
    if target_name not in SUPPORTED_TARGETS:
        note = (
            f"Target '{target_name}' is not in SUPPORTED_TARGETS "
            f"{set(SUPPORTED_TARGETS)}. "
            "No validated transformation exists for this target. "
            "Define a calibrated scoring formula before enabling it."
        )
        logger.warning("zone=%s: %s", zone_id, note)
        return _make_non_ok_record(
            zone_id=zone_id,
            risk_status=RiskStatus.SCORING_ERROR,
            scoring_method="not_scored",
            pred_status=pred_status,
            target_name=target_name,
            pred_value=pred_value,
            model_version=model_version,
            note=note,
            data_freshness=_compute_freshness(prediction),
        )

    # ------------------------------------------------------------------
    # Rule 3: predicted_value is None despite OK status
    # (should not happen — schemas.py enforces this — but guard anyway)
    # ------------------------------------------------------------------
    if pred_value is None:
        note = (
            "predicted_value is None despite prediction_status=OK. "
            "This indicates a schema violation upstream."
        )
        logger.error("zone=%s: %s", zone_id, note)
        return _make_non_ok_record(
            zone_id=zone_id,
            risk_status=RiskStatus.SCORING_ERROR,
            scoring_method="not_scored",
            pred_status=pred_status,
            target_name=target_name,
            pred_value=None,
            model_version=model_version,
            note=note,
            data_freshness=_compute_freshness(prediction),
        )

    # ------------------------------------------------------------------
    # Rule 4: numeric guard
    # ------------------------------------------------------------------
    if not math.isfinite(pred_value) or not (0.0 <= pred_value <= 1.0):
        note = (
            f"predicted_value={pred_value!r} is not finite or outside [0, 1]. "
            "Scoring aborted."
        )
        logger.error("zone=%s: %s", zone_id, note)
        return _make_non_ok_record(
            zone_id=zone_id,
            risk_status=RiskStatus.SCORING_ERROR,
            scoring_method="not_scored",
            pred_status=pred_status,
            target_name=target_name,
            pred_value=pred_value,
            model_version=model_version,
            note=note,
            data_freshness=_compute_freshness(prediction),
        )

    # ------------------------------------------------------------------
    # Rule 5: apply proxy transformation
    # ------------------------------------------------------------------
    risk_score = pred_value   # identity transform — see module docstring
    category   = thresholds.categorise(risk_score)
    freshness  = _compute_freshness(prediction)

    note = (
        f"Proxy transformation applied: risk_score = predicted_value = {risk_score:.6f}. "
        f"scoring_method={SCORING_METHOD_PROXY!r}. "
        f"This is a SYNTHETIC, PROVISIONAL, UNCALIBRATED decision-support score. "
        f"Do NOT interpret as a calibrated flood probability."
    )

    rr = RiskOutputRecord(
        zone_id=zone_id,
        risk_score=risk_score,
        risk_category=category,
        data_freshness=freshness,
        risk_status=RiskStatus.OK,
        contributing_factors=[CONTRIBUTION_LABEL, f"model_version:{model_version}"],
        contract_version=CONTRACT_VERSION,
    )

    return ScoredRiskRecord(
        risk_record=rr,
        scoring_method=SCORING_METHOD_PROXY,
        source_prediction_status=pred_status,
        source_target_name=target_name,
        source_predicted_value=pred_value,
        source_model_version=model_version,
        scoring_note=note,
    )


def score_batch(
    predictions: Sequence[HazardPredictionRecord],
    thresholds: CategoryThresholds = DEFAULT_THRESHOLDS,
) -> List[ScoredRiskRecord]:
    """
    Score a sequence of HazardPredictionRecords.

    Returns one ScoredRiskRecord per input, in the same order.
    Never raises — errors produce SCORING_ERROR records instead.

    Parameters
    ----------
    predictions : sequence of HazardPredictionRecord
    thresholds : CategoryThresholds

    Returns
    -------
    list of ScoredRiskRecord
    """
    results = []
    for pred in predictions:
        try:
            results.append(score_prediction(pred, thresholds))
        except Exception as exc:
            # Defensive catch — score_prediction should not raise,
            # but if it does we produce an error record rather than
            # propagating a crash to the caller.
            logger.exception(
                "Unexpected error scoring zone=%s: %s", pred.zone_id, exc
            )
            error_rr = RiskOutputRecord(
                zone_id=pred.zone_id,
                risk_score=None,
                risk_category=RiskCategory.UNKNOWN,
                data_freshness=None,
                risk_status=RiskStatus.SCORING_ERROR,
                contributing_factors=[f"exception:{type(exc).__name__}"],
            )
            results.append(ScoredRiskRecord(
                risk_record=error_rr,
                scoring_method="not_scored",
                source_prediction_status=pred.prediction_status,
                source_target_name=pred.target_name,
                source_predicted_value=pred.predicted_value,
                source_model_version=pred.model_version,
                scoring_note=f"Unexpected exception: {exc}",
            ))
    return results


def extract_risk_records(scored: List[ScoredRiskRecord]) -> List[RiskOutputRecord]:
    """
    Extract just the ``RiskOutputRecord`` objects from a list of
    ``ScoredRiskRecord`` objects.

    Convenience function for passing to ``apply_zone_node_mapping`` or
    similar GIS functions that expect ``List[RiskOutputRecord]``.
    """
    return [s.risk_record for s in scored]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_prediction_status_to_risk_status(
    pred_status: PredictionStatus,
) -> RiskStatus:
    """
    Map an upstream PredictionStatus to the corresponding RiskStatus.

    NO_DATA   → NO_DATA   (missing data upstream is missing data downstream)
    STALE_DATA→ STALE_DATA
    MODEL_ERROR  → SCORING_ERROR
    INVALID_INPUT→ INVALID_INPUT
    """
    _mapping = {
        PredictionStatus.NO_DATA:       RiskStatus.NO_DATA,
        PredictionStatus.STALE_DATA:    RiskStatus.STALE_DATA,
        PredictionStatus.MODEL_ERROR:   RiskStatus.SCORING_ERROR,
        PredictionStatus.INVALID_INPUT: RiskStatus.INVALID_INPUT,
    }
    return _mapping.get(pred_status, RiskStatus.SCORING_ERROR)


def _make_non_ok_record(
    zone_id: str,
    risk_status: RiskStatus,
    scoring_method: str,
    pred_status: PredictionStatus,
    target_name: str,
    pred_value: Optional[float],
    model_version: str,
    note: str,
    data_freshness: Optional[str],
) -> ScoredRiskRecord:
    rr = RiskOutputRecord(
        zone_id=zone_id,
        risk_score=None,
        risk_category=RiskCategory.UNKNOWN,
        data_freshness=data_freshness,
        risk_status=risk_status,
        contributing_factors=[],
        contract_version=CONTRACT_VERSION,
    )
    return ScoredRiskRecord(
        risk_record=rr,
        scoring_method=scoring_method,
        source_prediction_status=pred_status,
        source_target_name=target_name,
        source_predicted_value=pred_value,
        source_model_version=model_version,
        scoring_note=note,
    )


def _compute_freshness(prediction: HazardPredictionRecord) -> Optional[str]:
    """
    Compute an ISO-8601 duration string representing the age of the input
    data at the time the prediction was made.

    Returns None if either timestamp is missing or cannot be parsed.

    Example: data_timestamp="2024-06-01T06:00:00Z",
             prediction_time="2024-06-01T12:00:00Z"
             → "PT21600S"  (6 hours = 21 600 seconds)
    """
    if not prediction.data_timestamp or not prediction.prediction_time:
        return None
    try:
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        t_data = datetime.strptime(prediction.data_timestamp, fmt).replace(
            tzinfo=timezone.utc
        )
        t_pred = datetime.strptime(prediction.prediction_time, fmt).replace(
            tzinfo=timezone.utc
        )
        delta_s = (t_pred - t_data).total_seconds()
        if delta_s < 0:
            # data_timestamp is after prediction_time — unusual but possible
            # for back-dated predictions; report as zero freshness.
            delta_s = 0.0
        return f"PT{int(delta_s)}S"
    except (ValueError, TypeError):
        return None
