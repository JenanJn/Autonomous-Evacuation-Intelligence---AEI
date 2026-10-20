# AEI — GIS & Routing Extension: Final Report

> **Data disclaimer:** Every number, route, risk score, shelter and road
> segment in this report is **SYNTHETIC**.  Nothing here represents a real
> city, a real flood event, or a validated evacuation plan.  The AI model
> was trained on a synthetic fixture dataset.  Do not use any output as
> operational emergency guidance.

---

## 1. Existing Files Preserved

All original files from the ZIP were preserved without modification.

| File / Directory | Status |
|---|---|
| `src/data_pipeline/ingestion.py` | Unchanged |
| `src/data_pipeline/cleaning.py` | Unchanged |
| `src/data_pipeline/feature_engineering.py` | Unchanged |
| `src/data_pipeline/__init__.py` | Unchanged |
| `src/prediction/train.py` | Unchanged |
| `src/prediction/predict.py` | Unchanged |
| `src/prediction/evaluate.py` | Unchanged |
| `src/prediction/model_loader.py` | Unchanged |
| `src/prediction/__init__.py` | Unchanged |
| `src/integration/schemas.py` | Unchanged |
| `src/integration/__init__.py` | Unchanged |
| `models/RandomForest_v0.1.0/` | Unchanged |
| `models/MeanBaseline_v0.1.0/` | Unchanged |
| `tests/conftest.py` | Unchanged |
| `tests/fixtures/make_synthetic_fixture.py` | Unchanged |
| `tests/test_ingestion.py` | Unchanged |
| `tests/test_cleaning.py` | Unchanged |
| `tests/test_feature_engineering.py` | Unchanged |
| `tests/test_schemas.py` | Unchanged |
| `tests/test_prediction.py` | Unchanged |
| `scripts/demo_pipeline.py` | Unchanged |
| `scripts/run_training.py` | Unchanged |
| `scripts/benchmark_inference.py` | Unchanged |
| `pytest.ini` | Unchanged |
| `README.md` | Unchanged |

---

## 2. New and Modified Files

### New source modules

| File | Purpose |
|---|---|
| `src/gis/__init__.py` | Package marker |
| `src/gis/network_loader.py` | Road-network loading (OSM / synthetic / GraphML), CRS handling, geometry, edge-state management |
| `src/routing/__init__.py` | Package marker |
| `src/routing/router.py` | Three routing modes (shortest, risk-aware, adaptive), EvacuationRouter class, cost function |
| `src/shelter/__init__.py` | Package marker |
| `src/shelter/shelter_manager.py` | Shelter registry, capacity tracking, greedy nearest-feasible allocation |
| `src/scenarios/__init__.py` | Package marker |
| `src/scenarios/synthetic_scenarios.py` | Seven deterministic synthetic scenarios |

### Modified source modules

| File | Change |
|---|---|
| `src/risk_engine/__init__.py` | Added docstring (was empty stub) |
| `src/risk_engine/risk_mapper.py` | **New file** — zone-to-road risk mapping, coverage reporting |

### New tests

| File | Tests added |
|---|---|
| `tests/test_gis.py` | 36 tests — network loading, validation, geometry, edge state |
| `tests/test_routing.py` | 48 tests — all three routing modes, cost formula, determinism |
| `tests/test_shelter.py` | 38 tests — shelter state, allocation, capacity, CSV loading |
| `tests/test_risk_mapper.py` | 35 tests — risk mapping, coverage, zone-node mapping |
| `tests/test_scenarios.py` | 42 tests — all 7 scenarios, determinism, all-scenarios runner |
| `tests/test_integration.py` | 32 tests — schema compatibility, full pipeline, dynamic replanning |

### New scripts

| File | Purpose |
|---|---|
| `scripts/demo_evacuation.py` | End-to-end demo: AI → risk → routing → shelter → replanning |

### Modified configuration

| File | Change |
|---|---|
| `requirements.txt` | Added `geopandas==0.14.4`, `osmnx==1.9.4`, `networkx==3.3` |

---

## 3. Test Results Before and After Changes

