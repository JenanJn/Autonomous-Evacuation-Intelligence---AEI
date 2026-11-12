# AEI mobile evacuation update

Start with [README-LOCATION-INDEPENDENT.md](README-LOCATION-INDEPENDENT.md) for the current Home → disaster/location → real-street routing flow, phone/APK instructions, operations dashboard and verification limits. The app remains on SDK 53. Your original data-science project is retained below.

# Autonomous Evacuation Intelligence (AEI) — Python AI Component

> **MCA AI & Data Science project.**
> This repository contains the Python and AI component only.
> The GIS routing engine, shelter allocation, and mobile UI are separate.

---

## What this component does

AEI predicts a flood-hazard measure for geographic zones, scores hazard risk,
and exports structured outputs for a GIS-based evacuation engine to use when
calculating routes and assigning shelters.

Workflow: **PERCEIVE → PREDICT → ASSESS → DECIDE → ROUTE → ADAPT**

This component covers PERCEIVE, PREDICT, and ASSESS.
DECIDE, ROUTE, and ADAPT are the responsibility of the GIS teammate.

---

## Project structure

```
AEI/
├── data/
│   ├── raw/            Real downloaded datasets (not committed to git)
│   ├── processed/      Cleaned, feature-engineered data (reproducible)
│   └── simulated/      SYNTHETIC test fixtures only
├── notebooks/          Exploratory analysis notebooks
├── scripts/
│   └── demo_pipeline.py  End-to-end pipeline demonstration
├── src/
│   ├── data_pipeline/
│   │   ├── ingestion.py          Load + validate raw data
│   │   ├── cleaning.py           Imputation, deduplication, clipping
│   │   └── feature_engineering.py  Composite + scaled features
│   ├── prediction/
│   │   ├── train.py              Model training (Milestone 2)
│   │   ├── evaluate.py           Evaluation metrics (Milestone 2)
│   │   ├── predict.py            Inference (Milestone 2)
│   │   └── model_loader.py       Load saved model artefacts (Milestone 2)
│   ├── risk_engine/
│   │   ├── scoring.py            Hazard → risk score (Milestone 2)
│   │   └── validation.py         Risk-output validation (Milestone 2)
│   └── integration/
│       ├── schemas.py            Pydantic output schemas for GIS contract
│       └── export.py             CSV / JSON export (Milestone 2)
├── models/             Saved model artefacts (not committed to git)
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   └── make_synthetic_fixture.py
│   ├── test_ingestion.py
│   ├── test_cleaning.py
│   ├── test_feature_engineering.py
│   └── test_schemas.py
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## Setup

### Requirements

- Python 3.11 or higher
- Windows / Linux / macOS

### Install dependencies

```bash
cd AEI
pip install -r requirements.txt
```

Geospatial libraries (`rasterio`, `netCDF4`) are only needed when you work
with DEM or IMD NetCDF data.  The core pipeline and tests work with pandas
and scikit-learn only.

---

## Running the pipeline

### Run the end-to-end demo on synthetic data

```bash
python scripts/demo_pipeline.py
```

**Warning:** this demo uses SYNTHETIC data only.
The numbers it prints are not real accuracy scores.

### Run tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=src --cov-report=term-missing
```

Run only fast unit tests (skip slow/integration markers):

```bash
pytest -m "not slow and not integration"
```

---

## Data sources

### Candidate sources investigated in Milestone 1

| Source | Type | Resolution | Target variable | Status |
|---|---|---|---|---|
| Kaggle Playground S4E5 | SYNTHETIC tabular | Per event | FloodProbability (0–1) | Schema documented; download required |
| IMD Gridded Rainfall | REAL NetCDF | 0.25° daily | rainfall_mm | Ingestion code ready; download required |
| Copernicus DEM GLO-30 | REAL GeoTIFF | 30 m | elevation_m | Ingestion code ready; registration required |
| WorldPop India | ESTIMATED GeoTIFF | 100 m | population/pixel | For evacuation demand, not flood physics |
| OpenStreetMap India | REAL | Variable | Road network | Teammate's responsibility |

### Download instructions

**Kaggle Playground S4E5**
1. Go to https://www.kaggle.com/competitions/playground-series-s4e5/data
2. Accept the competition rules and download `train.csv`, `test.csv`.
3. Place them in `data/raw/kaggle_s4e5/`.

**IMD Gridded Rainfall**
1. Go to https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html
2. Register and download annual NetCDF files.
3. Place in `data/raw/imd_rainfall/`.

