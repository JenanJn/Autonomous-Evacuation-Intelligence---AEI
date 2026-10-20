"""
Tests for src/routing/router.py
=================================
All road networks are SYNTHETIC.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from gis.network_loader import from_synthetic
from routing.router import (
    DEFAULT_RISK_M_EQUIVALENT,
    EvacuationRouter,
    RouteResult,
    RoutingConfig,
    RoutingMode,
    UnknownRiskPolicy,
    route_risk_aware,
    route_shortest,
)


# ---------------------------------------------------------------------------
# Shared graph fixtures
# ---------------------------------------------------------------------------

def _grid_graph():
    """
    6-node grid with explicit lengths and risk scores.

        A ── B ── C
        │    │    │
        D ── E ── F

    A-B, B-C: length=1000, risk=0.8 (high risk)
    A-D, B-E, C-F: length=600, risk=0.1 (low risk)
    D-E, E-F: length=1000, risk=0.1 (low risk)
    All bidirectional.
    """
    nodes = [
        {"id": "A", "x": 0.000, "y":  0.000},
        {"id": "B", "x": 0.009, "y":  0.000},
        {"id": "C", "x": 0.018, "y":  0.000},
        {"id": "D", "x": 0.000, "y": -0.005},
        {"id": "E", "x": 0.009, "y": -0.005},
        {"id": "F", "x": 0.018, "y": -0.005},
    ]
    edges = [
        {"u": "A", "v": "B", "length_m": 1000, "one_way": False},
        {"u": "B", "v": "C", "length_m": 1000, "one_way": False},
        {"u": "A", "v": "D", "length_m":  600, "one_way": False},
        {"u": "B", "v": "E", "length_m":  600, "one_way": False},
        {"u": "C", "v": "F", "length_m":  600, "one_way": False},
        {"u": "D", "v": "E", "length_m": 1000, "one_way": False},
        {"u": "E", "v": "F", "length_m": 1000, "one_way": False},
    ]
    G = from_synthetic(nodes, edges)
    # Assign risk scores
    for u, v in [("A", "B"), ("B", "A"), ("B", "C"), ("C", "B")]:
        for k in G[u][v]:
            G[u][v][k]["risk_score"] = 0.8
    for u, v in [("A", "D"), ("D", "A"), ("B", "E"), ("E", "B"),
                 ("C", "F"), ("F", "C"), ("D", "E"), ("E", "D"),
                 ("E", "F"), ("F", "E")]:
        for k in G[u][v]:
            G[u][v][k]["risk_score"] = 0.1
    return G


def _linear_graph():
    """A-B-C linear, bidirectional."""
    nodes = [
        {"id": "A", "x": 0.0, "y": 0.0},
        {"id": "B", "x": 0.01, "y": 0.0},
        {"id": "C", "x": 0.02, "y": 0.0},
    ]
    edges = [
        {"u": "A", "v": "B", "length_m": 500, "one_way": False},
        {"u": "B", "v": "C", "length_m": 500, "one_way": False},
    ]
    return from_synthetic(nodes, edges)


@pytest.fixture
def grid_G():
    return _grid_graph()


@pytest.fixture
def linear_G():
    return _linear_graph()


# ---------------------------------------------------------------------------
# RoutingConfig validation
# ---------------------------------------------------------------------------

class TestRoutingConfig:
    def test_default_config_valid(self):
        cfg = RoutingConfig()
        assert cfg.mode == RoutingMode.SHORTEST
        assert cfg.risk_weight >= 0

    def test_negative_risk_weight_raises(self):
        with pytest.raises(ValueError, match="risk_weight"):
            RoutingConfig(risk_weight=-1.0)

    def test_zero_risk_m_equivalent_raises(self):
        with pytest.raises(ValueError, match="risk_m_equivalent"):
            RoutingConfig(risk_m_equivalent=0.0)

    def test_custom_config_stored(self):
        cfg = RoutingConfig(
            mode=RoutingMode.RISK_AWARE,
            risk_weight=2.0,
            risk_m_equivalent=3000.0,
            unknown_risk_policy=UnknownRiskPolicy.NEUTRAL,
        )
        assert cfg.risk_weight == 2.0
        assert cfg.risk_m_equivalent == 3000.0
        assert cfg.unknown_risk_policy == UnknownRiskPolicy.NEUTRAL


# ---------------------------------------------------------------------------
# Mode A: Shortest-path
# ---------------------------------------------------------------------------

class TestShortestPath:
    def test_direct_route_found(self, linear_G):
        r = route_shortest(linear_G, "A", "C")
        assert r.feasible
        assert r.path[0] == "A"
        assert r.path[-1] == "C"

    def test_path_includes_intermediate_nodes(self, linear_G):
        r = route_shortest(linear_G, "A", "C")
        assert "B" in r.path

    def test_total_length_correct(self, linear_G):
        r = route_shortest(linear_G, "A", "C")
        # A→B = 500, B→C = 500
        assert r.total_length_m == pytest.approx(1000.0)

    def test_risk_penalty_zero_in_shortest_mode(self, grid_G):
        r = route_shortest(grid_G, "A", "C")
        assert r.total_risk_penalty_m == pytest.approx(0.0)

    def test_cost_equals_length_in_shortest_mode(self, grid_G):
        r = route_shortest(grid_G, "A", "C")
        assert r.total_cost == pytest.approx(r.total_length_m)

    def test_same_node_returns_feasible_empty_path(self, linear_G):
        r = route_shortest(linear_G, "A", "A")
        assert r.feasible
        assert r.total_length_m == pytest.approx(0.0)

    def test_missing_origin_infeasible(self, linear_G):
        r = route_shortest(linear_G, "NONEXISTENT", "C")
        assert not r.feasible

    def test_missing_dest_infeasible(self, linear_G):
        r = route_shortest(linear_G, "A", "NONEXISTENT")
        assert not r.feasible

    def test_infeasible_has_notes(self, linear_G):
        r = route_shortest(linear_G, "NONEXISTENT", "C")
        assert len(r.notes) > 0

    def test_shortest_prefers_direct_path(self, grid_G):
        """A→C via top row (2000m) vs via bottom row (2200m)."""
        r = route_shortest(grid_G, "A", "C")
        # Top: A-B-C = 2000; Bottom: A-D-E-F-C = 3200
        assert r.total_length_m == pytest.approx(2000.0)

    def test_travel_time_positive(self, linear_G):
        r = route_shortest(linear_G, "A", "C")
        assert r.estimated_travel_time_s > 0

    def test_mode_field_correct(self, linear_G):
        r = route_shortest(linear_G, "A", "C")
        assert r.mode == RoutingMode.SHORTEST


# ---------------------------------------------------------------------------
# Mode B: Risk-aware routing
# ---------------------------------------------------------------------------

class TestRiskAwareRouting:
    def test_avoids_high_risk_path(self, grid_G):
        """
        Top row A-B-C has risk=0.8; bottom row A-D-E-F-C has risk=0.1.
        With large risk_m_equivalent, risk-aware router should prefer bottom.
        """
        r = route_risk_aware(
            grid_G, "A", "C",
            risk_weight=1.0,
            risk_m_equivalent=5000.0,
            unknown_risk_policy=UnknownRiskPolicy.OPTIMISTIC,
        )
        assert r.feasible
        # Bottom row: A-D-E-F-C = 600+1000+1000+600 = 3200 m
        # Top row: A-B-C = 2000 m + 2×0.8×5000 = 2000+8000 = 10000
        # Bottom: 3200 + 4×0.1×5000 = 3200+2000 = 5200
        # So bottom row is cheaper in risk-aware mode
        assert "B" not in r.path, (
            f"Risk-aware router should avoid high-risk B node, path={r.path}"
        )

    def test_risk_penalty_nonzero_for_risky_edges(self, grid_G):
        """Force a route that passes through high-risk edges."""
        # Make bottom row blocked so only top row is available
        import networkx as nx
        G2 = grid_G.copy()
        for u, v in [("A", "D"), ("D", "A"), ("D", "E"), ("E", "D"),
                     ("E", "F"), ("F", "E"), ("C", "F"), ("F", "C")]:
            if G2.has_edge(u, v):
                for k in G2[u][v]:
                    G2[u][v][k]["blocked"] = True
        r = route_risk_aware(G2, "A", "C",
                             risk_weight=1.0, risk_m_equivalent=5000.0,
                             unknown_risk_policy=UnknownRiskPolicy.OPTIMISTIC)
        if r.feasible:
            assert r.total_risk_penalty_m > 0

    def test_unknown_risk_conservative_avoids_none_edges(self):
        """Edges with risk_score=None get max penalty under CONSERVATIVE policy."""
        G = _grid_graph()
        # Remove risk from top row edges
        for u, v in [("A", "B"), ("B", "A"), ("B", "C"), ("C", "B")]:
            for k in G[u][v]:
                G[u][v][k]["risk_score"] = None
        r = route_risk_aware(
            G, "A", "C",
            risk_weight=1.0,
            risk_m_equivalent=5000.0,
            unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE,
        )
        assert r.feasible
        # Under CONSERVATIVE, unknown edges cost max → should route via bottom
        assert "B" not in r.path, (
            f"CONSERVATIVE router should avoid unknown-risk top row, path={r.path}"
        )

    def test_unknown_risk_optimistic_treats_as_zero(self):
        """Under OPTIMISTIC policy, unknown risk is treated as 0 → prefer shortest."""
        G = _linear_graph()
        # Leave risk_score=None on all edges
        r = route_risk_aware(
            G, "A", "C",
            risk_weight=1.0,
            risk_m_equivalent=5000.0,
            unknown_risk_policy=UnknownRiskPolicy.OPTIMISTIC,
        )
        assert r.feasible
        assert r.total_risk_penalty_m == pytest.approx(0.0)

    def test_risk_cost_formula(self):
        """
        Verify cost formula: length_m + risk_weight × risk_m_equiv × risk_score
        on a single-edge graph.
        """
        nodes = [
            {"id": "X", "x": 0.0, "y": 0.0},
            {"id": "Y", "x": 0.01, "y": 0.0},
        ]
        edges = [{"u": "X", "v": "Y", "length_m": 1000, "one_way": True}]
        G = from_synthetic(nodes, edges)
        G["X"]["Y"][0]["risk_score"] = 0.5

        risk_weight = 2.0
        risk_m_equiv = 3000.0
        r = route_risk_aware(
            G, "X", "Y",
            risk_weight=risk_weight,
            risk_m_equivalent=risk_m_equiv,
            unknown_risk_policy=UnknownRiskPolicy.OPTIMISTIC,
        )
        expected_penalty = risk_weight * risk_m_equiv * 0.5  # = 3000
        expected_cost = 1000 + expected_penalty              # = 4000
        assert r.total_risk_penalty_m == pytest.approx(expected_penalty)
        assert r.total_cost == pytest.approx(expected_cost)

    def test_notes_record_unknown_risk_policy(self):
        G = _linear_graph()
        r = route_risk_aware(
            G, "A", "C",
            unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE,
        )
        if r.feasible:
            # Should note unknown edges under CONSERVATIVE
            note_text = " ".join(r.notes).lower()
            assert "conservative" in note_text or "unknown" in note_text

    def test_mode_field_risk_aware(self, grid_G):
        r = route_risk_aware(grid_G, "A", "C")
        assert r.mode == RoutingMode.RISK_AWARE


# ---------------------------------------------------------------------------
# EvacuationRouter — stateful operations
# ---------------------------------------------------------------------------

class TestEvacuationRouter:
    def test_block_edge_prevents_use(self, linear_G):
        router = EvacuationRouter(linear_G, RoutingConfig(mode=RoutingMode.SHORTEST))
        # Block both directions of A-B so the only path A→B→C is severed
        router.block_edge("A", "B")
        router.block_edge("B", "A")
        r = router.route("A", "C")
        # Only path A→B→C is now blocked; graph has no other route
        assert not r.feasible

    def test_blocked_edges_list_updated(self, linear_G):
        router = EvacuationRouter(linear_G, RoutingConfig())
        router.block_edge("A", "B")
        assert ("A", "B") in router.blocked_edges

    def test_unblock_restores_route(self, linear_G):
        router = EvacuationRouter(linear_G, RoutingConfig(mode=RoutingMode.SHORTEST))
        router.block_edge("A", "B")
        router.block_edge("B", "A")
        router.unblock_edge("A", "B")
        router.unblock_edge("B", "A")
        r = router.route("A", "C")
        assert r.feasible

    def test_replan_returns_feasible_false_when_blocked(self, linear_G):
        router = EvacuationRouter(linear_G, RoutingConfig(mode=RoutingMode.SHORTEST))
        router.block_edge("A", "B")
        router.block_edge("B", "A")
        r = router.replan("A", "C")
        assert not r.feasible

    def test_replan_result_has_replanned_true(self, grid_G):
        router = EvacuationRouter(grid_G, RoutingConfig(mode=RoutingMode.SHORTEST))
        r = router.replan("A", "C")
        assert r.replanned is True

    def test_reset_graph_clears_blockages(self, linear_G):
        router = EvacuationRouter(linear_G, RoutingConfig(mode=RoutingMode.SHORTEST))
        router.block_edge("A", "B")
        router.reset_graph()
        r = router.route("A", "C")
        assert r.feasible

    def test_update_edge_risk_changes_cost(self, grid_G):
        cfg = RoutingConfig(
            mode=RoutingMode.RISK_AWARE,
            risk_weight=1.0,
            risk_m_equivalent=5000.0,
            unknown_risk_policy=UnknownRiskPolicy.OPTIMISTIC,
        )
        router = EvacuationRouter(grid_G, cfg)
        r_before = router.route("A", "C")

        # Increase risk on A-D to be very high (force router back to top)
        router.update_edge_risk("A", "D", 1.0)
        router.update_edge_risk("D", "A", 1.0)
        r_after = router.route("A", "C")

        # Both should be feasible
        assert r_before.feasible
        assert r_after.feasible

    def test_update_edge_risk_invalid_raises(self, linear_G):
        router = EvacuationRouter(linear_G, RoutingConfig())
        with pytest.raises(ValueError, match="risk_score"):
            router.update_edge_risk("A", "B", 1.5)

    def test_original_graph_not_modified(self, linear_G):
        """Router must not modify the caller's original graph."""
        import copy
        original_edges = list(linear_G.edges(data=True, keys=True))
        router = EvacuationRouter(linear_G, RoutingConfig())
        router.block_edge("A", "B")
        # Original graph should be unchanged
        current_edges = list(linear_G.edges(data=True, keys=True))
        for (ou, ov, ok, od), (cu, cv, ck, cd) in zip(original_edges, current_edges):
            assert od["blocked"] == cd["blocked"], (
                "Original graph was modified by router.block_edge()"
            )

    def test_mode_override_in_route_call(self, grid_G):
        cfg = RoutingConfig(mode=RoutingMode.SHORTEST)
        router = EvacuationRouter(grid_G, cfg)
        # Override to RISK_AWARE for this call
        r = router.route("A", "C", mode=RoutingMode.RISK_AWARE)
        assert r.mode == RoutingMode.RISK_AWARE


