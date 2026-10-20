"""
AEI — Data Pipeline: Ingestion
================================
Loads raw data from supported file formats and validates that the required
columns and data types are present before anything else touches the data.

Supported formats
-----------------
* CSV  — tabular event/indicator datasets (e.g. Kaggle Playground S4E5)
* Parquet — processed/cached tabular data
* NetCDF — gridded IMD rainfall (requires netCDF4 + numpy; lazy-loaded)
* GeoTIFF — raster DEM / WorldPop (requires rasterio; lazy-loaded)

City-independence notes
-----------------------
* No geographic coordinates or city names are hardcoded here.
* The caller supplies the file path and the expected schema name.
* Schema definitions live in SCHEMA_REGISTRY at the bottom of this file
  and can be extended for new datasets without touching pipeline logic.

Scientific-integrity notes
--------------------------
* Every DataFrame returned carries a ``_data_source`` metadata attribute
  (stored in df.attrs) that identifies whether the data is REAL, ESTIMATED,
  SIMULATED, or SYNTHETIC.
* Callers must supply the correct label; this module does not infer it.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data-source provenance labels (scientific integrity requirement)
# ---------------------------------------------------------------------------
DATA_SOURCE_LABELS = {"REAL", "ESTIMATED", "SIMULATED", "SYNTHETIC"}


# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------
@dataclass
class ColumnSpec:
    """Describes one required column."""
    name: str
    dtype_kind: str          # 'f' float, 'i' int, 'O' object, 'M' datetime — uses np.dtype.kind
    nullable: bool = True
    value_min: Optional[float] = None
    value_max: Optional[float] = None
    description: str = ""


@dataclass
class DatasetSchema:
    """
    Declares the expected columns for one named dataset.

    Parameters
    ----------
    name : str
        Short identifier, e.g. ``"kaggle_s4e5"``.
    required_columns : list[ColumnSpec]
        Columns that MUST be present.
    optional_columns : list[ColumnSpec]
        Columns that MAY be present; validated if found.
    target_column : str or None
        The prediction target column, if present in this dataset.
    notes : str
        Free-text description including data provenance and limitations.
    """
    name: str
    required_columns: List[ColumnSpec] = field(default_factory=list)
    optional_columns: List[ColumnSpec] = field(default_factory=list)
    target_column: Optional[str] = None
    notes: str = ""


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover
        lines = [f"ValidationResult(valid={self.valid})"]
        for e in self.errors:
            lines.append(f"  ERROR   {e}")
        for w in self.warnings:
            lines.append(f"  WARNING {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core ingestion functions
# ---------------------------------------------------------------------------

def load_csv(
    path: str | Path,
    data_source_label: str,
    schema_name: Optional[str] = None,
    **pandas_kwargs,
) -> pd.DataFrame:
    """
    Load a CSV file, attach provenance metadata, and optionally validate
    the schema.

    Parameters
    ----------
    path : str or Path
    data_source_label : str
        One of DATA_SOURCE_LABELS.  Must be set by the caller honestly.
    schema_name : str or None
        Key into SCHEMA_REGISTRY.  If supplied, validation is run after load.
    **pandas_kwargs
        Forwarded to ``pd.read_csv``.

    Returns
    -------
    pd.DataFrame
        With ``df.attrs["_data_source"]``, ``df.attrs["_source_file"]``,
        and ``df.attrs["_schema_name"]`` populated.

    Raises
    ------
    FileNotFoundError
    ValueError
        If data_source_label is unrecognised or schema validation fails with
        errors.
    """
    path = Path(path)
    _check_source_label(data_source_label)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    logger.info("Loading CSV: %s", path)
    df = pd.read_csv(path, **pandas_kwargs)
    _attach_metadata(df, data_source_label, path, schema_name)

    if schema_name is not None:
        result = validate_dataframe(df, schema_name)
        _raise_on_errors(result, path)

    logger.info("Loaded %d rows × %d cols from %s", len(df), len(df.columns), path.name)
    return df


def load_parquet(
    path: str | Path,
    data_source_label: str,
    schema_name: Optional[str] = None,
) -> pd.DataFrame:
    """Load a Parquet file with optional schema validation."""
    path = Path(path)
    _check_source_label(data_source_label)

    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    logger.info("Loading Parquet: %s", path)
    df = pd.read_parquet(path)
    _attach_metadata(df, data_source_label, path, schema_name)

    if schema_name is not None:
        result = validate_dataframe(df, schema_name)
        _raise_on_errors(result, path)

    logger.info("Loaded %d rows × %d cols from %s", len(df), len(df.columns), path.name)
    return df


def load_netcdf_rainfall(
    path: str | Path,
    variable_name: str = "RAINFALL",
    lat_name: str = "LATITUDE",
    lon_name: str = "LONGITUDE",
    time_name: str = "TIME",
) -> pd.DataFrame:
    """
    Load an IMD-style gridded rainfall NetCDF file and flatten it into a
    tidy DataFrame with columns [latitude, longitude, time, rainfall_mm].

    This function handles the IMD 0.25° daily gridded product
    (https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html).

    Parameters
    ----------
    path : str or Path
    variable_name : str
        Name of the rainfall variable inside the NetCDF file.
    lat_name, lon_name, time_name : str
        Dimension names inside the NetCDF file.

    Returns
    -------
    pd.DataFrame
        Columns: latitude, longitude, date, rainfall_mm
        df.attrs["_data_source"] = "REAL"

    Notes
    -----
    * IMD gridded data is DAILY.  It cannot represent sub-daily rainfall
      intensity or storm duration.  Do not treat it as 10-minute observations.
    * Spatial resolution is 0.25° (~28 km).  Do not interpolate to
      apparent high-resolution without documenting the assumption.
    """
    try:
        import netCDF4 as nc  # noqa: N813
    except ImportError as exc:
        raise ImportError(
            "netCDF4 is required to load IMD NetCDF files. "
            "Install it with: pip install netCDF4==1.7.1"
        ) from exc

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"NetCDF file not found: {path}")

    logger.info("Loading NetCDF rainfall: %s", path)
    with nc.Dataset(path, "r") as ds:
        lats = ds.variables[lat_name][:]
        lons = ds.variables[lon_name][:]
        times = ds.variables[time_name]
        rain = ds.variables[variable_name][:]  # shape: (time, lat, lon)

        # Convert CF time to Python dates
        dates = nc.num2date(times[:], times.units)

    # Flatten to tidy format
    records = []
    for t_idx, date in enumerate(dates):
        for la_idx, lat in enumerate(lats):
            for lo_idx, lon in enumerate(lons):
                val = float(rain[t_idx, la_idx, lo_idx])
                if not np.ma.is_masked(val):
                    records.append({
                        "latitude": float(lat),
                        "longitude": float(lon),
                        "date": pd.Timestamp(str(date)),
                        "rainfall_mm": val,
                    })

    df = pd.DataFrame(records)
    _attach_metadata(df, "REAL", path, "imd_rainfall")
    logger.info("Flattened NetCDF to %d rows", len(df))
    return df


def load_geotiff_raster(
    path: str | Path,
    band: int = 1,
    value_column: str = "raster_value",
) -> pd.DataFrame:
    """
    Load a single band from a GeoTIFF (Copernicus DEM, WorldPop) and return
    a DataFrame with columns [row, col, latitude, longitude, <value_column>].

    Masked / nodata pixels are dropped.

    Parameters
    ----------
    path : str or Path
    band : int
        1-based band index.
    value_column : str
        Name given to the raster value column.

    Returns
    -------
    pd.DataFrame
    """
    try:
        import rasterio
        from rasterio.transform import xy as rasterio_xy
    except ImportError as exc:
        raise ImportError(
            "rasterio is required to load GeoTIFF files. "
            "Install it with: pip install rasterio==1.3.10"
        ) from exc

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"GeoTIFF file not found: {path}")

    logger.info("Loading GeoTIFF: %s (band %d)", path, band)
    with rasterio.open(path) as src:
        data = src.read(band, masked=True)
        transform = src.transform

    rows_idx, cols_idx = np.where(~data.mask)
    values = data.data[rows_idx, cols_idx]
    lats, lons = rasterio_xy(transform, rows_idx, cols_idx)

    df = pd.DataFrame({
        "row": rows_idx,
        "col": cols_idx,
        "latitude": lats,
        "longitude": lons,
        value_column: values.astype(float),
    })

    # Provenance: DEM = REAL; WorldPop = ESTIMATED (model-derived)
    # Caller must set after load if they need to override
    _attach_metadata(df, "REAL", path, None)
    logger.info("Loaded %d valid pixels from %s", len(df), path.name)
    return df


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_dataframe(df: pd.DataFrame, schema_name: str) -> ValidationResult:
    """
    Check that *df* satisfies the named schema.

    Returns a ValidationResult rather than raising, so callers can log
    warnings without stopping the pipeline when non-critical issues appear.
    """
    if schema_name not in SCHEMA_REGISTRY:
        known = sorted(SCHEMA_REGISTRY.keys())
        return ValidationResult(
            valid=False,
            errors=[f"Unknown schema '{schema_name}'. Known schemas: {known}"],
        )

    schema = SCHEMA_REGISTRY[schema_name]
    errors: List[str] = []
    warns: List[str] = []

    # Check required columns
    for spec in schema.required_columns:
        if spec.name not in df.columns:
            errors.append(f"Required column '{spec.name}' is missing.")
            continue
        _check_column(df[spec.name], spec, errors, warns, required=True)

    # Check optional columns if present
    for spec in schema.optional_columns:
        if spec.name in df.columns:
            _check_column(df[spec.name], spec, errors, warns, required=False)

    # Empty DataFrame
    if len(df) == 0:
        warns.append("DataFrame has 0 rows — pipeline may produce no output.")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warns)


def _check_column(
    series: pd.Series,
    spec: ColumnSpec,
    errors: List[str],
    warns: List[str],
    required: bool,
) -> None:
    prefix = f"Column '{spec.name}'"

    # Dtype kind check (skip object columns — too broad to enforce kind)
    if spec.dtype_kind != "O":
        actual_kind = series.dtype.kind
        if actual_kind not in (spec.dtype_kind, "f", "i"):
            # Allow numeric upcasting
            if not (spec.dtype_kind in ("f", "i") and actual_kind in ("f", "i")):
                msg = (
                    f"{prefix}: expected dtype kind '{spec.dtype_kind}', "
                    f"got '{actual_kind}' ({series.dtype})."
                )
                if required:
                    errors.append(msg)
                else:
                    warns.append(msg)

    # Nullability
    null_count = series.isna().sum()
    if null_count > 0 and not spec.nullable:
        errors.append(f"{prefix}: {null_count} null values found but column is not nullable.")
    elif null_count > 0:
        pct = 100 * null_count / max(len(series), 1)
        if pct > 20:
            warns.append(f"{prefix}: {null_count} nulls ({pct:.1f}%) — review imputation strategy.")

    # Value bounds (numeric only, ignoring NaNs)
    if spec.value_min is not None or spec.value_max is not None:
        numeric = pd.to_numeric(series, errors="coerce").dropna()
        if spec.value_min is not None and (numeric < spec.value_min).any():
            errors.append(f"{prefix}: values below minimum {spec.value_min} found.")
        if spec.value_max is not None and (numeric > spec.value_max).any():
            errors.append(f"{prefix}: values above maximum {spec.value_max} found.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_source_label(label: str) -> None:
    if label not in DATA_SOURCE_LABELS:
        raise ValueError(
            f"data_source_label must be one of {DATA_SOURCE_LABELS}, got '{label}'."
        )


def _attach_metadata(
    df: pd.DataFrame,
    data_source_label: str,
    path: Path,
    schema_name: Optional[str],
) -> None:
    df.attrs["_data_source"] = data_source_label
    df.attrs["_source_file"] = str(path)
    df.attrs["_schema_name"] = schema_name or ""


def _raise_on_errors(result: ValidationResult, path: Path) -> None:
    for w in result.warnings:
        warnings.warn(f"[{path.name}] {w}", stacklevel=3)
    if not result.valid:
        msg = "\n".join(result.errors)
        raise ValueError(f"Schema validation failed for '{path.name}':\n{msg}")


# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------
# Add new schemas here without changing pipeline logic above.

# Features shared by the Kaggle Playground S4E5 flood-probability dataset.
# Source: https://www.kaggle.com/competitions/playground-series-s4e5
# Data type: SYNTHETIC (generated, not real observations).
# Target: FloodProbability — a normalised 0-1 score, NOT a calibrated
#         probability from observational data.

_KAGGLE_S4E5_FEATURES = [
    ColumnSpec("MonsoonIntensity",       "f", True,  0, 10),
    ColumnSpec("TopographyDrainage",     "f", True,  0, 10),
    ColumnSpec("RiverManagement",        "f", True,  0, 10),
    ColumnSpec("Deforestation",          "f", True,  0, 10),
    ColumnSpec("Urbanization",           "f", True,  0, 10),
    ColumnSpec("ClimateChange",          "f", True,  0, 10),
    ColumnSpec("DamsQuality",            "f", True,  0, 10),
    ColumnSpec("Siltation",              "f", True,  0, 10),
    ColumnSpec("AgriculturalPractices",  "f", True,  0, 10),
    ColumnSpec("Encroachments",          "f", True,  0, 10),
    ColumnSpec("IneffectiveDisasterPrep","f", True,  0, 10),
    ColumnSpec("WaterBodyChanges",       "f", True,  0, 10),
    ColumnSpec("DeterioratingInfrastructure", "f", True, 0, 10),
    ColumnSpec("PopulationScore",        "f", True,  0, 10),
    ColumnSpec("WetlandLoss",            "f", True,  0, 10),
    ColumnSpec("InadequatePlanning",     "f", True,  0, 10),
    ColumnSpec("PoliticalFactors",       "f", True,  0, 10),
    ColumnSpec("DrainageSystems",        "f", True,  0, 10),
    ColumnSpec("CoastalVulnerability",   "f", True,  0, 10),
    ColumnSpec("Landslides",             "f", True,  0, 10),
]

SCHEMA_REGISTRY: Dict[str, DatasetSchema] = {

    "kaggle_s4e5": DatasetSchema(
        name="kaggle_s4e5",
        required_columns=_KAGGLE_S4E5_FEATURES,
        optional_columns=[
            ColumnSpec("id",              "i", True),
            ColumnSpec("FloodProbability","f", False, 0.0, 1.0,
                       "Prediction target — SYNTHETIC, not a calibrated probability"),
        ],
        target_column="FloodProbability",
        notes=(
            "Kaggle Playground Series S4E5 flood-probability dataset. "
            "DATA IS FULLY SYNTHETIC — features are generated, not observed. "
            "FloodProbability is approximately a normalised weighted sum of "
            "the 20 input features. Do NOT treat this as real-world ground truth. "
            "Use only to test pipeline mechanics and as a baseline benchmark."
        ),
    ),

    "imd_rainfall": DatasetSchema(
        name="imd_rainfall",
        required_columns=[
            ColumnSpec("latitude",    "f", False, -90.0,  90.0),
            ColumnSpec("longitude",   "f", False, -180.0, 180.0),
            ColumnSpec("date",        "M", False),
            ColumnSpec("rainfall_mm", "f", True,  0.0,  None),
        ],
        target_column=None,
        notes=(
            "IMD 0.25° daily gridded rainfall. REAL observational data. "
            "Temporal resolution: DAILY — cannot represent sub-daily intensity. "
            "Spatial resolution: 0.25° (~28 km). "
            "Do not interpolate to finer resolution without documenting assumptions."
        ),
    ),

    "copernicus_dem": DatasetSchema(
        name="copernicus_dem",
        required_columns=[
            ColumnSpec("latitude",       "f", False, -90.0, 90.0),
            ColumnSpec("longitude",      "f", False, -180.0, 180.0),
            ColumnSpec("elevation_m",    "f", True, None, 9000.0),
        ],
        optional_columns=[
            ColumnSpec("slope_deg",      "f", True, 0.0, 90.0),
            ColumnSpec("aspect_deg",     "f", True, 0.0, 360.0),
        ],
        target_column=None,
        notes=(
            "Copernicus DEM GLO-30, 30 m Digital Surface Model. "
            "Represents the surface including buildings and vegetation. "
            "Freely available with registration. "
            "Derive slope/aspect in the feature-engineering stage."
        ),
    ),

    "aei_processed": DatasetSchema(
        name="aei_processed",
        required_columns=[
            ColumnSpec("zone_id",        "O", False),
            ColumnSpec("event_id",       "O", True),
            ColumnSpec("data_source",    "O", False),
        ],
        optional_columns=[
            ColumnSpec("latitude",       "f", True, -90.0,  90.0),
            ColumnSpec("longitude",      "f", True, -180.0, 180.0),
            ColumnSpec("FloodProbability","f", True, 0.0,  1.0),
        ],
        target_column=None,
        notes="Internal processed dataset used between pipeline stages.",
    ),
}
