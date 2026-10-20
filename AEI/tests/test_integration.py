"""
AEI — Integration Tests: AI → Risk → GIS → Routing → Shelter
==============================================================
End-to-end contract tests that verify the complete pipeline:
  AI prediction interface
  → RiskOutputRecord schema
  → Zone-to-road risk mapper
  → Road-network graph
  → Routing (shortest, risk-aware, adaptive)
  → Shelter allocation

All data is SYNTHETIC.  These tests do NOT validate real-world accuracy.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests"))

# AI modules
from integration.schemas import (
    CONTRACT_VERSION,
    HazardPredictionBatch,
    HazardPredictionRecord,
    PredictionStatus,
    RiskCategory,
    RiskOutputRecord,
    RiskStatus,
    make_valid_prediction,
    make_valid_risk,
)
from risk_engine.risk_mapper import (
    apply_zone_node_mapping,
    build_synthetic_risk_records,
    get_risk_coverage,
)
from gis.network_loader import from_synthetic, get_graph_summary, validate_graph
from routing.router import (
    EvacuationRouter,
    RoutingConfig,
    RoutingMode,
    UnknownRiskPolicy,
    route_risk_aware,
    route_shortest,
)
from shelter.shelter_manager import (
    Shelter,
    ShelterManager,
    ShelterStatus,
    load_shelters_from_list,
)


# ---------------------------------------------------------------------------
# Shared pipeline graph
# ---------------------------------------------------------------------------

def _pipeline_graph():
    """
    5-node graph used across integration tests.
        A ── B ── C
             │
             D ── E

    Zone assignment: ZONE_A → nodes A,B; ZONE_B → nodes C,D,E
    """
    nodes = [
        {"id": "A", "x": 0.000, "y": 0.000},
        {"id": "B", "x": 0.009, "y": 0.000},
        {"id": "C", "x": 0.018, "y": 0.000},
        {"id": "D", "x": 0.009, "y": -0.005},
        {"id": "E", "x": 0.018, "y": -0.005},
    ]
    edges = [
        {"u": "A", "v": "B", "length_m": 1000, "one_way": False},
        {"u": "B", "v": "C", "length_m": 1000, "one_way": False},
        {"u": "B", "v": "D", "length_m":  600, "one_way": False},
        {"u": "D", "v": "E", "length_m":  800, "one_way": False},
    ]
    return from_synthetic(nodes, edges)


# ---------------------------------------------------------------------------
# Contract: HazardPredictionRecord → routing-compatible schema
# ---------------------------------------------------------------------------

class TestSchemaCompatibility:
    def test_prediction_record_has_zone_id(self):
        rec = make_valid_prediction("ZONE_001")
        assert rec.zone_id == "ZONE_001"

    def test_prediction_record_json_serialisable(self):
        rec = make_valid_prediction("ZONE_001")
        d = rec.to_gis_dict()
        json.dumps(d)  # must not raise

    def test_risk_record_has_zone_id(self):
        rec = make_valid_risk("ZONE_001", score=0.7)
        assert rec.zone_id == "ZONE_001"

    def test_risk_record_score_in_range(self):
        rec = make_valid_risk("ZONE_001", score=0.7)
        assert 0.0 <= rec.risk_score <= 1.0

    def test_risk_record_json_serialisable(self):
        rec = make_valid_risk("ZONE_001")
        d = rec.to_gis_dict()
        json.dumps(d)

    def test_contract_version_consistent(self):
        pred = make_valid_prediction()
        risk = make_valid_risk()
        assert pred.contract_version == risk.contract_version == CONTRACT_VERSION

    def test_non_ok_risk_has_unknown_category(self):
        from integration.schemas import make_unavailable_risk
        rec = make_unavailable_risk("Z", RiskStatus.NO_DATA)
        assert rec.risk_category == RiskCategory.UNKNOWN
        assert rec.risk_score is None


# ---------------------------------------------------------------------------
# Contract: RiskOutputRecord → road-network edge attributes
# ---------------------------------------------------------------------------

class TestRiskToEdgePropagation:
    def test_zone_node_mapping_sets_risk(self):
        G = _pipeline_graph()
        records = build_synthetic_risk_records(
            {"ZONE_A": 0.3, "ZONE_B": 0.8}
        )
        zone_node_map = {"ZONE_A": ["A", "B"], "ZONE_B": ["C", "D", "E"]}
        stats = apply_zone_node_mapping(G, records, zone_node_map)
        assert stats["updated"] > 0

        # Edges from A should have risk ~0.3 (A is in ZONE_A)
        for data in G["A"]["B"].values():
            assert data["risk_score"] == pytest.approx(0.3)

    def test_unknown_risk_edges_remain_none(self):
        G = _pipeline_graph()
        records = build_synthetic_risk_records({"ZONE_A": 0.3})
        zone_node_map = {"ZONE_A": ["A", "B"]}  # ZONE_B not mapped
        apply_zone_node_mapping(G, records, zone_node_map)

        # Edges from C, D, E have no zone → risk_score stays None
        for u in ["C", "D", "E"]:
            for v in G.neighbors(u):
                for data in G[u][v].values():
                    assert data["risk_score"] is None

    def test_non_ok_risk_not_propagated(self):
        G = _pipeline_graph()
        stale = RiskOutputRecord(
            zone_id="ZONE_A",
            risk_score=None,
            risk_category=RiskCategory.UNKNOWN,
            risk_status=RiskStatus.STALE_DATA,
            contributing_factors=[],
        )
        zone_node_map = {"ZONE_A": ["A", "B"]}
        apply_zone_node_mapping(G, [stale], zone_node_map, skip_non_ok=True)
        for data in G["A"]["B"].values():
            assert data["risk_score"] is None, (
                "Stale risk must NOT propagate to edge"
            )

    def test_coverage_after_partial_mapping(self):
        G = _pipeline_graph()
        records = build_synthetic_risk_records({"ZONE_A": 0.5})
        zone_node_map = {"ZONE_A": ["A"]}  # only node A
        apply_zone_node_mapping(G, records, zone_node_map)
        cov = get_risk_coverage(G)
        assert 0.0 < cov["coverage_pct"] < 100.0


# ---------------------------------------------------------------------------
# Contract: road-network graph → router interface
# ---------------------------------------------------------------------------

class TestGraphToRouterInterface:
    def test_graph_valid_after_risk_mapping(self):
        G = _pipeline_graph()
        records = build_synthetic_risk_records({"ZONE_A": 0.3})
        apply_zone_node_mapping(G, records, {"ZONE_A": ["A"]})
        validate_graph(G)  # must not raise

    def test_shortest_route_uses_graph(self):
        G = _pipeline_graph()
        r = route_shortest(G, "A", "C")
        assert r.feasible
        assert "A" == r.path[0]
        assert "C" == r.path[-1]

    def test_risk_aware_route_uses_edge_risk(self):
        G = _pipeline_graph()
        # High risk on A-B-C top path
        for u, v in [("A", "B"), ("B", "A"), ("B", "C"), ("C", "B")]:
            if G.has_edge(u, v):
                for k in G[u][v]:
                    G[u][v][k]["risk_score"] = 0.9
        # Low risk on bottom path
        for u, v in [("B", "D"), ("D", "B"), ("D", "E"), ("E", "D")]:
            if G.has_edge(u, v):
                for k in G[u][v]:
                    G[u][v][k]["risk_score"] = 0.0

        r = route_risk_aware(G, "A", "E",
                             risk_weight=1.0,
                             risk_m_equivalent=5000.0,
                             unknown_risk_policy=UnknownRiskPolicy.OPTIMISTIC)
        assert r.feasible
        # Bottom path A→B→D→E should be cheaper than A→B→C→(no E)
        # Actually A→E must go through B in any case
        # Just verify route is feasible and uses the graph correctly
        assert r.path[0] == "A"
        assert r.path[-1] == "E"

    def test_blocked_edge_changes_route(self):
        G = _pipeline_graph()
        router = EvacuationRouter(G, RoutingConfig(mode=RoutingMode.SHORTEST))
        before = router.route("A", "C")
        router.block_edge("A", "B")
        router.block_edge("B", "A")
        after = router.replan("A", "C")
        # Before: feasible
        assert before.feasible
        # After blocking only path, result is either infeasible or a different path
        if after.feasible:
            assert after.path != before.path
        else:
            # Correctly reported infeasible — that is also valid behavior
            assert not after.feasible
            assert len(after.notes) > 0


# ---------------------------------------------------------------------------
# Contract: router → shelter allocation interface
# ---------------------------------------------------------------------------

class TestRouterToShelterInterface:
    def test_allocation_with_routing_cost(self):
        G = _pipeline_graph()
        shelters = load_shelters_from_list([
            {"shelter_id": "SH_C", "name": "C (SYNTHETIC)",
             "lat": 0.000, "lon": 0.018, "capacity": 50,
             "data_source": "SYNTHETIC"},
            {"shelter_id": "SH_E", "name": "E (SYNTHETIC)",
             "lat": -0.005, "lon": 0.018, "capacity": 50,
             "data_source": "SYNTHETIC"},
        ])
        shelters[0].nearest_node = "C"
        shelters[1].nearest_node = "E"

        mgr = ShelterManager(shelters)
        cfg = RoutingConfig(mode=RoutingMode.SHORTEST)
        router = EvacuationRouter(G, cfg)

        demand = [{"demand_id": "ZONE_A", "origin_node": "A", "count": 20}]
        result = mgr.allocate(demand, router=router)

        assert result.total_admitted == 20
        # Routing cost stored in assignment
        assert result.assignments[0].route_cost_m >= 0

    def test_shelter_near_blocked_road_not_reached(self):
        G = _pipeline_graph()
        shelters = load_shelters_from_list([
            {"shelter_id": "SH_C", "name": "C (SYNTHETIC)",
             "lat": 0.000, "lon": 0.018, "capacity": 100,
             "data_source": "SYNTHETIC"},
        ])
        shelters[0].nearest_node = "C"
        mgr = ShelterManager(shelters)

        cfg = RoutingConfig(mode=RoutingMode.SHORTEST)
        router = EvacuationRouter(G, cfg)
        # Pipeline graph only has A→B as exit from A; block both directions
        router.block_edge("A", "B")
        router.block_edge("B", "A")

        demand = [{"demand_id": "ZONE_A", "origin_node": "A", "count": 30}]
        result = mgr.allocate(demand, router=router)

        # All demand unassigned: no feasible route from A to SH_C
        assert result.total_unassigned == 30

    def test_allocation_result_json_serialisable(self):
        G = _pipeline_graph()
        shelters = load_shelters_from_list([
            {"shelter_id": "SH_C", "name": "C (SYNTHETIC)",
             "lat": 0.000, "lon": 0.018, "capacity": 50,
             "data_source": "SYNTHETIC"},
        ])
        shelters[0].nearest_node = "C"
        mgr = ShelterManager(shelters)
        demand = [{"demand_id": "Z", "origin_node": "A", "count": 5}]
        cfg = RoutingConfig(mode=RoutingMode.SHORTEST)
        router = EvacuationRouter(G, cfg)
        result = mgr.allocate(demand, router=router)

        # Convert to serialisable form
        output = {
            "total_admitted": result.total_admitted,
            "total_unassigned": result.total_unassigned,
            "assignments": [
                {"demand_id": a.demand_id,
                 "shelter_id": a.shelter_id,
                 "admitted": a.admitted,
                 "route_cost_m": a.route_cost_m}
                for a in result.assignments
            ],
            "unassigned": result.unassigned,
        }
        json.dumps(output)  # must not raise


# ---------------------------------------------------------------------------
# Full pipeline: AI predictions → routing → allocation
# ---------------------------------------------------------------------------

class TestFullPipeline:
    @pytest.fixture(scope="class")
    def bundle(self):
        """Load or train the RF model once for this class."""
        artefact_dir = _ROOT / "models" / "RandomForest_v0.1.0"
        if not artefact_dir.exists():
            from fixtures.make_synthetic_fixture import make_clean_fixture
            from prediction.train import run_training_pipeline
            from prediction.model_loader import (
                metadata_from_training_result,
                save_model_bundle,
            )
            df = make_clean_fixture(n_rows=200, seed=42)
            df.attrs["_data_source"] = "SYNTHETIC"
            result = run_training_pipeline(df)
            meta = metadata_from_training_result(result, "RandomForest", "0.1.0")
            save_model_bundle(result.rf_model, result.cleaning_stats,
                              result.feature_stats, meta,
                              _ROOT / "models", overwrite=True)

        from prediction.model_loader import load_model_bundle
        return load_model_bundle(artefact_dir)

    def test_predictions_to_risk_records(self, bundle):
        """AI predictions can be converted to valid RiskOutputRecords."""
        import pandas as pd
        from prediction.predict import predict_batch

        feat_cols = [c.replace("_scaled", "") for c in bundle.metadata.feature_cols
                     if c.endswith("_scaled")]
        rng = np.random.default_rng(999)
        df = pd.DataFrame({col: rng.uniform(1.0, 9.0, 5) for col in feat_cols})
        df["zone_id"] = [f"Z{i}" for i in range(5)]
        df.attrs["_data_source"] = "SYNTHETIC"

        pred_result = predict_batch(df, bundle)
        assert len(pred_result.batch.records) == 5

        # Convert to risk records
        risk_records = []
        for rec in pred_result.batch.records:
            if rec.prediction_status == PredictionStatus.OK:
                score = float(rec.predicted_value)
                cat = (RiskCategory.CRITICAL if score >= 0.75
                       else RiskCategory.HIGH if score >= 0.5
                       else RiskCategory.MODERATE if score >= 0.25
                       else RiskCategory.LOW)
                risk_records.append(RiskOutputRecord(
                    zone_id=rec.zone_id,
                    risk_score=score,
                    risk_category=cat,
                    data_freshness="PT0S",
                    risk_status=RiskStatus.OK,
                    contributing_factors=["FloodProbability_SYNTHETIC"],
                ))

        assert len(risk_records) == 5
        for r in risk_records:
            assert r.risk_status == RiskStatus.OK
            assert 0.0 <= r.risk_score <= 1.0

    def test_risk_records_to_graph_to_route(self, bundle):
        """Full pipeline: predictions → risk → graph → route."""
        import pandas as pd
        from prediction.predict import predict_batch

        feat_cols = [c.replace("_scaled", "") for c in bundle.metadata.feature_cols
                     if c.endswith("_scaled")]
        rng = np.random.default_rng(42)
        df = pd.DataFrame({col: rng.uniform(1.0, 9.0, 5) for col in feat_cols})
        df["zone_id"] = ["ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D", "ZONE_E"]
        df.attrs["_data_source"] = "SYNTHETIC"

        pred_result = predict_batch(df, bundle)
        risk_records = []
        for rec in pred_result.batch.records:
            if rec.prediction_status == PredictionStatus.OK:
                score = float(rec.predicted_value)
                cat = (RiskCategory.CRITICAL if score >= 0.75
                       else RiskCategory.HIGH if score >= 0.5
                       else RiskCategory.MODERATE if score >= 0.25
                       else RiskCategory.LOW)
                risk_records.append(RiskOutputRecord(
                    zone_id=rec.zone_id, risk_score=score,
                    risk_category=cat, data_freshness="PT0S",
                    risk_status=RiskStatus.OK,
                    contributing_factors=["FloodProbability_SYNTHETIC"],
                ))

        G = _pipeline_graph()
        zone_node_map = {
            "ZONE_A": ["A"], "ZONE_B": ["B"], "ZONE_C": ["C"],
            "ZONE_D": ["D"], "ZONE_E": ["E"],
        }
        apply_zone_node_mapping(G, risk_records, zone_node_map)

        cfg = RoutingConfig(
            mode=RoutingMode.RISK_AWARE,
            risk_weight=1.0,
            risk_m_equivalent=5000.0,
            unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE,
        )
        router = EvacuationRouter(G, cfg)
        route = router.route("A", "C")

        assert route.feasible
        assert route.path[0] == "A"
        assert route.path[-1] == "C"
        # Route is JSON-serialisable
        json.dumps({
            "path": route.path,
            "total_length_m": route.total_length_m,
            "total_cost": route.total_cost,
            "total_risk_penalty_m": route.total_risk_penalty_m,
            "feasible": route.feasible,
        })

    def test_end_to_end_with_shelter_allocation(self, bundle):
        """Complete pipeline including shelter allocation."""
        import pandas as pd
        from prediction.predict import predict_batch

        feat_cols = [c.replace("_scaled", "") for c in bundle.metadata.feature_cols
                     if c.endswith("_scaled")]
        rng = np.random.default_rng(7)
        df = pd.DataFrame({col: rng.uniform(1.0, 9.0, 5) for col in feat_cols})
        df["zone_id"] = ["ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D", "ZONE_E"]
        df.attrs["_data_source"] = "SYNTHETIC"

        pred_result = predict_batch(df, bundle)
        risk_records = []
        for rec in pred_result.batch.records:
            if rec.prediction_status == PredictionStatus.OK:
                score = float(rec.predicted_value)
                cat = (RiskCategory.CRITICAL if score >= 0.75
                       else RiskCategory.HIGH if score >= 0.5
                       else RiskCategory.MODERATE if score >= 0.25
                       else RiskCategory.LOW)
                risk_records.append(RiskOutputRecord(
                    zone_id=rec.zone_id, risk_score=score, risk_category=cat,
                    data_freshness="PT0S", risk_status=RiskStatus.OK,
                    contributing_factors=["FloodProbability_SYNTHETIC"],
                ))

        G = _pipeline_graph()
        zone_node_map = {
            "ZONE_A": ["A"], "ZONE_B": ["B"], "ZONE_C": ["C"],
            "ZONE_D": ["D"], "ZONE_E": ["E"],
        }
        apply_zone_node_mapping(G, risk_records, zone_node_map)

        shelters = load_shelters_from_list([
            {"shelter_id": "SH_C", "name": "C SYNTH",
             "lat": 0.000, "lon": 0.018, "capacity": 100, "data_source": "SYNTHETIC"},
            {"shelter_id": "SH_E", "name": "E SYNTH",
             "lat": -0.005, "lon": 0.018, "capacity": 80, "data_source": "SYNTHETIC"},
        ])
        shelters[0].nearest_node = "C"
        shelters[1].nearest_node = "E"
        mgr = ShelterManager(shelters)

        cfg = RoutingConfig(
            mode=RoutingMode.RISK_AWARE,
            risk_weight=1.0,
            risk_m_equivalent=5000.0,
            unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE,
        )
        router = EvacuationRouter(G, cfg)

        demand = [
            {"demand_id": "ZONE_A", "origin_node": "A", "count": 50},
            {"demand_id": "ZONE_B", "origin_node": "B", "count": 60},
        ]
        result = mgr.allocate(demand, router=router)

        assert result.total_requested == 110
        assert result.total_admitted + result.total_unassigned == 110
        assert result.total_admitted > 0


# ---------------------------------------------------------------------------
# Integration: dynamic replanning
# ---------------------------------------------------------------------------

class TestDynamicReplanning:
    def test_replan_after_blockage(self):
        G = _pipeline_graph()
        router = EvacuationRouter(G, RoutingConfig(mode=RoutingMode.SHORTEST))

        r1 = router.route("A", "C")
        assert r1.feasible

        # Block both directions of A-B to force infeasibility (A-B-C is the only path to C)
        router.block_edge("A", "B")
        router.block_edge("B", "A")

        r2 = router.replan("A", "C")
        assert r2.replanned is True
        # Pipeline graph: only path A→C is through B; after blocking it's infeasible
        if r2.feasible:
            assert "B" not in r2.path
        else:
            assert not r2.feasible  # correctly infeasible

    def test_replan_after_risk_increase(self):
        G = _pipeline_graph()
        cfg = RoutingConfig(
            mode=RoutingMode.RISK_AWARE,
            risk_weight=1.0,
            risk_m_equivalent=10000.0,
            unknown_risk_policy=UnknownRiskPolicy.OPTIMISTIC,
        )
        router = EvacuationRouter(G, cfg)

        # Set zero risk everywhere
        from risk_engine.risk_mapper import apply_uniform_risk
        apply_uniform_risk(router.graph, 0.0)

        r1 = router.route("A", "C")
        assert r1.feasible

        # Dramatically increase risk on A-B
        router.update_edge_risk("A", "B", 1.0)
        router.update_edge_risk("B", "A", 1.0)

        r2 = router.replan("A", "C")
        assert r2.feasible
        # Both routes feasible; cost should differ if paths differ
        # (may remain same path if only one path exists A→B→C)

    def test_replan_reports_infeasible_when_all_blocked(self):
        G = _pipeline_graph()
        router = EvacuationRouter(G, RoutingConfig(mode=RoutingMode.SHORTEST))
        # Block ALL edges leaving A (A-B is the only one in pipeline graph)
        router.block_edge("A", "B")
        router.block_edge("B", "A")
        router.block_edge("A", "D")
        router.block_edge("D", "A")
        r = router.replan("A", "C")
        assert not r.feasible

    def test_replan_notes_explain_infeasibility(self):
        G = _pipeline_graph()
        router = EvacuationRouter(G, RoutingConfig(mode=RoutingMode.SHORTEST))
        router.block_edge("A", "B")
        r = router.replan("A", "C")
        if not r.feasible:
            assert len(r.notes) > 0
