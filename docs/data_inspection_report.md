# AEI — Data Inspection Report (Milestone 1)

**Date:** 2026-10-19
**Author:** AEI Python AI component
**Status:** Milestone 1 — no real data downloaded yet

---

## 1. Repository state at inspection

The workspace was empty at the start of Milestone 1.
No existing code, datasets, or model artefacts were found.
This report documents the results of researching candidate data sources
and building the initial pipeline infrastructure.

---

## 2. Candidate datasets inspected

### 2.1 IMD Gridded Rainfall (0.25° daily)

| Attribute | Value |
|---|---|
| URL | https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html |
| Format | NetCDF |
| Spatial resolution | 0.25° (~28 km per grid cell) |
| Temporal resolution | **Daily** |
| Coverage | India, 1901–present |
| Variable | `RAINFALL` (mm/day) |
| License | Free for research; registration required |
| Provenance label | **REAL** |

**Key limitations:**
- Daily aggregates only — no sub-daily rainfall intensity, no storm-duration data.
- At 0.25° resolution, a single cell covers ~780 km². Fine-scale urban drainage effects are not captured.
- Cannot be used as a proxy for 10-minute intensity or peak flow.
- Spatial interpolation to finer resolution must be documented as an assumption, not presented as observed data.

**Intended use in AEI:**
Rainfall accumulation features (3-day, 7-day windows) once data is downloaded.
Not suitable as the primary prediction target — it is an input feature.

---

### 2.2 WorldPop India Population (100 m)

| Attribute | Value |
|---|---|
| URL | https://hub.worldpop.org/geodata/summary?id=73807 |
| Format | GeoTIFF |
| Spatial resolution | ~100 m (3 arc-seconds) |
| Temporal coverage | Annual estimates 2000–2020 |
| Variable | People per pixel |
| License | Creative Commons Attribution 4.0 |
| Provenance label | **ESTIMATED** (model-derived, not direct census) |

**Key limitations:**
- Population density is derived from census data disaggregated by machine learning — it carries uncertainty.
- Most recent year is 2020; not updated in real time.
- Population data informs evacuation demand and route prioritisation.
  It is NOT a flood physics feature and should not be used as a predictor of flood occurrence.

**Intended use in AEI:**
Evacuation demand weighting by zone. To be consumed by the GIS routing engine,
not used as a feature in the flood prediction model.

---

### 2.3 Copernicus DEM GLO-30

| Attribute | Value |
|---|---|
| URL | https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM |
| Format | GeoTIFF (tiles) |
| Spatial resolution | 30 m |
| Coverage | Global (Armenia and Azerbaijan excluded from free tier) |
| Variable | Elevation in metres (Digital Surface Model — includes buildings and vegetation) |
| License | Free and open with registration |
| Provenance label | **REAL** |

**Key limitations:**
- This is a **Digital Surface Model (DSM)**, not a bare-earth Digital Terrain Model (DTM).
  It includes building heights and vegetation canopy. For hydraulic modelling, a DTM is preferable.
- Tile download required per geographic area; processing large areas is memory-intensive.
- Slope and Topographic Wetness Index (TWI) must be derived computationally — they are not provided.

**Derived features planned:**
- `slope_deg` — from DEM gradient
- `elevation_category` — low / medium / high
- Approximate TWI = ln(upslope_area / tan(slope))

**Intended use in AEI:**
Terrain features (slope, elevation) as flood-susceptibility predictors.
Ingestion code implemented in `ingestion.py::load_geotiff_raster`.

---

### 2.4 Kaggle Playground Series S4E5 — Flood Prediction

| Attribute | Value |
|---|---|
| URL | https://www.kaggle.com/competitions/playground-series-s4e5/data |
| Format | CSV |
| Rows | ~1.1 million (train) |
| Features | 20 synthetic indicator columns (0–10 scale each) |
| Target | `FloodProbability` — normalised float [0, 1] |
| Provenance label | **SYNTHETIC** |
| License | Kaggle competition rules; download requires account |

**Feature schema:**

