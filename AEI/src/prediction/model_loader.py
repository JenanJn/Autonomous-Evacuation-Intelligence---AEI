"""
AEI — Prediction: Model Loader
================================
Saves and loads trained model artefacts together with all preprocessing
statistics and a metadata sidecar.

Artefact layout (one directory per model version)
--------------------------------------------------
models/
└── <model_name>_v<version>/
    ├── model.joblib          — trained sklearn estimator (RF or baseline)
    ├── cleaning_stats.joblib — CleaningStats
    ├── feature_stats.joblib  — FeaturePipelineStats
    ├── metadata.json         — ModelMetadata as JSON

Design rules
------------
* The metadata sidecar records every fact needed to reproduce or audit the
  artefact: random seed, dataset provenance, sklearn version, feature list,
  evaluation metrics, training-split strategy.
* load_model_bundle verifies the contract version before returning.
* Artefact directories are never silently overwritten — caller must pass
  overwrite=True explicitly.
* All joblib files use compress=3 for a reasonable size/speed trade-off.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import sklearn

logger = logging.getLogger(__name__)

# Bump when the on-disk format changes in a breaking way.
ARTEFACT_FORMAT_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Metadata schema
# ---------------------------------------------------------------------------

@dataclass
class ModelMetadata:
    """
    Human- and machine-readable sidecar for a saved model artefact.

    All fields are plain Python types so the object can be round-tripped
    through JSON without a custom encoder.
    """
    model_name: str                      # "MeanBaseline" | "RandomForest"
    model_version: str                   # Semantic version, e.g. "0.1.0"
    target_col: str
    feature_cols: List[str]
    train_rows: int
    test_rows: int
    data_source: str                     # SYNTHETIC | REAL | ESTIMATED | SIMULATED
    split_strategy: str
    random_seed: int
    sklearn_version: str
    artefact_format_version: str = ARTEFACT_FORMAT_VERSION
    baseline_mae: Optional[float] = None
    baseline_rmse: Optional[float] = None
    rf_mae: Optional[float] = None
    rf_rmse: Optional[float] = None
    rf_r2: Optional[float] = None
    training_duration_s: Optional[float] = None
    notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Bundle container (in memory)
# ---------------------------------------------------------------------------

@dataclass
class ModelBundle:
    """
    Everything needed to run inference, loaded from disk.

    Attributes
    ----------
    model : any sklearn estimator
    cleaning_stats : CleaningStats
    feature_stats : FeaturePipelineStats
    metadata : ModelMetadata
    artefact_dir : Path
    """
    model: Any
    cleaning_stats: Any          # CleaningStats — avoid circular import
    feature_stats: Any           # FeaturePipelineStats
    metadata: ModelMetadata
    artefact_dir: Path


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_model_bundle(
    model: Any,
    cleaning_stats: Any,
    feature_stats: Any,
    metadata: ModelMetadata,
    models_dir: str | Path,
    overwrite: bool = False,
) -> Path:
    """
    Persist a model bundle to disk.

    Parameters
    ----------
    model : sklearn estimator
    cleaning_stats : CleaningStats
    feature_stats : FeaturePipelineStats
    metadata : ModelMetadata
    models_dir : path to the top-level models/ directory
    overwrite : bool
        If False (default) and the artefact directory already exists, raise.

    Returns
    -------
    Path  — the artefact directory that was written.
    """
    models_dir = Path(models_dir)
    slug = f"{metadata.model_name}_v{metadata.model_version}"
    artefact_dir = models_dir / slug

    if artefact_dir.exists() and not overwrite:
        raise FileExistsError(
            f"Artefact directory already exists: {artefact_dir}. "
            "Pass overwrite=True to replace it."
        )

    artefact_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model,          artefact_dir / "model.joblib",          compress=3)
    joblib.dump(cleaning_stats, artefact_dir / "cleaning_stats.joblib", compress=3)
    joblib.dump(feature_stats,  artefact_dir / "feature_stats.joblib",  compress=3)

    meta_path = artefact_dir / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(asdict(metadata), fh, indent=2, default=str)

    logger.info("Model bundle saved to: %s", artefact_dir)
    return artefact_dir


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_model_bundle(artefact_dir: str | Path) -> ModelBundle:
    """
    Load a model bundle from disk.

    Parameters
    ----------
    artefact_dir : path to the artefact directory (containing model.joblib etc.)

    Returns
    -------
    ModelBundle

    Raises
    ------
    FileNotFoundError  — if a required file is missing
    ValueError         — if the artefact format version is incompatible
    """
    artefact_dir = Path(artefact_dir)

    required = ["model.joblib", "cleaning_stats.joblib",
                "feature_stats.joblib", "metadata.json"]
    for fname in required:
        p = artefact_dir / fname
        if not p.exists():
            raise FileNotFoundError(
                f"Required artefact file missing: {p}\n"
                f"Expected files: {required}"
            )

    with open(artefact_dir / "metadata.json", encoding="utf-8") as fh:
        meta_dict = json.load(fh)

    stored_format = meta_dict.get("artefact_format_version", "unknown")
    if stored_format != ARTEFACT_FORMAT_VERSION:
        raise ValueError(
            f"Artefact format version mismatch: "
            f"stored='{stored_format}', expected='{ARTEFACT_FORMAT_VERSION}'. "
            "Retrain the model with the current codebase."
        )

    metadata = ModelMetadata(**{
        k: v for k, v in meta_dict.items()
        if k in ModelMetadata.__dataclass_fields__
    })

    model          = joblib.load(artefact_dir / "model.joblib")
    cleaning_stats = joblib.load(artefact_dir / "cleaning_stats.joblib")
    feature_stats  = joblib.load(artefact_dir / "feature_stats.joblib")

    logger.info(
        "Loaded model bundle: %s  (data_source=%s)",
        metadata.model_name, metadata.data_source,
    )

    return ModelBundle(
        model=model,
        cleaning_stats=cleaning_stats,
        feature_stats=feature_stats,
        metadata=metadata,
        artefact_dir=artefact_dir,
    )


# ---------------------------------------------------------------------------
# Convenience: build metadata from TrainingResult
# ---------------------------------------------------------------------------

def metadata_from_training_result(
    result: Any,     # TrainingResult — avoid circular import
    model_name: str,
    model_version: str = "0.1.0",
    random_seed: int = 42,
) -> ModelMetadata:
    """
    Construct a ModelMetadata from a TrainingResult.

    Parameters
    ----------
    result : TrainingResult (from train.py)
    model_name : "MeanBaseline" | "RandomForest"
    model_version : str
    random_seed : int

    Returns
    -------
    ModelMetadata
    """
    return ModelMetadata(
        model_name=model_name,
        model_version=model_version,
        target_col=result.target_col,
        feature_cols=result.feature_cols,
        train_rows=result.train_rows,
        test_rows=result.test_rows,
        data_source=result.data_source,
        split_strategy=result.split_strategy,
        random_seed=random_seed,
        sklearn_version=sklearn.__version__,
        baseline_mae=result.baseline_metrics.mae,
        baseline_rmse=result.baseline_metrics.rmse,
        rf_mae=result.rf_metrics.mae,
        rf_rmse=result.rf_metrics.rmse,
        rf_r2=result.rf_metrics.r2,
        training_duration_s=result.training_duration_s,
        notes=result.notes,
    )
