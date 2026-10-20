"""
AEI — Risk Engine: Risk-Output Validation
===========================================
Validates individual ``RiskOutputRecord`` objects and batches of them
before they are exported to the GIS routing module or written to disk.

Design rules
------------
* Validation never silently discards records.  Every invalid record produces
  a ``RecordValidationResult`` with one or more ``errors`` describing the
  problem.
* Validation is separate from the Pydantic schema.  Pydantic enforces
  structural types; this module enforces semantic consistency and
  application-level business rules that Pydantic cannot express.
* Warnings are distinguished from errors.  A warning does not make a record
  invalid but should be surfaced to operators.
* Duplicate ``zone_id`` handling is configurable and documented.
  The default policy is ``WARN``: duplicates are flagged but not rejected,
  because valid use cases exist (e.g., multiple model runs for the same zone).
* Empty batches are handled explicitly — they produce a valid result with
  a warning, not a crash.

Checks performed on individual records
---------------------------------------
1. ``zone_id`` is non-empty and does not contain only whitespace.
2. ``risk_status`` is a known ``RiskStatus`` enum value.
3. When ``risk_status == OK``:
   a. ``risk_score`` is not None.
   b. ``risk_score`` is finite and in [0.0, 1.0].
   c. ``risk_category`` is not UNKNOWN.
4. When ``risk_status != OK``:
   a. ``risk_score`` is None.
   b. ``risk_category`` is UNKNOWN.
   (These mirror the Pydantic validators but are checked independently so
   validation can be run on dicts as well as Pydantic models.)
5. ``contract_version`` matches ``CONTRACT_VERSION`` if present.
6. ``data_freshness``, when set, is a valid ISO-8601 duration string
   (must start with "P" per ISO 8601).
7. ``contributing_factors`` is a list of strings (not None, not other types).

Additional batch-level checks
-------------------------------
8. Duplicate ``zone_id`` detection (configurable policy).
9. Empty-batch warning.
10. Count of OK vs non-OK records reported in summary.

What this module does NOT do
------------------------------
* It does not re-run the Pydantic schema validation (``RiskOutputRecord``
  already enforces types at construction time).
* It does not validate spatial coordinates or zone geometry.
* It does not evaluate whether ``risk_score`` values are sensible for a
  given real-world context — that requires domain expertise and calibration
  data not available here.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Union

from integration.schemas import (
    CONTRACT_VERSION,
    RiskCategory,
    RiskOutputRecord,
    RiskStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Duplicate-zone policy
# ---------------------------------------------------------------------------

class DuplicateZonePolicy(str, Enum):
    """
    How to handle duplicate zone_id values in a batch.

    WARN   (default) — flag duplicates as warnings; records are kept.
    ERROR  — flag duplicates as errors; records are kept but the batch
             is marked invalid.
    IGNORE — do not check for duplicates.
    """
    WARN   = "warn"
    ERROR  = "error"
    IGNORE = "ignore"


# ---------------------------------------------------------------------------
# Validation result containers
# ---------------------------------------------------------------------------

@dataclass
class RecordValidationResult:
    """
    Validation outcome for one ``RiskOutputRecord``.

    Attributes
    ----------
    zone_id : str
        Zone identifier from the record (may be empty if missing).
    valid : bool
        True when there are no errors (warnings are allowed).
    errors : list of str
        Semantic errors found.  Non-empty → invalid.
    warnings : list of str
        Non-fatal issues.  Non-empty → still valid but should be reviewed.
    """
    zone_id: str
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "VALID" if self.valid else "INVALID"
        parts = [f"[{status}] zone={self.zone_id!r}"]
        for e in self.errors:
            parts.append(f"  ERROR:   {e}")
        for w in self.warnings:
            parts.append(f"  WARNING: {w}")
        return "\n".join(parts)


@dataclass
class BatchValidationResult:
    """
    Aggregated validation outcome for a batch of risk records.

    Attributes
    ----------
    valid : bool
        True when ALL records are individually valid AND no batch-level
        errors were raised.
    total : int
    n_valid : int
    n_invalid : int
    n_ok_status : int     — records with risk_status == OK
    n_non_ok_status : int — records with risk_status != OK
    record_results : list of RecordValidationResult
    batch_errors : list of str   — batch-level errors (e.g. duplicate policy)
    batch_warnings : list of str — batch-level warnings (e.g. empty batch)

    Usage
    -----
    >>> result = validate_batch(records)
    >>> if not result.valid:
    ...     for rr in result.record_results:
    ...         if not rr.valid:
    ...             print(rr.summary())
    """
    valid: bool
    total: int = 0
    n_valid: int = 0
    n_invalid: int = 0
    n_ok_status: int = 0
    n_non_ok_status: int = 0
    record_results: List[RecordValidationResult] = field(default_factory=list)
    batch_errors: List[str] = field(default_factory=list)
    batch_warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "VALID" if self.valid else "INVALID"
        lines = [
            f"Batch validation [{status}]: "
            f"{self.n_valid}/{self.total} records valid, "
            f"{self.n_ok_status} OK-status, "
            f"{self.n_non_ok_status} non-OK-status",
        ]
        for e in self.batch_errors:
            lines.append(f"  BATCH ERROR:   {e}")
        for w in self.batch_warnings:
            lines.append(f"  BATCH WARNING: {w}")
        invalid = [r for r in self.record_results if not r.valid]
        if invalid:
            lines.append(f"  {len(invalid)} invalid record(s):")
            for r in invalid[:10]:        # cap output at 10
                lines.append(f"    {r.summary()}")
            if len(invalid) > 10:
                lines.append(f"    ... and {len(invalid)-10} more")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_record(
    record: Union[RiskOutputRecord, dict],
) -> RecordValidationResult:
    """
    Validate one risk output record.

    Accepts either a ``RiskOutputRecord`` Pydantic object or a plain dict
    (e.g. from ``record.to_gis_dict()``).

    Parameters
    ----------
    record : RiskOutputRecord or dict

    Returns
    -------
    RecordValidationResult
        ``valid=True`` when no errors are found.
        ``valid=False`` when at least one error is found.
        Warnings do not affect ``valid``.
    """
    if isinstance(record, dict):
        return _validate_dict(record)
    return _validate_pydantic(record)


def validate_batch(
    records: Sequence[Union[RiskOutputRecord, dict]],
    duplicate_policy: DuplicateZonePolicy = DuplicateZonePolicy.WARN,
) -> BatchValidationResult:
    """
    Validate a sequence of risk output records as a batch.

    Parameters
    ----------
    records : sequence of RiskOutputRecord or dict
    duplicate_policy : DuplicateZonePolicy
        How to handle zone_id values that appear more than once.
        WARN (default): duplicates produce batch_warnings.
        ERROR: duplicates produce batch_errors (marks batch invalid).
        IGNORE: no duplicate check.

    Returns
    -------
    BatchValidationResult
    """
    batch_errors: List[str] = []
    batch_warnings: List[str] = []
    record_results: List[RecordValidationResult] = []

    records_list = list(records)
    total = len(records_list)

    # ------------------------------------------------------------------
    # Empty batch
    # ------------------------------------------------------------------
    if total == 0:
        batch_warnings.append(
            "Batch is empty (0 records). "
            "No risk information will be available for the GIS module."
        )
        return BatchValidationResult(
            valid=True,
            total=0,
            n_valid=0,
            n_invalid=0,
            n_ok_status=0,
            n_non_ok_status=0,
            record_results=[],
            batch_errors=batch_errors,
            batch_warnings=batch_warnings,
        )

    # ------------------------------------------------------------------
    # Validate individual records
    # ------------------------------------------------------------------
    zone_id_counts: Dict[str, int] = {}
    n_ok = 0
    n_non_ok = 0

    for rec in records_list:
        result = validate_record(rec)
        record_results.append(result)

        # Count zone_id occurrences for duplicate check
        zid = result.zone_id
        zone_id_counts[zid] = zone_id_counts.get(zid, 0) + 1

        # Count status
        status = _get_risk_status(rec)
        if status == RiskStatus.OK:
            n_ok += 1
        else:
            n_non_ok += 1

    # ------------------------------------------------------------------
    # Duplicate zone_id check
    # ------------------------------------------------------------------
    if duplicate_policy != DuplicateZonePolicy.IGNORE:
        duplicates = {z: c for z, c in zone_id_counts.items() if c > 1}
        if duplicates:
            dup_desc = ", ".join(
                f"{z!r}×{c}" for z, c in list(duplicates.items())[:5]
            )
            if len(duplicates) > 5:
                dup_desc += f" ... (+{len(duplicates)-5} more)"
            msg = (
                f"Duplicate zone_id values found: {dup_desc}. "
                "If multiple model runs cover the same zone, ensure the GIS "
                "module knows which record to use."
            )
            if duplicate_policy == DuplicateZonePolicy.ERROR:
                batch_errors.append(msg)
            else:  # WARN
                batch_warnings.append(msg)

    n_valid   = sum(1 for r in record_results if r.valid)
    n_invalid = total - n_valid
    any_batch_error = len(batch_errors) > 0
    overall_valid = (n_invalid == 0) and not any_batch_error

    logger.info(
        "Batch validation: %d/%d valid, %d ok-status, %d non-ok, "
        "%d batch errors, %d batch warnings.",
        n_valid, total, n_ok, n_non_ok, len(batch_errors), len(batch_warnings),
    )

    return BatchValidationResult(
        valid=overall_valid,
        total=total,
        n_valid=n_valid,
        n_invalid=n_invalid,
        n_ok_status=n_ok,
        n_non_ok_status=n_non_ok,
        record_results=record_results,
        batch_errors=batch_errors,
        batch_warnings=batch_warnings,
    )


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------

def _validate_pydantic(record: RiskOutputRecord) -> RecordValidationResult:
    """Validate a Pydantic RiskOutputRecord."""
    errors: List[str] = []
    warnings: List[str] = []
    zone_id = record.zone_id or ""

    # 1. zone_id
    if not zone_id or not zone_id.strip():
        errors.append("zone_id is empty or whitespace-only.")
        zone_id = "<empty>"

    # 2. risk_status is a known enum (Pydantic already enforces this,
    #    but we surface it explicitly for dict path parity)
    # — already enforced by Pydantic; skip re-check here.

    # 3 & 4. OK / non-OK consistency
    if record.risk_status == RiskStatus.OK:
        if record.risk_score is None:
            errors.append(
                "risk_status=OK but risk_score is None. "
                "A numeric score is required."
            )
        else:
            if not math.isfinite(record.risk_score):
                errors.append(
                    f"risk_score={record.risk_score!r} is not finite."
                )
            elif not (0.0 <= record.risk_score <= 1.0):
                errors.append(
                    f"risk_score={record.risk_score:.6f} is outside [0, 1]."
                )
        if record.risk_category == RiskCategory.UNKNOWN:
            errors.append(
                "risk_status=OK but risk_category=UNKNOWN. "
                "An ordinal category (LOW/MODERATE/HIGH/CRITICAL) is required."
            )
    else:
        # non-OK
        if record.risk_score is not None:
            errors.append(
                f"risk_status={record.risk_status.value} but risk_score is "
                f"{record.risk_score:.6f} (expected None for non-OK status)."
            )
        if record.risk_category != RiskCategory.UNKNOWN:
            errors.append(
                f"risk_status={record.risk_status.value} but "
                f"risk_category={record.risk_category.value} "
                "(expected UNKNOWN for non-OK status)."
            )

    # 5. contract_version
    cv = record.contract_version
    if cv and cv != CONTRACT_VERSION:
        warnings.append(
            f"contract_version={cv!r} does not match current "
            f"CONTRACT_VERSION={CONTRACT_VERSION!r}. "
            "The GIS module may reject this record."
        )

    # 6. data_freshness
    if record.data_freshness is not None:
        if not _is_valid_iso8601_duration(record.data_freshness):
            warnings.append(
                f"data_freshness={record.data_freshness!r} does not look like "
                "a valid ISO-8601 duration string (expected to start with 'P')."
            )

    # 7. contributing_factors
    cf = record.contributing_factors
    if cf is None:
        errors.append("contributing_factors is None; expected a list.")
    elif not isinstance(cf, list):
        errors.append(
            f"contributing_factors must be a list, got {type(cf).__name__}."
        )
    else:
        non_str = [i for i, v in enumerate(cf) if not isinstance(v, str)]
        if non_str:
            errors.append(
                f"contributing_factors contains non-string items at "
                f"indices {non_str[:5]}."
            )

    return RecordValidationResult(
        zone_id=zone_id,
        valid=(len(errors) == 0),
        errors=errors,
        warnings=warnings,
    )


def _validate_dict(record: dict) -> RecordValidationResult:
    """
    Validate a plain-dict representation of a RiskOutputRecord
    (e.g. from ``record.to_gis_dict()``).
    """
    errors: List[str] = []
    warnings: List[str] = []
    zone_id = str(record.get("zone_id", "")) or ""

    # 1. zone_id
    if not zone_id or not zone_id.strip():
        errors.append("zone_id is missing, empty or whitespace-only.")
        zone_id = "<empty>"

    # 2. risk_status
    raw_status = record.get("risk_status")
    valid_statuses = {s.value for s in RiskStatus}
    if raw_status not in valid_statuses:
        errors.append(
            f"risk_status={raw_status!r} is not a valid RiskStatus value. "
            f"Expected one of {sorted(valid_statuses)}."
        )
        # Cannot continue status-dependent checks
        return RecordValidationResult(
            zone_id=zone_id, valid=False, errors=errors, warnings=warnings
        )

    status = RiskStatus(raw_status)
    risk_score = record.get("risk_score")
    risk_category = record.get("risk_category")

    # 3 & 4. OK / non-OK consistency
    if status == RiskStatus.OK:
        if risk_score is None:
            errors.append(
                "risk_status=OK but risk_score is null/missing."
            )
        else:
            try:
                score_f = float(risk_score)
            except (TypeError, ValueError):
                errors.append(
                    f"risk_score={risk_score!r} cannot be converted to float."
                )
                score_f = None

            if score_f is not None:
                if not math.isfinite(score_f):
                    errors.append(f"risk_score={score_f!r} is not finite.")
                elif not (0.0 <= score_f <= 1.0):
                    errors.append(
                        f"risk_score={score_f:.6f} is outside [0, 1]."
                    )

        valid_cats = {c.value for c in RiskCategory if c != RiskCategory.UNKNOWN}
        if risk_category not in valid_cats:
            errors.append(
                f"risk_status=OK but risk_category={risk_category!r}. "
                f"Expected one of {sorted(valid_cats)}."
            )
    else:
        if risk_score is not None:
            errors.append(
                f"risk_status={raw_status!r} but risk_score={risk_score!r} "
                "(expected null for non-OK status)."
            )
        if risk_category != RiskCategory.UNKNOWN.value:
            errors.append(
                f"risk_status={raw_status!r} but "
                f"risk_category={risk_category!r} "
                "(expected 'UNKNOWN' for non-OK status)."
            )

    # 5. contract_version
    cv = record.get("contract_version")
    if cv and cv != CONTRACT_VERSION:
        warnings.append(
            f"contract_version={cv!r} does not match current "
            f"CONTRACT_VERSION={CONTRACT_VERSION!r}."
        )

    # 6. data_freshness
    df_val = record.get("data_freshness")
    if df_val is not None:
        if not _is_valid_iso8601_duration(str(df_val)):
            warnings.append(
                f"data_freshness={df_val!r} does not look like a valid "
                "ISO-8601 duration (expected to start with 'P')."
            )

    # 7. contributing_factors
    cf = record.get("contributing_factors")
    if cf is None:
        errors.append("contributing_factors is null/missing; expected a list.")
    elif not isinstance(cf, list):
        errors.append(
            f"contributing_factors must be a list, got {type(cf).__name__}."
        )
    else:
        non_str = [i for i, v in enumerate(cf) if not isinstance(v, str)]
        if non_str:
            errors.append(
                f"contributing_factors contains non-string items at "
                f"indices {non_str[:5]}."
            )

    return RecordValidationResult(
        zone_id=zone_id,
        valid=(len(errors) == 0),
        errors=errors,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_iso8601_duration(s: str) -> bool:
    """
    Minimal check that ``s`` looks like an ISO-8601 duration.

    ISO 8601 durations start with "P" (e.g. "PT1H", "P1D", "PT21600S").
    We do not fully parse the duration — just check the leading character.
    """
    return isinstance(s, str) and s.startswith("P") and len(s) >= 2


def _get_risk_status(
    record: Union[RiskOutputRecord, dict],
) -> RiskStatus:
    """Extract risk_status from either a Pydantic record or a dict."""
    if isinstance(record, dict):
        raw = record.get("risk_status", "")
        try:
            return RiskStatus(raw)
        except ValueError:
            return RiskStatus.SCORING_ERROR
    return record.risk_status
