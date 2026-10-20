"""
Tests for src/risk_engine/risk_mapper.py
==========================================
All data is SYNTHETIC.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from gis.network_loader import from_synthetic
from risk_engine.risk_mapper import (
    CATEGORY_MIDPOINTS,
    apply_risk_records_to_graph,
    apply_uniform_risk,
    apply_zone_node_mapping,
    build_synthetic_risk_records,
    get_risk_coverage,
)
from integration.schemas import (
    RiskCategory,
    RiskOutputRecord,
    RiskStatus,
    make_valid_risk,
    make_unavailable_risk,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _simple_graph(n_nodes=4):
    """
    Linear graph: 0 → 1 → 2 → 3 (bidirectional).
    """
    nodes = [{"id": i, "x": float(i) * 0.01, "y": 0.0} for i in range(n_nodes)]
    edges = [{"u": i, "v": i + 1, "length_m": 500, "one_way": False}
             for i in range(n_nodes - 1)]
    return from_synthetic(nodes, edges)


def _graph_with_zones():
    """
    4-node graph with zone_id pre-set on edges.
    Edges 0→1 and 1→0 belong to ZONE_A.
    Edges 1→2 and 2→1 belong to ZONE_B.
    Edges 2→3 and 3→2 belong to ZONE_C.
    """
    G = _simple_graph(4)
    zone_map = {(0, 1): "ZONE_A", (1, 0): "ZONE_A",
                (1, 2): "ZONE_B", (2, 1): "ZONE_B",
                (2, 3): "ZONE_C", (3, 2): "ZONE_C"}
    for (u, v), zone in zone_map.items():
        for k in G[u][v]:
            G[u][v][k]["zone_id"] = zone
    return G


# ---------------------------------------------------------------------------
# build_synthetic_risk_records
# ---------------------------------------------------------------------------

class TestBuildSyntheticRiskRecords:
    def test_returns_correct_count(self):
        records = build_synthetic_risk_records(
            {"ZONE_A": 0.2, "ZONE_B": 0.6, "ZONE_C": 0.9}
        )
        assert len(records) == 3

    def test_record_risk_scores_match(self):
        records = build_synthetic_risk_records({"ZONE_X": 0.45})
        assert records[0].risk_score == pytest.approx(0.45)

    def test_category_low_for_low_score(self):
        records = build_synthetic_risk_records({"Z": 0.10})
        assert records[0].risk_category == RiskCategory.LOW

    def test_category_moderate(self):
        records = build_synthetic_risk_records({"Z": 0.30})
        assert records[0].risk_category == RiskCategory.MODERATE

    def test_category_high(self):
        records = build_synthetic_risk_records({"Z": 0.60})
        assert records[0].risk_category == RiskCategory.HIGH

    def test_category_critical(self):
        records = build_synthetic_risk_records({"Z": 0.80})
        assert records[0].risk_category == RiskCategory.CRITICAL

    def test_status_ok(self):
        records = build_synthetic_risk_records({"Z": 0.5})
        assert records[0].risk_status == RiskStatus.OK

    def test_contributing_factors_present(self):
        records = build_synthetic_risk_records({"Z": 0.5})
        assert len(records[0].contributing_factors) > 0


# ---------------------------------------------------------------------------
# apply_risk_records_to_graph
# ---------------------------------------------------------------------------

class TestApplyRiskRecordsToGraph:
    def test_updates_correct_edges(self):
        G = _graph_with_zones()
        records = build_synthetic_risk_records(
            {"ZONE_A": 0.3, "ZONE_B": 0.7, "ZONE_C": 0.9}
        )
        stats = apply_risk_records_to_graph(G, records)
        assert stats["updated"] > 0

    def test_risk_score_assigned_to_matching_edges(self):
        G = _graph_with_zones()
        records = build_synthetic_risk_records({"ZONE_A": 0.55})
        apply_risk_records_to_graph(G, records)
        # Check all edges with zone_id == ZONE_A have risk_score = 0.55
        for _, _, _, data in G.edges(data=True, keys=True):
            if data.get("zone_id") == "ZONE_A":
                assert data["risk_score"] == pytest.approx(0.55)

    def test_non_ok_records_skipped_by_default(self):
        G = _graph_with_zones()
        stale_record = RiskOutputRecord(
            zone_id="ZONE_A",
            risk_score=None,
            risk_category=RiskCategory.UNKNOWN,
            risk_status=RiskStatus.STALE_DATA,
            contributing_factors=[],
        )
        apply_risk_records_to_graph(G, [stale_record], skip_non_ok=True)
        # Edges in ZONE_A should still have risk_score=None
        for _, _, _, data in G.edges(data=True, keys=True):
            if data.get("zone_id") == "ZONE_A":
                assert data["risk_score"] is None

    def test_no_zone_id_edges_skipped(self):
        G = _simple_graph(3)  # no zone_id on edges
        records = build_synthetic_risk_records({"ZONE_A": 0.5})
        stats = apply_risk_records_to_graph(G, records)
        assert stats["updated"] == 0
        assert stats["skipped"] == G.number_of_edges()

    def test_stats_total_equals_edge_count(self):
        G = _graph_with_zones()
        records = build_synthetic_risk_records(
            {"ZONE_A": 0.2, "ZONE_B": 0.5}
        )
        stats = apply_risk_records_to_graph(G, records)
        assert stats["total"] == G.number_of_edges()
        assert stats["updated"] + stats["skipped"] == stats["total"]


# ---------------------------------------------------------------------------
# apply_zone_node_mapping
# ---------------------------------------------------------------------------

class TestApplyZoneNodeMapping:
    def test_edges_get_risk_and_zone_id(self):
        G = _simple_graph(4)
        records = build_synthetic_risk_records({"ZONE_A": 0.4, "ZONE_B": 0.8})
        zone_node_map = {
            "ZONE_A": [0, 1],
            "ZONE_B": [2, 3],
        }
        apply_zone_node_mapping(G, records, zone_node_map)

        for u, v, k, data in G.edges(data=True, keys=True):
            if u in (0, 1):
                assert data["zone_id"] == "ZONE_A"
                assert data["risk_score"] == pytest.approx(0.4)
            elif u in (2, 3):
                assert data["zone_id"] == "ZONE_B"
                assert data["risk_score"] == pytest.approx(0.8)

    def test_non_ok_records_skipped(self):
        G = _simple_graph(3)
        bad_rec = RiskOutputRecord(
            zone_id="ZONE_A", risk_score=None,
            risk_category=RiskCategory.UNKNOWN,
            risk_status=RiskStatus.NO_DATA,
            contributing_factors=[],
        )
        zone_node_map = {"ZONE_A": [0]}
        stats = apply_zone_node_mapping(G, [bad_rec], zone_node_map, skip_non_ok=True)
        assert stats["updated"] == 0

    def test_missing_zone_no_crash(self):
        G = _simple_graph(3)
        records = build_synthetic_risk_records({"ZONE_X": 0.5})
        # zone_node_map references ZONE_X but graph nodes have no such zone
        zone_node_map = {"ZONE_X": [0, 1]}
        # Should not raise
        stats = apply_zone_node_mapping(G, records, zone_node_map)
        assert isinstance(stats, dict)

    def test_stats_keys_present(self):
        G = _simple_graph(3)
        records = build_synthetic_risk_records({"ZONE_A": 0.5})
        zone_node_map = {"ZONE_A": [0]}
        stats = apply_zone_node_mapping(G, records, zone_node_map)
        for k in ("updated", "skipped", "total"):
            assert k in stats

    def test_stats_totals_consistent(self):
        G = _simple_graph(4)
        records = build_synthetic_risk_records({"ZONE_A": 0.5})
        zone_node_map = {"ZONE_A": [0, 1]}
        stats = apply_zone_node_mapping(G, records, zone_node_map)
        assert stats["updated"] + stats["skipped"] == stats["total"]


# ---------------------------------------------------------------------------
# apply_uniform_risk
# ---------------------------------------------------------------------------

class TestApplyUniformRisk:
    def test_all_edges_get_risk_score(self):
        G = _simple_graph(4)
        apply_uniform_risk(G, 0.65)
        for _, _, data in G.edges(data=True):
            assert data["risk_score"] == pytest.approx(0.65)

    def test_returns_edge_count(self):
        G = _simple_graph(4)
        n = apply_uniform_risk(G, 0.5)
        assert n == G.number_of_edges()

    def test_invalid_risk_score_raises(self):
        G = _simple_graph(3)
        with pytest.raises(ValueError, match="risk_score"):
            apply_uniform_risk(G, 1.5)

    def test_zero_risk_allowed(self):
        G = _simple_graph(3)
        apply_uniform_risk(G, 0.0)
        for _, _, data in G.edges(data=True):
            assert data["risk_score"] == pytest.approx(0.0)

    def test_one_risk_allowed(self):
        G = _simple_graph(3)
        apply_uniform_risk(G, 1.0)
        for _, _, data in G.edges(data=True):
            assert data["risk_score"] == pytest.approx(1.0)

    def test_with_zone_id_option(self):
        G = _simple_graph(3)
        apply_uniform_risk(G, 0.5, zone_id="TEST_ZONE")
        for _, _, data in G.edges(data=True):
            assert data["zone_id"] == "TEST_ZONE"


# ---------------------------------------------------------------------------
# get_risk_coverage
# ---------------------------------------------------------------------------

class TestGetRiskCoverage:
    def test_zero_coverage_on_fresh_graph(self):
        G = _simple_graph(4)
        cov = get_risk_coverage(G)
        assert cov["coverage_pct"] == pytest.approx(0.0)
        assert cov["mean_risk"] is None

    def test_full_coverage_after_uniform(self):
        G = _simple_graph(4)
        apply_uniform_risk(G, 0.5)
        cov = get_risk_coverage(G)
        assert cov["coverage_pct"] == pytest.approx(100.0)

    def test_mean_risk_correct(self):
        G = _simple_graph(3)
        # 4 directed edges, set known risk on all
        apply_uniform_risk(G, 0.4)
        cov = get_risk_coverage(G)
        assert cov["mean_risk"] == pytest.approx(0.4, abs=0.001)

    def test_max_min_risk(self):
        G = _simple_graph(3)
        # Manually set different risk values
        edges = list(G.edges(keys=True))
        G[edges[0][0]][edges[0][1]][edges[0][2]]["risk_score"] = 0.2
        G[edges[1][0]][edges[1][1]][edges[1][2]]["risk_score"] = 0.8
        cov = get_risk_coverage(G)
        assert cov["max_risk"] == pytest.approx(0.8, abs=0.01)
        assert cov["min_risk"] == pytest.approx(0.2, abs=0.01)

    def test_coverage_keys_present(self):
        G = _simple_graph(3)
        cov = get_risk_coverage(G)
        for key in ("total_edges", "edges_with_risk", "edges_without_risk",
                    "coverage_pct", "mean_risk", "max_risk", "min_risk"):
            assert key in cov

    def test_totals_consistent(self):
        G = _simple_graph(4)
        apply_uniform_risk(G, 0.3)
        cov = get_risk_coverage(G)
        assert (cov["edges_with_risk"] + cov["edges_without_risk"]
                == cov["total_edges"])
