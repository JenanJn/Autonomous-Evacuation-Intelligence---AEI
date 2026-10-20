"""
AEI — pytest configuration and shared fixtures
================================================
All fixtures are labelled SYNTHETIC and must not be used as real-world
validation evidence.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make src importable without installing the package
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from tests.fixtures.make_synthetic_fixture import (
    make_clean_fixture,
    make_dirty_fixture,
    make_minimal_fixture,
    FEATURE_COLS,
)


# ---------------------------------------------------------------------------
# DataFrame fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def clean_df() -> pd.DataFrame:
    """200-row clean SYNTHETIC DataFrame matching kaggle_s4e5 schema."""
    return make_clean_fixture(n_rows=200, seed=42)


@pytest.fixture(scope="session")
def dirty_df() -> pd.DataFrame:
    """SYNTHETIC DataFrame with injected nulls, duplicates, out-of-range values."""
    return make_dirty_fixture(n_rows=50, seed=43)


@pytest.fixture(scope="session")
def minimal_df() -> pd.DataFrame:
    """5-row SYNTHETIC DataFrame for fast unit tests."""
    return make_minimal_fixture(n_rows=5)


@pytest.fixture
def clean_df_copy(clean_df) -> pd.DataFrame:
    """A fresh copy of clean_df for tests that mutate it."""
    return clean_df.copy()


@pytest.fixture
def dirty_df_copy(dirty_df) -> pd.DataFrame:
    """A fresh copy of dirty_df for tests that mutate it."""
    return dirty_df.copy()


# ---------------------------------------------------------------------------
# Path fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def simulated_dir(tmp_path_factory) -> Path:
    """Temporary directory for fixture CSV files written during tests."""
    return tmp_path_factory.mktemp("simulated")


@pytest.fixture(scope="session")
def clean_csv_path(simulated_dir, clean_df) -> Path:
    """Write clean_df to a temp CSV and return the path."""
    p = simulated_dir / "clean.csv"
    clean_df.to_csv(p, index=False)
    return p


@pytest.fixture(scope="session")
def dirty_csv_path(simulated_dir, dirty_df) -> Path:
    """Write dirty_df to a temp CSV and return the path."""
    p = simulated_dir / "dirty.csv"
    dirty_df.to_csv(p, index=False)
    return p
