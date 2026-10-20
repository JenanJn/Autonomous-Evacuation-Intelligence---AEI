"""
AEI — Prediction: Evaluation
==============================
Computes and formats regression evaluation metrics.

Design choices
--------------
* Only MAE and RMSE are reported as primary metrics — these are the
  requirements for regression on this task.
* R² is included as a supplementary diagnostic but must not be the primary
  decision metric (it behaves poorly on small datasets and can be negative).
* All functions return typed dataclasses, not raw dicts, to make metric
  values explicit and reduce the chance of silent misuse.
* No metrics are invented.  If inputs are empty or contain NaN, an error
  is raised rather than returning a misleading number.

Scientific-integrity note
-------------------------
Metrics computed on SYNTHETIC data do not measure real-world flood-prediction
accuracy.  The caller's ModelMetadata.data_source field must carry the
provenance label so this cannot be forgotten.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class RegressionMetrics:
    """
    Regression evaluation metrics for one model on one split.

    Attributes
    ----------
    model_name : str
    mae : float  — Mean Absolute Error
    rmse : float  — Root Mean Squared Error
    r2 : float  — R-squared (supplementary; not the primary metric)
    n_samples : int  — number of test rows used
    notes : str  — free-text, e.g. provenance caveat
    """
    model_name: str
    mae: float
    rmse: float
    r2: float
    n_samples: int
    notes: str = ""

    def summary(self) -> str:
        lines = [
            f"Model     : {self.model_name}",
            f"Samples   : {self.n_samples}",
            f"MAE       : {self.mae:.6f}",
            f"RMSE      : {self.rmse:.6f}",
            f"R²        : {self.r2:.6f}  (supplementary)",
        ]
        if self.notes:
            lines.append(f"Notes     : {self.notes}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core metric computation
# ---------------------------------------------------------------------------

def compute_regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    model_name: str = "model",
    notes: str = "",
) -> RegressionMetrics:
    """
    Compute MAE, RMSE and R² from arrays.

    Parameters
    ----------
    y_true : np.ndarray, shape (n,)
    y_pred : np.ndarray, shape (n,)
    model_name : str
    notes : str

    Returns
    -------
    RegressionMetrics

    Raises
    ------
    ValueError
        If either array is empty, contains NaN, or shapes differ.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    if y_true.shape != y_pred.shape:
        raise ValueError(
            f"Shape mismatch: y_true {y_true.shape} vs y_pred {y_pred.shape}."
        )
    if len(y_true) == 0:
        raise ValueError("Cannot compute metrics on empty arrays.")
    if np.any(np.isnan(y_true)):
        raise ValueError("y_true contains NaN values.  Drop them before evaluating.")
    if np.any(np.isnan(y_pred)):
        raise ValueError(
            f"y_pred from '{model_name}' contains NaN values.  "
            "Check model output and feature matrix for NaN."
        )

    n = len(y_true)
    residuals = y_true - y_pred
    mae  = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))

    # R²  =  1 - SS_res / SS_tot
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    logger.info(
        "[%s] n=%d  MAE=%.6f  RMSE=%.6f  R²=%.6f",
        model_name, n, mae, rmse, r2,
    )

    return RegressionMetrics(
        model_name=model_name,
        mae=mae,
        rmse=rmse,
        r2=r2,
        n_samples=n,
        notes=notes,
    )


def compare_models(
    baseline: RegressionMetrics,
    candidate: RegressionMetrics,
) -> str:
    """
    Return a human-readable comparison of two RegressionMetrics objects.
    Flags whether the candidate beats the baseline on MAE and RMSE.
    """
    mae_improvement  = (baseline.mae  - candidate.mae)  / max(baseline.mae,  1e-12) * 100
    rmse_improvement = (baseline.rmse - candidate.rmse) / max(baseline.rmse, 1e-12) * 100

    lines = [
        "Model comparison (test split)",
        "-" * 40,
        f"{'Metric':<12} {'Baseline':>12} {'Candidate':>12} {'Δ%':>8}",
        f"{'MAE':<12} {baseline.mae:>12.6f} {candidate.mae:>12.6f} {mae_improvement:>+7.2f}%",
        f"{'RMSE':<12} {baseline.rmse:>12.6f} {candidate.rmse:>12.6f} {rmse_improvement:>+7.2f}%",
        f"{'R²':<12} {baseline.r2:>12.6f} {candidate.r2:>12.6f}",
        "-" * 40,
    ]

    if candidate.mae < baseline.mae and candidate.rmse < baseline.rmse:
        lines.append("VERDICT: Candidate beats baseline on both MAE and RMSE.")
    elif candidate.mae < baseline.mae:
        lines.append("VERDICT: Candidate beats baseline on MAE only.")
    elif candidate.rmse < baseline.rmse:
        lines.append("VERDICT: Candidate beats baseline on RMSE only.")
    else:
        lines.append("VERDICT: Candidate does NOT beat baseline on either metric.")

    return "\n".join(lines)
