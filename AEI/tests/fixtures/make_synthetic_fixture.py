"""
AEI — Test Fixtures: Synthetic Dataset Generator
==================================================
Generates clearly-labelled SYNTHETIC fixtures for pipeline testing.

IMPORTANT — Scientific integrity notice
-----------------------------------------
All data produced by this script is SYNTHETIC.
* It is generated from a pseudo-random number generator with a fixed seed.
* It follows the Kaggle Playground S4E5 schema to test pipeline mechanics.
* It is NOT real observational data.
* It MUST NOT be used as evidence of real-world model accuracy.
* Files are saved to data/simulated/ NOT data/raw/ to make provenance clear.

Run this script directly to regenerate fixtures:
    python tests/fixtures/make_synthetic_fixture.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running from any working directory
_ROOT = Path(__file__).resolve().parents[2]   # AEI/
sys.path.insert(0, str(_ROOT / "src"))

SIMULATED_DIR = _ROOT / "data" / "simulated"
SIMULATED_DIR.mkdir(parents=True, exist_ok=True)

# Random seed — fixed for reproducibility
RNG_SEED = 42

FEATURE_COLS = [
    "MonsoonIntensity",
    "TopographyDrainage",
    "RiverManagement",
    "Deforestation",
    "Urbanization",
    "ClimateChange",
    "DamsQuality",
    "Siltation",
    "AgriculturalPractices",
    "Encroachments",
    "IneffectiveDisasterPrep",
    "WaterBodyChanges",
    "DeterioratingInfrastructure",
    "PopulationScore",
    "WetlandLoss",
    "InadequatePlanning",
    "PoliticalFactors",
    "DrainageSystems",
    "CoastalVulnerability",
    "Landslides",
]


def make_clean_fixture(n_rows: int = 200, seed: int = RNG_SEED) -> pd.DataFrame:
    """
    Generate a clean synthetic DataFrame with:
    - 20 indicator columns (float, 0-10 scale)
    - FloodProbability target (float, 0-1)
    - zone_id and event_id identifiers

    The target is a normalised weighted sum of the features, matching the
    known structure of the Kaggle S4E5 dataset.  It is NOT a real measured
    flood probability.

    Parameters
    ----------
    n_rows : int
    seed : int

    Returns
    -------
    pd.DataFrame  with df.attrs["_data_source"] = "SYNTHETIC"
    """
    rng = np.random.default_rng(seed)

    data: dict = {}
    data["id"] = np.arange(1, n_rows + 1)
    data["zone_id"] = [f"ZONE_{i:04d}" for i in range(1, n_rows + 1)]
    data["event_id"] = [f"EVT_{i:04d}" for i in range(1, n_rows + 1)]

    # Features: uniform(0, 10), rounded to 2 decimal places
    for col in FEATURE_COLS:
        data[col] = np.round(rng.uniform(0.0, 10.0, n_rows), 2)

    feature_matrix = np.column_stack([data[c] for c in FEATURE_COLS])
    # Target: normalised sum (mimics S4E5 structure) + small noise
    raw_sum = feature_matrix.sum(axis=1)
    max_possible = 10.0 * len(FEATURE_COLS)
    noise = rng.normal(0, 0.02, n_rows)
    target = np.clip(raw_sum / max_possible + noise, 0.0, 1.0)
    data["FloodProbability"] = np.round(target, 4)

    df = pd.DataFrame(data)
    df.attrs["_data_source"] = "SYNTHETIC"
    df.attrs["_source_file"] = __file__
    df.attrs["_schema_name"] = "kaggle_s4e5"
    return df


def make_dirty_fixture(n_rows: int = 50, seed: int = RNG_SEED + 1) -> pd.DataFrame:
    """
    Generate a synthetic DataFrame with intentional data-quality problems:
    - ~10% nulls in MonsoonIntensity
    - ~5% duplicate rows
    - 3 out-of-range values (> 10) in Urbanization
    - Missing FloodProbability in 3 rows

    Used to verify that cleaning.py handles each case correctly.
    """
    rng = np.random.default_rng(seed)

    df = make_clean_fixture(n_rows=n_rows, seed=seed)

    # Inject nulls
    null_idx = rng.choice(n_rows, size=max(1, n_rows // 10), replace=False)
    df.loc[null_idx, "MonsoonIntensity"] = np.nan

    # Inject out-of-range values
    oor_idx = rng.choice(n_rows, size=3, replace=False)
    df.loc[oor_idx, "Urbanization"] = rng.uniform(11.0, 15.0, 3)

    # Inject duplicate rows
    dup_count = max(1, n_rows // 20)
    dup_idx = rng.choice(n_rows, size=dup_count, replace=False)
    df = pd.concat([df, df.iloc[dup_idx]], ignore_index=True)

    # Inject missing targets
    target_null_idx = rng.choice(len(df), size=3, replace=False)
    df.loc[target_null_idx, "FloodProbability"] = np.nan

    df.attrs["_data_source"] = "SYNTHETIC"
    return df


def make_minimal_fixture(n_rows: int = 5) -> pd.DataFrame:
    """
    Return a tiny 5-row clean fixture for fast unit tests.
    All values are hand-crafted for predictability.
    """
    rows = []
    for i in range(n_rows):
        row = {col: float(i + 1) for col in FEATURE_COLS}
        row["id"] = i + 1
        row["zone_id"] = f"ZONE_{i+1:04d}"
        row["event_id"] = f"EVT_{i+1:04d}"
        row["FloodProbability"] = round((i + 1) / (n_rows * 2), 4)
        rows.append(row)
    df = pd.DataFrame(rows)
    df.attrs["_data_source"] = "SYNTHETIC"
    return df


def save_fixtures() -> None:
    """Save all fixtures to data/simulated/."""
    clean = make_clean_fixture()
    dirty = make_dirty_fixture()
    minimal = make_minimal_fixture()

    clean_path = SIMULATED_DIR / "synthetic_clean_200.csv"
    dirty_path = SIMULATED_DIR / "synthetic_dirty_50.csv"
    minimal_path = SIMULATED_DIR / "synthetic_minimal_5.csv"

    clean.to_csv(clean_path, index=False)
    dirty.to_csv(dirty_path, index=False)
    minimal.to_csv(minimal_path, index=False)

    print(f"[SYNTHETIC] Clean fixture:   {clean_path}  ({len(clean)} rows)")
    print(f"[SYNTHETIC] Dirty fixture:   {dirty_path}  ({len(dirty)} rows)")
    print(f"[SYNTHETIC] Minimal fixture: {minimal_path} ({len(minimal)} rows)")
    print()
    print("WARNING: These are SYNTHETIC fixtures for pipeline testing only.")
    print("         Do NOT use these results as evidence of real-world accuracy.")


if __name__ == "__main__":
    save_fixtures()