### Before (baseline from ZIP)

```
135 passed, 4 warnings in 12.29s
```

All 135 original tests passed without modification.

### After (full suite including new GIS/routing tests)

```
346 passed, 7 warnings in 9.94s
```

211 new tests added; 0 tests removed or weakened; 0 failures.

The 7 warnings are all identical:

```
InconsistentVersionWarning: Trying to unpickle estimator … from version 1.5.0
when using version 1.6.1.
```

This is a harmless sklearn version mismatch between the saved artefacts
(trained with sklearn 1.5.0) and the installed version (1.6.1).  All
prediction tests pass despite this warning.  To eliminate it, re-run
`python scripts/run_training.py` on the current environment.

---

## 4. Commands to Run the Complete Project

```bash
# 1. Install dependencies (from AEI/ directory)
pip install -r requirements.txt

# 2. Run the full test suite
cd AEI
pytest

# With coverage report
pytest --cov=src --cov-report=term-missing

# Skip slow/integration tests
pytest -m "not slow and not integration"

# 3. Run the original AI pipeline demo (synthetic data)
python scripts/demo_pipeline.py

# 4. Run the new end-to-end evacuation demo
python scripts/demo_evacuation.py

# 5. Train / refresh AI model artefacts
python scripts/run_training.py

# 6. Run the AI inference benchmark
python scripts/benchmark_inference.py
```

---

## 5. Example Route and Shelter-Assignment Output

The following is actual output from `scripts/demo_evacuation.py` on a
6-node synthetic grid graph (ALL DATA SYNTHETIC):

```
Stage 5+6: Routing — Shortest-Path and Risk-Aware

  A. Shortest-path (distance only, ignores risk)
    A→C shortest:
      Path          : A → B → C
      Distance      : 2400 m
      Total cost    : 2400 m
      Risk penalty  : 0 m
      Travel est.   : 173 s  (approx, not validated)

    A→F shortest:
      Path          : A → D → E → F
      Distance      : 3000 m

  B. Risk-aware routing (risk penalty = risk_score × 5000 m)
    A→C risk-aware:
      Path          : A → B → C
      Distance      : 2400 m
      Total cost    : 6814 m  (includes risk penalty)
      Risk penalty  : 4414 m

Stage 7: Shelter Allocation
  Total requested : 240
  Total admitted  : 240
  Total unassigned: 0
  Demand       Shelter     Admitted   Cost(m)
  ZONE_A       SH_C              80      6814
  ZONE_B       SH_C              60      3378
  ZONE_D       SH_F             100      6894

Stage 8: Road Closure + Dynamic Replanning
  Before closure:  A → B → C  (2400 m)
  Event: A-B blocked
  Replanned:       A → D → E → F → C  (3600 m)
  Distance increase: 1200 m

Stage 9: Shelter Capacity Event
  Event: SH_C closes
  New demand: 80 people from D
  Admitted  : 50   → SH_F
  Unassigned: 30   (SH_F full after 50)
```

---

## 6. Integration Contract: AI Module ↔ GIS Module

**Contract version:** `0.1.0` (matches `schemas.CONTRACT_VERSION`)

### Step-by-step data flow

```
AI module                         GIS module
─────────────────────────────────────────────────────────────────
predict.predict_batch(df, bundle)
  → HazardPredictionRecord
      .zone_id          ──────────► used as mapping key
      .predicted_value  ──────────► converted to risk_score
      .prediction_status            checked before use
      .model_version                forwarded to output records

Risk engine converts prediction to:
  RiskOutputRecord
      .zone_id          ──────────► matched to zone_node_map key
      .risk_score       ──────────► applied to edge["risk_score"]
      .risk_status      ──────────► non-OK records are skipped
      .risk_category    ──────────► display only, NOT used in cost

risk_mapper.apply_zone_node_mapping(G, records, zone_node_map)
  → sets edge["risk_score"] on all edges whose source node is
    in the zone

EvacuationRouter(G, RoutingConfig(mode=RISK_AWARE))
  → cost(edge) = length_m + risk_weight × risk_m_equiv × risk_score
  → unknown risk_score=None: handled by UnknownRiskPolicy
      CONSERVATIVE → treat as 1.0   (default — safest)
      NEUTRAL      → treat as 0.5
      OPTIMISTIC   → treat as 0.0

ShelterManager.allocate(demand, router)
  → greedy nearest-feasible assignment
  → unreachable shelters (inf routing cost) are skipped
  → unassigned demand reported explicitly
```