**Copernicus DEM GLO-30**
1. Register at https://dataspace.copernicus.eu/
2. Download tiles covering your study area.
3. Place in `data/raw/copernicus_dem/`.

---

## Integration contract with GIS module

**Contract version:** `0.1.0`

The GIS routing engine consumes two output types:

### HazardPredictionRecord (JSON / CSV)

| Field | Type | Notes |
|---|---|---|
| `zone_id` | string | Stable geographic zone ID — must match GIS layer |
| `prediction_time` | ISO-8601 string | When prediction was generated |
| `target_name` | string | e.g. `"FloodProbability"` |
| `predicted_value` | float or null | Null when status ≠ OK |
| `target_unit` | string | e.g. `"dimensionless_0_to_1"` |
| `forecast_horizon` | string | e.g. `"static_snapshot"`, `"6h_ahead"` |
| `model_version` | string | Semantic version of model artefact |
| `data_timestamp` | ISO-8601 or null | Timestamp of most recent input |
| `prediction_status` | enum | `OK`, `NO_DATA`, `STALE_DATA`, `MODEL_ERROR`, `INVALID_INPUT` |

### RiskOutputRecord (JSON / CSV)

| Field | Type | Notes |
|---|---|---|
| `zone_id` | string | Must match GIS layer |
| `risk_score` | float [0,1] or null | Decision-support score, NOT a probability |
| `risk_category` | enum | `LOW`, `MODERATE`, `HIGH`, `CRITICAL`, `UNKNOWN` |
| `data_freshness` | ISO-8601 duration or null | e.g. `"PT1H"` |
| `risk_status` | enum | `OK`, `NO_DATA`, `STALE_DATA`, `SCORING_ERROR`, `INVALID_INPUT` |
| `contributing_factors` | list of strings | Which inputs drove the score |

**Important:** `risk_score` is a decision-support score derived from model
predictions and data freshness.  It is NOT a calibrated probability.
Do not label it as a probability in the GIS UI without calibration.

---

## Assumptions and limitations

### Milestone 1 (current)

1. **No real dataset available yet.**
   The pipeline has been tested on a SYNTHETIC fixture only.
   All performance metrics from this milestone are synthetic.

2. **Kaggle S4E5 is synthetic, not observational.**
   Its `FloodProbability` target is approximately a normalised weighted sum
   of 20 input indicators.  It does not represent real flood measurements.
   It is useful for testing pipeline mechanics and as a sanity-check baseline,
   but model accuracy on it does not predict accuracy on real data.

3. **IMD rainfall is daily, not sub-daily.**
   The 0.25° daily gridded product cannot represent rainfall intensity,
   storm duration, or 10-minute accumulation.  Do not treat it as fine-grained
   event data.

4. **DEM gives surface elevation, not hydraulic routing.**
   Copernicus DEM GLO-30 includes buildings and vegetation.  Deriving flood
   depth from it alone requires hydraulic modelling that is outside this
   component's scope.

5. **City-independent ≠ universally accurate.**
   The pipeline accepts different geographic datasets without hardcoded city
   names.  This does not mean the model will perform equally well everywhere.
   Accuracy must be evaluated on each new geographic area.

6. **Risk-score thresholds are placeholders.**
   The LOW / MODERATE / HIGH / CRITICAL thresholds in `schemas.py` and the
   demo script are illustrative.  They must be calibrated with domain experts
   and validated against real event data before operational use.

7. **No temporal modelling yet.**
   Features are static per-event snapshots.  Time-series forecasting
   (e.g. 6 h ahead) requires a temporal model and is planned for Milestone 3.

### What this component does NOT do

- Calculate evacuation routes (GIS teammate's responsibility).
- Select or score shelters (GIS teammate's responsibility).
- Provide a mobile UI (React Native — separate component).
- Guarantee accuracy for any specific city or flood event.

---

## Decisions remaining after Milestone 1

1. Download and inspect real Kaggle S4E5 or IMD data — confirm schema match.
2. Agree final `zone_id` naming convention with GIS teammate.
3. Define the train/validation/test split strategy (time-based vs event-based).
4. Calibrate risk-score thresholds with domain experts.
5. Decide whether to use IMD + DEM features alongside S4E5 indicators.
6. Benchmark inference latency on actual project hardware.

---

## Reproducibility

All random operations use explicit seeds (default: `RNG_SEED = 42`).
To regenerate synthetic fixtures with the same values:

```bash
python tests/fixtures/make_synthetic_fixture.py
```

Model artefacts (Milestone 2+) will be saved with their random seed,
dataset version, and scikit-learn version recorded in a companion JSON file.