| Feature | Description | Scale |
|---|---|---|
| MonsoonIntensity | Synthetic indicator of monsoon strength | 0–10 |
| TopographyDrainage | Drainage capacity of terrain | 0–10 |
| RiverManagement | Quality of river management systems | 0–10 |
| Deforestation | Degree of forest loss | 0–10 |
| Urbanization | Degree of urban sprawl | 0–10 |
| ClimateChange | Exposure to climate change effects | 0–10 |
| DamsQuality | Quality of dam infrastructure | 0–10 |
| Siltation | Siltation in water channels | 0–10 |
| AgriculturalPractices | Risk from agricultural water use | 0–10 |
| Encroachments | Encroachments on water bodies | 0–10 |
| IneffectiveDisasterPrep | Lack of disaster preparedness | 0–10 |
| WaterBodyChanges | Changes to water body extent | 0–10 |
| DeterioratingInfrastructure | Degradation of flood infrastructure | 0–10 |
| PopulationScore | Population exposure indicator | 0–10 |
| WetlandLoss | Loss of wetland buffers | 0–10 |
| InadequatePlanning | Urban planning deficiencies | 0–10 |
| PoliticalFactors | Governance and political risk | 0–10 |
| DrainageSystems | Effectiveness of drainage networks | 0–10 |
| CoastalVulnerability | Exposure to coastal flooding | 0–10 |
| Landslides | Landslide susceptibility | 0–10 |

**Target variable:** `FloodProbability`

Structure (from published analyses): approximately a normalised weighted sum
of the 20 input columns with added noise.  It is **not** a physical flood
measurement and **not** a calibrated probability from observational data.

**Key limitations:**
- All 1.1M rows are generated, not measured.
- There are no geographic coordinates, timestamps, or spatial identifiers.
- The target is a data artefact, not a real flood observation.
- Accuracy on this dataset does not predict accuracy on real-world data.
- Cannot be used to validate the model for any specific city.

**Intended use in AEI:**
Initial pipeline testing and sanity-check baseline only.
Clearly labelled SYNTHETIC in all outputs.
Will be supplemented or replaced with real data (IMD + DEM) once downloaded.

---

### 2.5 OpenStreetMap — India Road Network

| Attribute | Value |
|---|---|
| URL | https://download.geofabrik.de/asia/india.html |
| Format | PBF / Shapefile |
| Coverage | India road network, POIs, buildings |
| License | ODbL 1.0 (open) |
| Provenance label | **REAL** (volunteered geographic information) |

**Intended use in AEI:**
This dataset is **not** used by the Python AI component.
It is the responsibility of the GIS teammate for road-network construction,
route calculation, and shelter location.

---

## 3. Prediction target selection

### Decision: FloodProbability (regression)

**Recommended initial target:** `FloodProbability` from the Kaggle S4E5 dataset.

**Justification:**

1. The schema is well-defined, documented, and immediately usable for pipeline testing.
2. The regression formulation (predicting a continuous 0–1 hazard score) maps
   directly to the risk-scoring module's needs.
3. Classification would require a binary threshold that is not scientifically
   justified without real observational data.
4. The target variable is produced by a deterministic process (weighted sum),
   so baseline performance will be high — but this is expected and documented.

**Forecast horizon:** Static per-event snapshot (no temporal dimension in S4E5).
When IMD rainfall time series are available, the horizon can be extended to
multi-day accumulation windows.

**Critical caveats:**
- This target is SYNTHETIC. High accuracy on it means the pipeline is
  mechanically correct, not that the model predicts real floods.
- When real data becomes available, the target variable must be re-evaluated.
  Candidate real targets: binary flood/no-flood label from historical records,
  or continuous water-level observations from gauge stations.
- Do not report S4E5 accuracy as real-world performance.

---

## 4. Data readiness assessment

| Component | Status | Blocker |
|---|---|---|
| Synthetic fixture (pipeline testing) | **Ready** | None |
| Kaggle S4E5 CSV | **Schema documented** | Kaggle download required |
| IMD Rainfall NetCDF | **Ingestion code ready** | Download + registration |
| Copernicus DEM GeoTIFF | **Ingestion code ready** | Download + registration |
| WorldPop GeoTIFF | **Not ingested yet** | Low priority (not a flood predictor) |
| OSM road network | **Not applicable** | GIS teammate's responsibility |

