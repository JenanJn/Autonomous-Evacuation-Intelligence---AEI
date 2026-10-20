"""
Tests for src/gis/network_loader.py
=====================================
All graphs are SYNTHETIC — no real road data is used.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import networkx as nx
import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from gis.network_loader import (
    NetworkLoadError,
    NetworkMetadata,
    NetworkValidationError,
    block_edge,
    edge_length_m,
    from_synthetic,
    get_graph_summary,
    nearest_node,
    node_distance_m,
    set_edge_risk,
    unblock_edge,
    validate_graph,
    _haversine_m,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def small_graph() -> nx.MultiDiGraph:
    """
    Minimal 4-node synthetic graph:
        A ── B ── C
             │
             D
    All edges bidirectional.
    """
    nodes = [
        {"id": "A", "x": 0.000, "y": 0.000},
        {"id": "B", "x": 0.009, "y": 0.000},
        {"id": "C", "x": 0.018, "y": 0.000},
        {"id": "D", "x": 0.009, "y": -0.005},
    ]
    edges = [
        {"u": "A", "v": "B", "length_m": 1000, "road_type": "primary",   "one_way": False},
        {"u": "B", "v": "C", "length_m": 1000, "road_type": "primary",   "one_way": False},
        {"u": "B", "v": "D", "length_m":  500, "road_type": "secondary", "one_way": False},
    ]
    return from_synthetic(nodes, edges)


@pytest.fixture
def triangle_graph() -> nx.MultiDiGraph:
    """Simple 3-node triangle, all bidirectional."""
    nodes = [
        {"id": 1, "x": 0.0, "y": 0.0},
        {"id": 2, "x": 0.1, "y": 0.0},
        {"id": 3, "x": 0.05, "y": 0.05},
    ]
    edges = [
        {"u": 1, "v": 2, "length_m": 5000, "one_way": False},
        {"u": 2, "v": 3, "length_m": 4000, "one_way": False},
        {"u": 1, "v": 3, "length_m": 6000, "one_way": False},
    ]
    return from_synthetic(nodes, edges)


# ---------------------------------------------------------------------------
# from_synthetic — structure and attributes
# ---------------------------------------------------------------------------

class TestFromSynthetic:
    def test_returns_multidigraph(self, small_graph):
        assert isinstance(small_graph, nx.MultiDiGraph)

    def test_correct_node_count(self, small_graph):
        assert small_graph.number_of_nodes() == 4

    def test_correct_edge_count_bidirectional(self, small_graph):
        # 3 edge specs × 2 directions = 6 directed edges
        assert small_graph.number_of_edges() == 6

    def test_one_way_edge_not_reversed(self):
        nodes = [
            {"id": "X", "x": 0.0, "y": 0.0},
            {"id": "Y", "x": 0.01, "y": 0.0},
        ]
        edges = [{"u": "X", "v": "Y", "length_m": 500, "one_way": True}]
        G = from_synthetic(nodes, edges)
        assert G.has_edge("X", "Y")
        assert not G.has_edge("Y", "X")

    def test_nodes_have_x_y(self, small_graph):
        for n, data in small_graph.nodes(data=True):
            assert "x" in data, f"Node {n} missing x"
            assert "y" in data, f"Node {n} missing y"

    def test_edges_have_length_m(self, small_graph):
        for u, v, k, data in small_graph.edges(data=True, keys=True):
            assert "length_m" in data
            assert data["length_m"] > 0

    def test_edges_have_blocked_false(self, small_graph):
        for _, _, _, data in small_graph.edges(data=True, keys=True):
            assert data["blocked"] is False

    def test_edges_have_risk_score_none(self, small_graph):
        for _, _, _, data in small_graph.edges(data=True, keys=True):
            assert data["risk_score"] is None

    def test_edges_have_road_type(self, small_graph):
        for _, _, _, data in small_graph.edges(data=True, keys=True):
            assert "road_type" in data

    def test_crs_stored(self, small_graph):
        assert "crs" in small_graph.graph

    def test_metadata_stored(self, small_graph):
        assert "_aei_meta" in small_graph.graph
        meta = small_graph.graph["_aei_meta"]
        assert isinstance(meta, NetworkMetadata)
        assert meta.source == "synthetic"

    def test_length_m_computed_from_coords_when_missing(self):
        """If length_m is absent, it should be computed from haversine."""
        nodes = [
            {"id": "P", "x": 0.0, "y": 0.0},
            {"id": "Q", "x": 0.01, "y": 0.0},
        ]
        edges = [{"u": "P", "v": "Q", "one_way": True}]  # no length_m
        G = from_synthetic(nodes, edges)
        assert G["P"]["Q"][0]["length_m"] > 0

    def test_extra_edge_attrs_preserved(self):
        nodes = [
            {"id": "A", "x": 0.0, "y": 0.0},
            {"id": "B", "x": 0.01, "y": 0.0},
        ]
        edges = [{"u": "A", "v": "B", "length_m": 1000, "custom_tag": "highway",
                  "one_way": True}]
        G = from_synthetic(nodes, edges)
        assert G["A"]["B"][0]["custom_tag"] == "highway"


# ---------------------------------------------------------------------------
# validate_graph
# ---------------------------------------------------------------------------

class TestValidateGraph:
    def test_valid_graph_no_error(self, small_graph):
        validate_graph(small_graph)  # should not raise

    def test_single_node_raises(self):
        G = nx.MultiDiGraph()
        G.add_node(1, x=0.0, y=0.0)
        with pytest.raises(NetworkValidationError, match="at least 2"):
            validate_graph(G)

    def test_non_multidigraph_raises(self):
        G = nx.Graph()
        G.add_node(1)
        G.add_node(2)
        with pytest.raises(NetworkValidationError, match="MultiDiGraph"):
            validate_graph(G)

    def test_missing_xy_raises(self):
        G = nx.MultiDiGraph()
        G.add_node(1)           # no x, y
        G.add_node(2, x=0.0, y=0.0)
        G.add_edge(1, 2, length_m=100, blocked=False)
        with pytest.raises(NetworkValidationError, match="coordinates"):
            validate_graph(G)

    def test_zero_length_edge_raises(self):
        G = nx.MultiDiGraph()
        G.add_node(1, x=0.0, y=0.0)
        G.add_node(2, x=0.01, y=0.0)
        G.add_edge(1, 2, length_m=0.0, blocked=False)  # zero length
        with pytest.raises(NetworkValidationError, match="length_m"):
            validate_graph(G)

    def test_missing_blocked_attr_raises(self):
        G = nx.MultiDiGraph()
        G.add_node(1, x=0.0, y=0.0)
        G.add_node(2, x=0.01, y=0.0)
        G.add_edge(1, 2, length_m=100)  # missing blocked
        with pytest.raises(NetworkValidationError):
            validate_graph(G)


# ---------------------------------------------------------------------------
# block_edge / unblock_edge / set_edge_risk
# ---------------------------------------------------------------------------

class TestEdgeStateManagement:
    def test_block_edge_sets_blocked_true(self, small_graph):
        block_edge(small_graph, "A", "B")
        for key in small_graph["A"]["B"]:
            assert small_graph["A"]["B"][key]["blocked"] is True

    def test_unblock_edge_sets_blocked_false(self, small_graph):
        block_edge(small_graph, "A", "B")
        unblock_edge(small_graph, "A", "B")
        for key in small_graph["A"]["B"]:
            assert small_graph["A"]["B"][key]["blocked"] is False

    def test_block_nonexistent_edge_logs_warning(self, small_graph):
        # Should not raise — logs warning only
        block_edge(small_graph, "A", "C")  # no direct edge

    def test_set_edge_risk_valid(self, small_graph):
        set_edge_risk(small_graph, "A", "B", 0.75)
        for key in small_graph["A"]["B"]:
            assert small_graph["A"]["B"][key]["risk_score"] == pytest.approx(0.75)

    def test_set_edge_risk_out_of_range_raises(self, small_graph):
        with pytest.raises(ValueError, match="risk_score"):
            set_edge_risk(small_graph, "A", "B", 1.5)

    def test_set_edge_risk_negative_raises(self, small_graph):
        with pytest.raises(ValueError, match="risk_score"):
            set_edge_risk(small_graph, "A", "B", -0.1)

    def test_block_does_not_remove_edge(self, small_graph):
        block_edge(small_graph, "A", "B")
        assert small_graph.has_edge("A", "B")


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

class TestGeometryHelpers:
    def test_edge_length_m_returns_stored_value(self, small_graph):
        assert edge_length_m(small_graph, "A", "B") == pytest.approx(1000.0)

    def test_node_distance_m_positive(self, small_graph):
        d = node_distance_m(small_graph, "A", "B")
        assert d > 0

    def test_node_distance_m_symmetric(self, small_graph):
        d_ab = node_distance_m(small_graph, "A", "B")
        d_ba = node_distance_m(small_graph, "B", "A")
        assert d_ab == pytest.approx(d_ba, rel=1e-9)

    def test_node_distance_m_same_node_zero(self, small_graph):
        d = node_distance_m(small_graph, "A", "A")
        assert d == pytest.approx(0.0, abs=1e-6)

    def test_nearest_node_returns_correct_node(self, small_graph):
        # 0.000, 0.000 should snap to "A"
        result = nearest_node(small_graph, lat=0.000, lon=0.000)
        assert result == "A"

    def test_nearest_node_b(self, small_graph):
        # 0.009, 0.000 longitude → "B"
        result = nearest_node(small_graph, lat=0.000, lon=0.009)
        assert result == "B"

    def test_haversine_known_distance(self):
        # ~111 km per degree latitude
        d = _haversine_m(0.0, 0.0, 1.0, 0.0)
        assert 110_000 < d < 112_000, f"Got {d:.0f} m, expected ~111 km"

    def test_haversine_symmetric(self):
        d1 = _haversine_m(10.0, 20.0, 11.0, 21.0)
        d2 = _haversine_m(11.0, 21.0, 10.0, 20.0)
        assert d1 == pytest.approx(d2, rel=1e-10)


# ---------------------------------------------------------------------------
# get_graph_summary
# ---------------------------------------------------------------------------

class TestGetGraphSummary:
    def test_summary_keys_present(self, small_graph):
        s = get_graph_summary(small_graph)
        for key in ("nodes", "edges", "total_length_m", "blocked_edges",
                    "edges_with_risk", "edges_without_risk", "crs", "source"):
            assert key in s, f"Key '{key}' missing from summary"

    def test_summary_node_count(self, small_graph):
        assert get_graph_summary(small_graph)["nodes"] == 4

    def test_summary_blocked_zero_initially(self, small_graph):
        assert get_graph_summary(small_graph)["blocked_edges"] == 0

    def test_summary_blocked_increments(self, small_graph):
        block_edge(small_graph, "A", "B")
        assert get_graph_summary(small_graph)["blocked_edges"] == 1

    def test_summary_risk_counts(self, small_graph):
        s = get_graph_summary(small_graph)
        assert s["edges_with_risk"] == 0
        assert s["edges_without_risk"] == small_graph.number_of_edges()


# ---------------------------------------------------------------------------
# from_graphml
# ---------------------------------------------------------------------------

class TestFromGraphML:
    def test_file_not_found_raises(self, tmp_path):
        from gis.network_loader import from_graphml
        with pytest.raises(FileNotFoundError):
            from_graphml(tmp_path / "nonexistent.graphml")
