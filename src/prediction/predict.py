"""
AEI — Prediction: Inference Interface
=======================================
Provides a reusable, validated prediction interface that sits between
the raw data pipeline and the GIS integration schemas.

Design rules
------------
* A loaded ModelBundle is the only required argument.  No global state.
* Input DataFrames are validated before inference — invalid inputs return
  records with prediction_status=INVALID_INPUT, not raised exceptions,
  so the GIS engine always receives a well-formed response.
* Prediction time is measured and returned alongside the outputs.
* Preprocessing reuses the loaded CleaningStats and FeaturePipelineStats —
  the model is never retrained for a prediction request.
* Outputs are Pydantic-validated HazardPredictionRecord objects compatible
  with the integration contract defined in schemas.py.
* Data provenance from the artefact metadata is forwarded to every record.

City-independence
-----------------
zone_id values come from the input DataFrame; nothing is hardcoded here.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np
import pandas as pd

from data_pipeline.cleaning import apply_cleaning_pipeline
from data_pipeline.feature_engineering import (
    apply_feature_pipeline,
    build_model_feature_matrix,
)
from integration.schemas import (
    HazardPredictionBatch,
    HazardPredictionRecord,
    PredictionStatus,
)
from prediction.model_loader import ModelBundle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Inference timing container
# ---------------------------------------------------------------------------

@dataclass
class InferenceTiming:
    """
    Measured latency for one predict_batch call.

    All times are in seconds.
    """
    preprocess_s: float
    inference_s: float
    schema_build_s: float
    total_s: float
    n_records: int

    def summary(self) -> str:
        return (
            f"Inference timing ({self.n_records} records): "
            f"preprocess={self.preprocess_s*1000:.2f} ms  "
            f"inference={self.inference_s*1000:.2f} ms  "
            f"schema={self.schema_build_s*1000:.2f} ms  "
            f"total={self.total_s*1000:.2f} ms"
        )


@dataclass
class PredictResult:
    """Return value of predict_batch."""
    batch: HazardPredictionBatch
    timing: InferenceTiming


# ---------------------------------------------------------------------------
# Main inference function
# ---------------------------------------------------------------------------

def predict_batch(
    df: pd.DataFrame,
    bundle: ModelBundle,
    scenario_id: Optional[str] = None,
    zone_id_col: Optional[str] = "zone_id",
    forecast_horizon: str = "static_snapshot",
) -> PredictResult:
    """
    Run batch inference on a DataFrame and return validated output records.

    Parameters
    ----------
    df : pd.DataFrame
        Input feature data.  Must contain the feature columns the model was
        trained on.  May optionally contain a zone_id column.
    bundle : ModelBundle
        Loaded model + preprocessing artefacts from model_loader.load_model_bundle.
    scenario_id : str, optional
        Identifier for the current prediction scenario (e.g. "flood_event_042").
    zone_id_col : str, optional
        Column name that holds zone identifiers.  If None or not present,
        zone IDs are generated as "ROW_{i:06d}".
    forecast_horizon : str
        Temporal scope label forwarded to every output record.

    Returns
    -------
    PredictResult containing:
        batch   — HazardPredictionBatch (Pydantic-validated records)
        timing  — InferenceTiming with measured latency
    """
    prediction_time = _utc_now()
    t_total_start = time.perf_counter()

    metadata  = bundle.metadata
    model     = bundle.model
    c_stats   = bundle.cleaning_stats
    fe_stats  = bundle.feature_stats
    feat_cols = metadata.feature_cols
    target    = metadata.target_col

    n_input = len(df)
    if n_input == 0:
        logger.warning("predict_batch called with empty DataFrame.")
        empty_batch = HazardPredictionBatch(
            records=[],
            generated_at=prediction_time,
            scenario_id=scenario_id,
        )
        zero = InferenceTiming(0, 0, 0, 0, 0)
        return PredictResult(batch=empty_batch, timing=zero)

    # ------------------------------------------------------------------
    # Input validation — check RAW indicator columns are present.
    # The model's feature_cols list contains post-engineering names
    # (e.g. "MonsoonIntensity_scaled").  The input DataFrame contains
    # raw names (e.g. "MonsoonIntensity").  We derive the required raw
    # columns from the scaled names and check those instead.
    # ------------------------------------------------------------------
    raw_required = _raw_cols_from_feature_cols(feat_cols)
    missing_cols = [c for c in raw_required if c not in df.columns]
    if missing_cols:
        logger.error("Missing feature columns: %s", missing_cols)
        records = _build_error_records(
            df, zone_id_col, PredictionStatus.INVALID_INPUT,
            prediction_time, target, metadata.model_version, forecast_horizon,
        )
        t_end = time.perf_counter()
        timing = InferenceTiming(0, 0, 0, t_end - t_total_start, len(records))
        return PredictResult(
            batch=HazardPredictionBatch(
                records=records, generated_at=prediction_time, scenario_id=scenario_id
            ),
            timing=timing,
        )

    # ------------------------------------------------------------------
    # Preprocessing (reuse training stats — no refitting)
    # ------------------------------------------------------------------
    t_pre = time.perf_counter()
    try:
        df_clean = apply_cleaning_pipeline(
            df, c_stats, drop_target_nulls=False, target_column=None
        )
        df_eng = apply_feature_pipeline(df_clean, fe_stats)
        X, _ = build_model_feature_matrix(df_eng, feature_cols=feat_cols,
                                          target_col=None)
    except Exception as exc:
        logger.error("Preprocessing failed: %s", exc)
        records = _build_error_records(
            df, zone_id_col, PredictionStatus.INVALID_INPUT,
            prediction_time, target, metadata.model_version, forecast_horizon,
        )
        t_end = time.perf_counter()
        timing = InferenceTiming(t_end - t_pre, 0, 0, t_end - t_total_start, len(records))
        return PredictResult(
            batch=HazardPredictionBatch(
                records=records, generated_at=prediction_time, scenario_id=scenario_id
            ),
            timing=timing,
        )
    t_pre_end = time.perf_counter()
    preprocess_s = t_pre_end - t_pre

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    t_inf = time.perf_counter()
    try:
        preds = model.predict(X)
    except Exception as exc:
        logger.error("Model inference failed: %s", exc)
        records = _build_error_records(
            df, zone_id_col, PredictionStatus.MODEL_ERROR,
            prediction_time, target, metadata.model_version, forecast_horizon,
        )
        t_end = time.perf_counter()
        timing = InferenceTiming(preprocess_s, t_end - t_inf, 0,
                                 t_end - t_total_start, len(records))
        return PredictResult(
            batch=HazardPredictionBatch(
                records=records, generated_at=prediction_time, scenario_id=scenario_id
            ),
            timing=timing,
        )
    t_inf_end = time.perf_counter()
    inference_s = t_inf_end - t_inf

    # ------------------------------------------------------------------
    # Build validated output records
    # ------------------------------------------------------------------
    t_schema = time.perf_counter()
    zone_ids = _extract_zone_ids(df, zone_id_col, len(preds))

    records: List[HazardPredictionRecord] = []
    for i, (zone_id, pred_val) in enumerate(zip(zone_ids, preds)):
        val = float(pred_val)
        # Clamp to [0, 1] for targets defined on that scale
        if target == "FloodProbability":
            val = float(np.clip(val, 0.0, 1.0))

        if not np.isfinite(val):
            status = PredictionStatus.MODEL_ERROR
            val = None
        else:
            status = PredictionStatus.OK

        records.append(HazardPredictionRecord(
            zone_id=zone_id,
            prediction_time=prediction_time,
            target_name=target,
            predicted_value=val,
            target_unit=_target_unit(target),
            forecast_horizon=forecast_horizon,
            model_version=metadata.model_version,
            data_timestamp=None,
            prediction_status=status,
        ))

    t_schema_end = time.perf_counter()
    schema_build_s = t_schema_end - t_schema
    total_s = t_schema_end - t_total_start

    timing = InferenceTiming(
        preprocess_s=preprocess_s,
        inference_s=inference_s,
        schema_build_s=schema_build_s,
        total_s=total_s,
        n_records=len(records),
    )

    logger.info(timing.summary())

    batch = HazardPredictionBatch(
        records=records,
        generated_at=prediction_time,
        scenario_id=scenario_id,
    )
    return PredictResult(batch=batch, timing=timing)


def predict_single(
    row: dict,
    bundle: ModelBundle,
    zone_id: str = "ZONE_UNKNOWN",
    forecast_horizon: str = "static_snapshot",
) -> HazardPredictionRecord:
    """
    Convenience wrapper for single-row inference.

    Parameters
    ----------
    row : dict  — feature values (keys = column names)
    bundle : ModelBundle
    zone_id : str
    forecast_horizon : str

    Returns
    -------
    HazardPredictionRecord
    """
    df = pd.DataFrame([row])
    if zone_id:
        df["zone_id"] = zone_id
    result = predict_batch(df, bundle, zone_id_col="zone_id",
                           forecast_horizon=forecast_horizon)
    if result.batch.records:
        return result.batch.records[0]

    # Empty result — return unavailable record
    return HazardPredictionRecord(
        zone_id=zone_id,
        prediction_time=_utc_now(),
        target_name=bundle.metadata.target_col,
        predicted_value=None,
        target_unit=_target_unit(bundle.metadata.target_col),
        forecast_horizon=forecast_horizon,
        model_version=bundle.metadata.model_version,
        prediction_status=PredictionStatus.MODEL_ERROR,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _target_unit(target_col: str) -> str:
    units = {
        "FloodProbability": "dimensionless_0_to_1",
        "WaterLevelM":      "metres_above_sea_level",
        "FloodDepthM":      "metres",
    }
    return units.get(target_col, "unknown")


def _extract_zone_ids(
    df: pd.DataFrame, zone_id_col: Optional[str], n: int
) -> List[str]:
    if zone_id_col and zone_id_col in df.columns:
        return [str(v) for v in df[zone_id_col].values]
    return [f"ROW_{i:06d}" for i in range(n)]


def _build_error_records(
    df: pd.DataFrame,
    zone_id_col: Optional[str],
    status: PredictionStatus,
    prediction_time: str,
    target_col: str,
    model_version: str,
    forecast_horizon: str,
) -> List[HazardPredictionRecord]:
    zone_ids = _extract_zone_ids(df, zone_id_col, len(df))
    return [
        HazardPredictionRecord(
            zone_id=zid,
            prediction_time=prediction_time,
            target_name=target_col,
            predicted_value=None,
            target_unit=_target_unit(target_col),
            forecast_horizon=forecast_horizon,
            model_version=model_version,
            data_timestamp=None,
            prediction_status=status,
        )
        for zid in zone_ids
    ]


def _raw_cols_from_feature_cols(feat_cols: List[str]) -> List[str]:
    """
    Derive the raw input column names that must be present in the input
    DataFrame, given the model's post-engineering feature column list.

    Scaled columns   "X_scaled"  → raw column "X"
    Composite cols   "composite_risk_raw", "composite_risk_norm",
                     "hydro_pressure", "governance_deficit",
                     "infrastructure_stress"  → derived, not required as input
    """
    COMPOSITE = {
        "composite_risk_raw", "composite_risk_norm",
        "hydro_pressure", "governance_deficit", "infrastructure_stress",
    }
    raw = []
    for col in feat_cols:
        if col in COMPOSITE:
            continue           # computed from raw cols during feature engineering
        if col.endswith("_scaled"):
            raw.append(col[:-len("_scaled")])
        else:
            raw.append(col)    # already a raw name
    return raw