---

## 5. Architecture decisions

### City-independent design

The pipeline has no hardcoded city names or geographic coordinates.
- `zone_id` is a caller-supplied stable identifier.
- All geographic handling is explicit (lat/lon stored as columns, CRS documented).
- The schema registry (`ingestion.py::SCHEMA_REGISTRY`) can be extended for
  new geographic areas without touching pipeline logic.

### Leakage prevention

- `fit_cleaning_pipeline` computes medians on the training split only.
- `fit_feature_pipeline` fits the StandardScaler on the training split only.
- The fitted stats objects (`CleaningStats`, `FeaturePipelineStats`) are
  designed to be serialised alongside the model artefact.
- Tests verify that the test set uses training-set statistics.

### Data provenance labelling

Every DataFrame carries `df.attrs["_data_source"]` ∈ {REAL, ESTIMATED, SIMULATED, SYNTHETIC}.
This label is set by the caller at ingestion time and must not be changed
downstream without documenting the reason.

### Integration contract

Output schemas use Pydantic v2 for validation, JSON serialisation, and
clear error messages.  Contract version `0.1.0` is embedded in every record.
The GIS module must check `prediction_status` / `risk_status` before
using numeric values.

---

## 6. What was implemented in Milestone 1

| Deliverable | File | Status |
|---|---|---|
| Project directory structure | AEI/ | Done |
| Dependency list | requirements.txt | Done |
| Ingestion module | src/data_pipeline/ingestion.py | Done |
| Cleaning module | src/data_pipeline/cleaning.py | Done |
| Feature engineering | src/data_pipeline/feature_engineering.py | Done |
| Integration schemas | src/integration/schemas.py | Done |
| Synthetic fixture generator | tests/fixtures/make_synthetic_fixture.py | Done |
| Unit tests — ingestion | tests/test_ingestion.py | Done |
| Unit tests — cleaning | tests/test_cleaning.py | Done |
| Unit tests — feature engineering | tests/test_feature_engineering.py | Done |
| Unit tests — schemas | tests/test_schemas.py | Done |
| Pipeline demo script | scripts/demo_pipeline.py | Done |
| README | README.md | Done |
| Data inspection report | docs/data_inspection_report.md | This file |

---

## 7. Unresolved decisions

1. **Real dataset:** Kaggle S4E5 train.csv must be downloaded and inspected.
   Confirm that the 20 feature columns match the schema in `SCHEMA_REGISTRY`.
2. **Zone ID convention:** Agree with GIS teammate on the exact format for
   `zone_id` (e.g. administrative district code, grid cell ID, custom string).
3. **Train/validation/test split:** S4E5 has no timestamps — a random split
   is acceptable for the synthetic benchmark.  For real IMD data, use a
   time-based split (train on earlier years, test on most recent).
4. **Risk-score thresholds:** LOW/MODERATE/HIGH/CRITICAL boundaries are
   placeholders.  Must be calibrated with domain experts.
5. **Temporal features:** Multi-day rainfall accumulation windows require
   aligned timestamps — not available in the S4E5 dataset.
6. **Hardware benchmarking:** Inference latency targets (< 1 s, < 3 s) have
   not been measured yet.  Benchmark after Milestone 2 model training.

---

## 8. Recommended next step (Milestone 2)

1. Download Kaggle S4E5 `train.csv` and place it in `data/raw/kaggle_s4e5/`.
2. Run `scripts/demo_pipeline.py` with the real file.
3. Implement `src/prediction/train.py` — fit a baseline (mean predictor)
   and a Random Forest regressor on the cleaned feature matrix.
4. Evaluate with MAE and RMSE using a time/event-agnostic held-out split
   (since S4E5 has no temporal structure).
5. Save the trained model and `CleaningStats` + `FeaturePipelineStats` to `models/`.
6. Implement `src/prediction/predict.py` for inference.
7. Benchmark loading, preprocessing, and inference latency separately.
