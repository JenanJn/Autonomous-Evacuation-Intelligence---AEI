"""
AEI — End-to-End Evacuation Demo
==================================
Demonstrates the complete pipeline from AI risk predictions through
GIS routing to shelter allocation and dynamic replanning.

Pipeline stages demonstrated
-----------------------------
  1. AI Prediction Interface  — load saved RandomForest model and
                                generate synthetic HazardPredictionRecords
  2. Risk Assessment          — convert predictions to RiskOutputRecords
  3. Zone-to-Road Mapping     — apply zone risk scores to road-network edges
  4. Road-Network Loading     — build a synthetic configurable road graph
  5. Shortest-Path Routing    — baseline route (mode A)
  6. Risk-Aware Routing       — risk-penalised route (mode B)
  7. Shelter Allocation       — capacity-aware assignment
  8. Road Closure Event       — block a road and replan (mode C)
  9. Shelter Capacity Event   — close a shelter and reassign
 10. Summary & Benchmark      — timing and output summary

DATA SOURCE: ALL SYNTHETIC
--------------------------
* Road network is generated in memory — NOT a real place.
* Predictions come from the synthetic-fixture-trained RandomForest.
* Risk scores are derived from synthetic flood-probability values.
* Shelter locations and capacities are made up for this demo.
* DO NOT use any output here as a real-world routing decision.
* DO NOT claim these routes are safe or optimal for a real emergency.

Run from AEI/ directory:
    python scripts/demo_evacuation.py
"""
from __future__ import annotations

import logging
import pathlib
import sys
import time

_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests"))

logging.basicConfig(level=logging.WARNING)   # suppress INFO during demo

import numpy as np
import pandas as pd

# ── AI modules (existing, unchanged) ─────────────────────────────────────
from data_pipeline.ingestion import load_csv
from fixtures.make_synthetic_fixture import SIMULATED_DIR, make_clean_fixture
from prediction.model_loader import load_model_bundle
from prediction.predict import predict_batch

# ── Integration schemas (existing, unchanged) ─────────────────────────────
from integration.schemas import (
    HazardPredictionRecord,
    PredictionStatus,
    RiskOutputRecord,
)