### Key field mapping

| AI field | GIS edge attribute | Notes |
|---|---|---|
| `RiskOutputRecord.zone_id` | `edge["zone_id"]` | Via zone→node map |
| `RiskOutputRecord.risk_score` | `edge["risk_score"]` | float [0,1] or None |
| `RiskOutputRecord.risk_status` | — | Non-OK records skipped |
| `HazardPredictionRecord.model_version` | forwarded to RiskOutputRecord | Provenance tracking |

### What the contract does NOT assume

- `risk_score` is NOT a calibrated probability.  It is a decision-support
  score derived from the AI model output.
- `FloodProbability` (model target) and `risk_score` are separate concepts.
- Unknown risk (`risk_score=None`) is NEVER silently treated as safe.
  The caller must explicitly choose OPTIMISTIC to treat it as zero risk.

### What requires spatial data to complete

The zone→node mapping (`zone_node_map: Dict[str, List[node_id]]`) must be
supplied by the caller.  This requires either:
- A spatial join between zone polygons (GeoJSON/Shapefile) and road-network
  nodes using GeoPandas.
- A manually curated lookup table for known study areas.

Until zone polygon data is available, use `apply_zone_node_mapping` with a
caller-supplied mapping, or `apply_uniform_risk` for synthetic testing.

---

## 7. Routing and Replanning Benchmark Results

Measured on a 6-node synthetic graph (200 repetitions, first call excluded
as warm-up). **These timings are NOT representative of production
performance on a real city-scale graph.**

```
Route     Reps    Total(ms)    Per call(ms)
A→C        200       52.53          0.26
A→F        200       61.75          0.31
D→C        200       55.95          0.28
B→F        200       56.61          0.28
```

Per-call latency is 0.26–0.31 ms on a 6-node graph.  Real city road
networks contain tens of thousands of nodes.  Dijkstra's algorithm scales
as O((V + E) log V); expect significantly higher latency at scale.
Use A* with a haversine heuristic for production city-scale routing.

For AI inference latency on the same hardware, see
`scripts/benchmark_inference.py`.  The model was benchmarked at
< 50 ms end-to-end for a batch of 50 records (synthetic data only).

---

## 8. Missing Datasets and Integration Requirements

| Requirement | Status | Notes |
|---|---|---|
| Real flood observation data | Not available | Kaggle S4E5 is synthetic; IMD/DEM download required |
| OSM road network for target city | Not downloaded | `network_loader.from_osm(query)` is ready; internet required |
| Zone polygon GeoJSON/Shapefile | Not available | Required for automatic zone→edge spatial join |
| Verified shelter locations | Not available | Synthetic locations used in all demos and tests |
| Real shelter capacities | Not available | Synthetic capacities used |
| Calibrated risk thresholds | Not calibrated | LOW/MODERATE/HIGH/CRITICAL thresholds are placeholders |
| Time-series weather forecast | Not implemented | Planned for Milestone 3 |
| Zone-to-road spatial join code | Interface ready | `apply_zone_node_mapping` accepts caller-supplied mapping |

---

## 9. Architecture Diagram (text)