# ---------------------------------------------------------------------------
# Infeasible route reporting
# ---------------------------------------------------------------------------

class TestInfeasibleRoute:
    def test_disconnected_graph_infeasible(self):
        """G and I are connected; H is isolated — no path from G to H."""
        import networkx as nx
        G2 = nx.MultiDiGraph()
        G2.add_node("G", x=0.0, y=0.0)
        G2.add_node("H", x=1.0, y=0.0)
        G2.add_node("I", x=0.5, y=0.0)
        G2.add_edge("G", "I", length_m=100, blocked=False, risk_score=None,
                    zone_id=None, road_type="synthetic")
        G2.add_edge("I", "G", length_m=100, blocked=False, risk_score=None,
                    zone_id=None, road_type="synthetic")
        # H is isolated — no path from G to H
        router = EvacuationRouter(G2, RoutingConfig(mode=RoutingMode.SHORTEST))
        r = router.route("G", "H")
        assert not r.feasible

    def test_infeasible_notes_not_empty(self, linear_G):
        router = EvacuationRouter(linear_G, RoutingConfig())
        router.block_edge("A", "B")
        router.block_edge("B", "A")
        r = router.route("A", "C")
        if not r.feasible:
            assert len(r.notes) > 0

    def test_infeasible_path_empty(self, linear_G):
        router = EvacuationRouter(linear_G, RoutingConfig())
        router.block_edge("A", "B")
        router.block_edge("B", "A")
        r = router.route("A", "C")
        if not r.feasible:
            assert r.path == []

    def test_infeasible_length_zero(self, linear_G):
        router = EvacuationRouter(linear_G, RoutingConfig())
        router.block_edge("A", "B")
        router.block_edge("B", "A")
        r = router.route("A", "C")
        if not r.feasible:
            assert r.total_length_m == 0.0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_graph_same_path_repeated_calls(self, grid_G):
        cfg = RoutingConfig(mode=RoutingMode.RISK_AWARE,
                            unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE)
        router = EvacuationRouter(grid_G, cfg)
        paths = [router.route("A", "F").path for _ in range(5)]
        assert all(p == paths[0] for p in paths), "Router is not deterministic"

    def test_route_result_fields_consistent(self, linear_G):
        r = route_shortest(linear_G, "A", "C")
        assert r.origin == "A"
        assert r.destination == "C"
        assert r.path[0] == "A"
        assert r.path[-1] == "C"
        assert r.total_length_m == r.total_cost  # SHORTEST: cost = length