# ── New GIS / routing / shelter / risk modules ────────────────────────────
from gis.network_loader import (
    from_synthetic,
    get_graph_summary,
    validate_graph,
)
from routing.router import (
    EvacuationRouter,
    RouteResult,
    RoutingConfig,
    RoutingMode,
    UnknownRiskPolicy,
)
from risk_engine.risk_mapper import (
    apply_zone_node_mapping,
    build_synthetic_risk_records,
    get_risk_coverage,
)
from risk_engine.scoring import (
    CategoryThresholds,
    DEFAULT_THRESHOLDS,
    SCORING_METHOD_PROXY,
    ScoredRiskRecord,
    extract_risk_records,
    score_batch,
)
from risk_engine.validation import (
    BatchValidationResult,
    DuplicateZonePolicy,
    validate_batch,
)
from shelter.shelter_manager import (
    Shelter,
    ShelterManager,
    ShelterStatus,
    load_shelters_from_list,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print()
    print("=" * 68)
    print(f"  {title}")
    print("=" * 68)


def subsection(title: str) -> None:
    print(f"\n  ── {title}")


def _print_route(label: str, r: RouteResult) -> None:
    if r.feasible:
        print(f"    {label}:")
        print(f"      Path          : {' → '.join(str(n) for n in r.path)}")
        print(f"      Distance      : {r.total_length_m:.0f} m")
        print(f"      Total cost    : {r.total_cost:.0f} m  "
              f"(includes risk penalty)")
        print(f"      Risk penalty  : {r.total_risk_penalty_m:.0f} m "
              f"(risk×5000m/unit)")
        print(f"      Travel est.   : {r.estimated_travel_time_s:.0f} s  "
              f"(approx, not validated)")
        print(f"      Replanned     : {r.replanned}")
        if r.notes:
            for n in r.notes:
                print(f"      NOTE: {n}")
    else:
        print(f"    {label}: INFEASIBLE")
        for n in r.notes:
            print(f"      NOTE: {n}")


# ---------------------------------------------------------------------------
# Stage 1 — AI predictions
# ---------------------------------------------------------------------------

def stage_ai_predictions():
    section("Stage 1: AI Prediction Interface  [SYNTHETIC DATA]")

    # Load or train model
    artefact_dir = _ROOT / "models" / "RandomForest_v0.1.0"
    if not artefact_dir.exists():
        print("  Model artefact not found — training now on synthetic fixture ...")
        from prediction.train import run_training_pipeline
        from prediction.model_loader import metadata_from_training_result, save_model_bundle
        df = make_clean_fixture(n_rows=200, seed=42)
        df.attrs["_data_source"] = "SYNTHETIC"
        result = run_training_pipeline(df)
        meta = metadata_from_training_result(result, "RandomForest", "0.1.0")
        save_model_bundle(result.rf_model, result.cleaning_stats,
                          result.feature_stats, meta,
                          _ROOT / "models", overwrite=True)

    bundle = load_model_bundle(artefact_dir)
    print(f"  Model : {bundle.metadata.model_name} v{bundle.metadata.model_version}")
    print(f"  Source: {bundle.metadata.data_source}  ← NOT real observations")

    # Build a 6-zone synthetic feature DataFrame (one zone per road zone)
    rng = np.random.default_rng(2024)
    feat_cols = [c.replace("_scaled", "") for c in bundle.metadata.feature_cols
                 if c.endswith("_scaled")]
    zone_ids = [f"ZONE_{chr(65+i)}" for i in range(6)]   # ZONE_A … ZONE_F

    df_zones = pd.DataFrame(
        {col: rng.uniform(1.0, 9.0, 6) for col in feat_cols}
    )
    df_zones["zone_id"] = zone_ids
    df_zones.attrs["_data_source"] = "SYNTHETIC"

    t0 = time.perf_counter()
    pred_result = predict_batch(df_zones, bundle, scenario_id="DEMO_EVA_001")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    print(f"\n  Predictions generated in {elapsed_ms:.1f} ms  (SYNTHETIC only)")
    print(f"  {'Zone':<10} {'FloodProb':>10} {'Status':>14}")
    print(f"  {'-'*36}")
    for rec in pred_result.batch.records:
        val = f"{rec.predicted_value:.4f}" if rec.predicted_value is not None else "N/A"
        print(f"  {rec.zone_id:<10} {val:>10} {rec.prediction_status.value:>14}")

    return pred_result.batch.records


# ---------------------------------------------------------------------------
# Stage 2 — Risk assessment  (uses risk_engine.scoring + validation)
# ---------------------------------------------------------------------------

def stage_risk_assessment(pred_records: list) -> list:
    section("Stage 2: Risk Assessment  [SYNTHETIC — PROVISIONAL — UNCALIBRATED]")

    # ------------------------------------------------------------------
    # Score predictions using the documented scoring module.
    #
    # The scoring module applies:
    #   risk_score = predicted_value   (identity proxy, not calibrated)
    #   scoring_method = "direct_proxy_uncalibrated"
    #
    # This replaces the former inline `risk_score = float(predicted_value)`
    # shortcut and makes the provenance explicit in every output record.
    # ------------------------------------------------------------------
    scored = score_batch(pred_records, thresholds=DEFAULT_THRESHOLDS)
    risk_records = extract_risk_records(scored)

    # ------------------------------------------------------------------
    # Validate the scored batch before passing to GIS.
    # Invalid records are NOT discarded — they are reported so operators
    # know about problems. The GIS router checks risk_status on every
    # record and handles non-OK scores via UnknownRiskPolicy.
    # ------------------------------------------------------------------
    validation = validate_batch(risk_records, duplicate_policy=DuplicateZonePolicy.WARN)

    print(f"  Scoring method    : {SCORING_METHOD_PROXY}")
    print(f"  Thresholds (PROVISIONAL, uncalibrated):")
    print(f"    LOW      < {DEFAULT_THRESHOLDS.low_max}")
    print(f"    MODERATE < {DEFAULT_THRESHOLDS.moderate_max}")
    print(f"    HIGH     < {DEFAULT_THRESHOLDS.high_max}")
    print(f"    CRITICAL >= {DEFAULT_THRESHOLDS.high_max}")
    print()
    print(f"  {'Zone':<10} {'RiskScore':>10} {'Category':>12} "
          f"{'Status':>10}  {'Method'}")
    print(f"  {'-'*62}")
    for sr in scored:
        rr = sr.risk_record
        score_str = f"{rr.risk_score:.4f}" if rr.risk_score is not None else "N/A"
        method_label = sr.scoring_method if rr.risk_status.value == "OK" else "not_scored"
        print(f"  {rr.zone_id:<10} {score_str:>10} {rr.risk_category.value:>12}"
              f" {rr.risk_status.value:>10}  {method_label}")

    print()
    print(f"  Validation: {validation.summary().splitlines()[0]}")
    if validation.batch_warnings:
        for w in validation.batch_warnings:
            print(f"  WARN: {w}")
    if not validation.valid:
        print("  VALIDATION ERRORS — see details above.")
        for rr_result in validation.record_results:
            if not rr_result.valid:
                print(f"    {rr_result.summary()}")

    print()
    print(
        "  IMPORTANT: risk_score is a SYNTHETIC, PROVISIONAL, UNCALIBRATED\n"
        "  decision-support proxy (= predicted FloodProbability value).\n"
        "  It is NOT a calibrated flood probability or a validated risk measure.\n"
        "  Do not use for real emergency decisions."
    )

    # Return list[RiskOutputRecord] — same interface as before for GIS stages.
    return risk_records


# ---------------------------------------------------------------------------
# Stage 3 — Road network
# ---------------------------------------------------------------------------

def stage_road_network():
    section("Stage 3: Synthetic Road Network  [NOT A REAL PLACE]")

    # 6-node grid: A-B-C top row, D-E-F bottom row
    # Matches the zones: ZONE_A..ZONE_F roughly correspond to each node
    nodes = [
        {"id": "A", "x": 0.000, "y":  0.000},
        {"id": "B", "x": 0.009, "y":  0.000},
        {"id": "C", "x": 0.018, "y":  0.000},
        {"id": "D", "x": 0.000, "y": -0.005},
        {"id": "E", "x": 0.009, "y": -0.005},
        {"id": "F", "x": 0.018, "y": -0.005},
    ]
    edges = [
        {"u": "A", "v": "B", "length_m": 1200, "road_type": "primary",    "one_way": False},
        {"u": "B", "v": "C", "length_m": 1200, "road_type": "primary",    "one_way": False},
        {"u": "A", "v": "D", "length_m":  600, "road_type": "secondary",  "one_way": False},
        {"u": "B", "v": "E", "length_m":  600, "road_type": "secondary",  "one_way": False},
        {"u": "C", "v": "F", "length_m":  600, "road_type": "secondary",  "one_way": False},
        {"u": "D", "v": "E", "length_m": 1200, "road_type": "tertiary",   "one_way": False},
        {"u": "E", "v": "F", "length_m": 1200, "road_type": "tertiary",   "one_way": False},
    ]
    G = from_synthetic(nodes, edges)
    validate_graph(G)

    summary = get_graph_summary(G)
    print(f"  Nodes   : {summary['nodes']}")
    print(f"  Edges   : {summary['edges']}")
    print(f"  Length  : {summary['total_length_m']:.0f} m total road")
    print(f"  CRS     : {summary['crs']}")
    print(f"  Source  : {summary['source']}  ← NOT a real road network")
    print()
    print("  Layout (SYNTHETIC — not a real place):")
    print("    A ── B ── C")
    print("    │    │    │")
    print("    D ── E ── F")
    print()
    print("  Shelters will be located at C and F.")
    print("  Evacuation origin: node A.")

    return G


# ---------------------------------------------------------------------------
# Stage 4 — Zone-to-road risk mapping
# ---------------------------------------------------------------------------

def stage_risk_mapping(G, risk_records: list) -> None:
    section("Stage 4: Zone-to-Road Risk Mapping")

    # Explicit zone → nodes mapping (caller-supplied; spatial join not available)
    # Each zone corresponds to one node and all edges leaving that node.
    zone_node_map = {
        "ZONE_A": ["A"],
        "ZONE_B": ["B"],
        "ZONE_C": ["C"],
        "ZONE_D": ["D"],
        "ZONE_E": ["E"],
        "ZONE_F": ["F"],
    }

    stats = apply_zone_node_mapping(G, risk_records, zone_node_map)
    coverage = get_risk_coverage(G)

    print(f"  Edges updated with risk : {stats['updated']}")
    print(f"  Edges skipped (no map)  : {stats['skipped']}")
    print(f"  Risk coverage           : {coverage['coverage_pct']:.1f}%")
    print(f"  Mean risk score         : {coverage['mean_risk']}")
    print()
    print(
        "  NOTE: Zone→node mapping is caller-supplied here (spatial polygon\n"
        "  data unavailable). Real deployment requires a GIS spatial join."
    )


# ---------------------------------------------------------------------------
# Stage 5+6 — Routing
# ---------------------------------------------------------------------------

def stage_routing(G) -> tuple:
    section("Stage 5+6: Routing  — Shortest-Path and Risk-Aware")

    cfg_shortest = RoutingConfig(mode=RoutingMode.SHORTEST)
    cfg_risk = RoutingConfig(
        mode=RoutingMode.RISK_AWARE,
        risk_weight=1.0,
        risk_m_equivalent=5000.0,
        unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE,
    )
    router_s = EvacuationRouter(G, cfg_shortest)
    router_r = EvacuationRouter(G, cfg_risk)

    subsection("A. Shortest-path (distance only, ignores risk)")
    route_s = router_s.route("A", "C")
    _print_route("A→C shortest", route_s)

    route_s2 = router_s.route("A", "F")
    _print_route("A→F shortest", route_s2)

    subsection("B. Risk-aware routing (risk penalty = risk_score × 5000 m)")
    route_r = router_r.route("A", "C")
    _print_route("A→C risk-aware", route_r)

    route_r2 = router_r.route("A", "F")
    _print_route("A→F risk-aware", route_r2)

    # Return router_r for adaptive replanning
    return router_r, route_r


# ---------------------------------------------------------------------------
# Stage 7 — Shelter allocation
# ---------------------------------------------------------------------------

def stage_shelter_allocation(G, router) -> ShelterManager:
    section("Stage 7: Shelter Allocation  [SYNTHETIC capacities]")

    shelters = load_shelters_from_list([
        {
            "shelter_id": "SH_C",
            "name": "Evacuation Point C (SYNTHETIC)",
            "lat": 0.000, "lon": 0.018,
            "capacity": 200,
            "data_source": "SYNTHETIC",
            "notes": "Synthetic shelter — not a real facility.",
        },
        {
            "shelter_id": "SH_F",
            "name": "Evacuation Point F (SYNTHETIC)",
            "lat": -0.005, "lon": 0.018,
            "capacity": 150,
            "data_source": "SYNTHETIC",
            "notes": "Synthetic shelter — not a real facility.",
        },
    ])
    mgr = ShelterManager(shelters)
    mgr.get("SH_C").nearest_node = "C"
    mgr.get("SH_F").nearest_node = "F"

    demand = [
        {"demand_id": "ZONE_A", "origin_node": "A", "count": 80},
        {"demand_id": "ZONE_B", "origin_node": "B", "count": 60},
        {"demand_id": "ZONE_D", "origin_node": "D", "count": 100},
    ]
    result = mgr.allocate(demand, router=router)

    print(f"  Total requested : {result.total_requested}")
    print(f"  Total admitted  : {result.total_admitted}")
    print(f"  Total unassigned: {result.total_unassigned}")
    print()
    print(f"  {'Demand':<12} {'Shelter':<10} {'Admitted':>9} {'Cost(m)':>9}")
    print(f"  {'-'*44}")
    for a in result.assignments:
        print(f"  {a.demand_id:<12} {a.shelter_id:<10} {a.admitted:>9} "
              f"{a.route_cost_m:>9.0f}")
    if result.unassigned:
        print(f"\n  Unassigned:")
        for u in result.unassigned:
            print(f"    demand={u['demand_id']}  count={u['requested']}  "
                  f"reason={u['reason']}")

    smry = mgr.summary()
    print(f"\n  Shelter summary: {smry}")
    return mgr


# ---------------------------------------------------------------------------
# Stage 8 — Road closure + dynamic replanning
# ---------------------------------------------------------------------------

def stage_road_closure(G) -> None:
    section("Stage 8: Road Closure + Dynamic Replanning  [mode C]")

    cfg = RoutingConfig(
        mode=RoutingMode.RISK_AWARE,
        risk_weight=1.0,
        risk_m_equivalent=5000.0,
        unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE,
    )
    router = EvacuationRouter(G, cfg)

    subsection("Before closure: route A→C")
    before = router.route("A", "C")
    _print_route("A→C (before closure)", before)

    subsection("Event: Primary road A-B blocked (e.g. flood water on road)")
    router.block_edge("A", "B")
    router.block_edge("B", "A")
    print(f"    Blocked edges: {router.blocked_edges}")

    subsection("Replan: route A→C after closure")
    after = router.replan("A", "C")
    _print_route("A→C (replanned)", after)

    if before.feasible and after.feasible:
        print(f"\n  Route changed: {before.path} → {after.path}")
        print(f"  Distance increase: "
              f"{after.total_length_m - before.total_length_m:.0f} m")


# ---------------------------------------------------------------------------
# Stage 9 — Shelter capacity event + reassignment
# ---------------------------------------------------------------------------

def stage_shelter_capacity_event(G, mgr: ShelterManager, router) -> None:
    section("Stage 9: Shelter Capacity Event + Reassignment")

    subsection("Event: SH_C closes (structural damage)")
    mgr.close_shelter("SH_C")
    print(f"    SH_C status: {mgr.get('SH_C').status.value}")

    subsection("New demand wave: 80 people from node D")
    new_demand = [{"demand_id": "ZONE_D_WAVE2", "origin_node": "D", "count": 80}]
    result = mgr.allocate(new_demand, router=router)

    print(f"    Admitted  : {result.total_admitted}")
    print(f"    Unassigned: {result.total_unassigned}")
    for a in result.assignments:
        print(f"    → assigned to {a.shelter_id}  (admitted={a.admitted})")
    if result.unassigned:
        for u in result.unassigned:
            print(f"    → unassigned: {u}")
    print(f"\n    Final shelter summary: {mgr.summary()}")


# ---------------------------------------------------------------------------
# Stage 10 — Benchmark
# ---------------------------------------------------------------------------

def stage_benchmark(G) -> None:
    section("Stage 10: Routing Benchmark  [SYNTHETIC]")

    cfg = RoutingConfig(
        mode=RoutingMode.RISK_AWARE,
        risk_weight=1.0,
        risk_m_equivalent=5000.0,
        unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE,
    )
    pairs = [("A", "C"), ("A", "F"), ("D", "C"), ("B", "F")]
    N = 200  # repetitions per pair

    print(f"  {'Route':<8}  {'Reps':>5}  {'Total(ms)':>12}  {'Per call(ms)':>14}")
    print(f"  {'-'*46}")
    for origin, dest in pairs:
        router = EvacuationRouter(G, cfg)
        t0 = time.perf_counter()
        for _ in range(N):
            router.route(origin, dest)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        per_call = elapsed_ms / N
        print(f"  {origin}→{dest:<4}  {N:>5}  {elapsed_ms:>12.2f}  "
              f"{per_call:>14.4f}")

    print()
    print("  NOTE: Benchmark is on a 6-node synthetic graph.")
    print("  Real city networks are orders of magnitude larger.")
    print("  These timings do NOT predict production performance.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t_start = time.perf_counter()

    print()
    print("=" * 68)
    print("  AEI — End-to-End Evacuation Intelligence Demo")
    print("  ALL DATA IS SYNTHETIC — NOT a real emergency guidance tool")
    print("=" * 68)
    print()
    print("  Pipeline: AI Predictions → Risk Scores → Zone-to-Road Mapping")
    print("           → Routing → Shelter Allocation → Replanning")

    # Stage 1: AI predictions
    pred_records = stage_ai_predictions()

    # Stage 2: Risk records
    risk_records = stage_risk_assessment(pred_records)

    # Stage 3: Road network
    G = stage_road_network()

    # Stage 4: Risk mapping
    stage_risk_mapping(G, risk_records)

    # Stage 5+6: Routing
    router, _ = stage_routing(G)

    # Stage 7: Shelter allocation
    mgr = stage_shelter_allocation(G, router)

    # Stage 8: Road closure + replanning
    stage_road_closure(G)

    # Stage 9: Shelter capacity event
    stage_shelter_capacity_event(G, mgr, router)

    # Stage 10: Benchmark
    stage_benchmark(G)

    # Final summary
    section("Demo Complete")
    elapsed = time.perf_counter() - t_start
    print(f"  Total demo runtime : {elapsed:.2f} s")
    print()
    print("  Stages completed:")
    print("    1.  AI predictions (synthetic RandomForest)")
    print("    2.  Risk records (synthetic decision-support scores)")
    print("    3.  Synthetic road network (not a real place)")
    print("    4.  Zone-to-road risk mapping")
    print("    5.  Shortest-path routing (mode A)")
    print("    6.  Risk-aware routing (mode B)")
    print("    7.  Capacity-aware shelter allocation")
    print("    8.  Road closure + dynamic replanning (mode C)")
    print("    9.  Shelter closure + demand reassignment")
    print("   10.  Routing benchmark")
    print()
    print("  Integration contract: AI module → GIS module")
    print("    RiskOutputRecord.zone_id + risk_score → edge weights")
    print("    Routing cost = length_m + risk_weight × 5000 × risk_score")
    print("    Unknown risk: configurable policy (CONSERVATIVE default)")
    print()
    print("  LIMITATIONS:")
    print("    * All predictions from a synthetic-data-trained model.")
    print("    * Road network is synthetic — no real geography.")
    print("    * Shelter capacities are made-up numbers.")
    print("    * Routing algorithm is Dijkstra (not A*; not optimised for")
    print("      large networks).")
    print("    * Travel times are rough estimates (fixed speed per road type).")
    print("    * No temporal modelling — static snapshot only.")
    print("    * Zone→node mapping was manually specified; real deployment")
    print("      requires a GIS spatial join with polygon data.")


if __name__ == "__main__":
    main()