```
                     ┌───────────────────────────────┐
                     │       AI Pipeline (existing)   │
                     │                               │
                     │  ingestion → cleaning →        │
                     │  feature_engineering →         │
                     │  RandomForest.predict()        │
                     │       ↓                        │
                     │  HazardPredictionRecord        │
                     │  (zone_id, predicted_value,    │
                     │   prediction_status)           │
                     └──────────────┬────────────────┘
                                    │
                     ┌──────────────▼────────────────┐
                     │       Risk Engine (new)        │
                     │                               │
                     │  predicted_value → risk_score  │
                     │  RiskOutputRecord              │
                     │  (zone_id, risk_score [0,1],  │
                     │   risk_category, risk_status)  │
                     └──────────────┬────────────────┘
                                    │
                     ┌──────────────▼────────────────┐
                     │    Risk Mapper (new)           │
                     │                               │
                     │  apply_zone_node_mapping()     │
                     │  zone_id → edge["risk_score"]  │
                     │  (requires zone→node map)      │
                     └──────────────┬────────────────┘
                                    │
          ┌─────────────────────────▼──────────────────────────┐
          │              Road Network Graph (new)               │
          │                                                    │
          │  nx.MultiDiGraph  nodes: {x, y}                    │
          │  edges: {length_m, road_type, blocked,             │
          │          risk_score, zone_id}                      │
          │  Source: osmnx / synthetic / GraphML               │
          └──────────┬──────────────────────────┬─────────────┘
                     │                          │
          ┌──────────▼──────────┐    ┌──────────▼──────────────┐
          │   EvacuationRouter  │    │    ShelterManager        │
          │   (new)             │    │    (new)                 │
          │                    │    │                          │
          │  Mode A: shortest  │    │  snap_to_network()       │
          │  Mode B: risk-aware│    │  allocate(demand,router) │
          │  Mode C: adaptive  │    │  greedy nearest-feasible │
          │  block_edge()       │    │  capacity tracking       │
          │  replan()           │    │  unassigned reporting    │
          └─────────────────────┘    └──────────────────────────┘
```

---

## 10. Limitations and Next Steps

### Current limitations

1. **Synthetic data only.** The AI model was trained on a synthetic
   200-row fixture.  Predictions have no relationship to real flood risk
   anywhere.  All metrics, routes and allocations are for pipeline
   demonstration only.

2. **No real road network.** All routing demos use a 6-node in-memory
   graph.  `from_osm()` is implemented but requires internet access and a
   valid place query.

3. **Dijkstra, not A*.** The router uses `nx.dijkstra_path`.  For
   city-scale graphs (10 k+ nodes) this will be slow.  A* with a haversine
   heuristic would be significantly faster.

4. **Zone→node mapping is caller-supplied.** Automatic spatial join between
   zone polygons and road nodes requires zone GeoJSON/Shapefile data that
   is not in this repository.

5. **Greedy allocation is not optimal.** The shelter assignment algorithm is
   greedy nearest-feasible.  Global optimum (minimise total travel cost
   subject to capacity constraints) is NP-hard; a more sophisticated
   assignment (e.g. min-cost flow) could be added.

6. **Travel times are approximate.** Speed estimates use a fixed table by
   road type.  Real evacuation speeds depend on traffic, time of day,
   vehicle type and emergency conditions.

7. **Static snapshot only.** There is no temporal model.  Risk does not
   evolve over time within a single planning cycle.

8. **Risk thresholds are uncalibrated.** LOW / MODERATE / HIGH / CRITICAL
   cutoffs are illustrative placeholders.  Domain-expert calibration against
   real event data is required before operational use.

9. **Shelter data is entirely synthetic.** Locations, capacities and names
   are made up.  Real shelter data must come from official sources.

10. **No mobile UI integration.** The React Native component is out of scope
    for this module.

### Recommended next steps (Milestone 3+)

- Download real Kaggle S4E5 / IMD / DEM data and retrain the model.
- Implement GeoPandas spatial join for zone→road mapping.
- Replace Dijkstra with A* for city-scale graphs.
- Add temporal risk propagation (risk decays or grows over time).
- Calibrate risk thresholds with domain experts.
- Implement min-cost flow or Hungarian algorithm for shelter allocation.
- Integrate verified shelter dataset from official emergency-planning sources.
- Add REST API wrapper around `predict_batch` + `allocate` for mobile UI.
- Benchmark on a real city OSM graph and establish latency SLAs.

---

*Report generated automatically at project completion.
All data is synthetic unless explicitly stated otherwise.*
