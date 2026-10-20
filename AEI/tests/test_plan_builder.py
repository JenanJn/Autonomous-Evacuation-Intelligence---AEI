"""
Tests for src/api/plan_builder.py
====================================
Verifies the EvacuationPlan builder independently of the HTTP layer,
using the actual synthetic graph and existing backend modules.

ALL data produced by these tests is SYNTHETIC.
These tests do NOT validate real-world evacuation routes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from api.plan_builder import (
    SCENARIO_ID,
    DemoState,
    _DEMO_DESTINATION,
    _DEMO_NODES,
    _DEMO_ZONE_RISK_MAP,
    _make_demo_graph,
    _make_demo_risk_records,
    _resolve_origin,
    _serialise_allocation,
    _serialise_risk_records,
    _serialise_route,
    _serialise_shelters,
    build_clear,
    build_plan,
    build_replan,
)
from api.models import (
    AllocationResultResponse,
    EvacuationPlanResponse,
    RiskOutputRecordResponse,
    RouteResultResponse,
    ShelterResponse,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_state() -> DemoState:
    """A freshly initialised DemoState for each test."""
    return DemoState()


# ---------------------------------------------------------------------------
# DemoState initialisation
# ---------------------------------------------------------------------------

class TestDemoState:
    def test_primary_route_cached_at_startup(self, fresh_state):
        assert fresh_state.primary_route.feasible
        assert fresh_state.primary_route.path[0] == "A"
        assert fresh_state.primary_route.path[-1] == _DEMO_DESTINATION

    def test_origin_node_is_A(self, fresh_state):
        assert fresh_state.origin_node == "A"

    def test_two_shelters_present(self, fresh_state):
        assert len(fresh_state.shelters) == 2

    def test_shelters_snapped_to_network(self, fresh_state):
        for s in fresh_state.shelters:
            assert s.nearest_node is not None

    def test_six_risk_records(self, fresh_state):
        assert len(fresh_state.risk_records) == 6

    def test_reset_restores_primary_route(self, fresh_state):
        fresh_state.apply_blockages([["A", "B"], ["B", "A"]])
        fresh_state.reset()
        r = fresh_state.router.route("A", _DEMO_DESTINATION)
        assert r.feasible
        assert r.path == fresh_state.primary_route.path

    def test_reset_clears_blocked_edges(self, fresh_state):
        fresh_state.apply_blockages([["A", "B"]])
        assert ("A", "B") in fresh_state.router.blocked_edges
        fresh_state.reset()
        assert fresh_state.router.blocked_edges == []


# ---------------------------------------------------------------------------
# _make_demo_graph
# ---------------------------------------------------------------------------

class TestMakeDemoGraph:
    def test_six_nodes(self):
        G = _make_demo_graph()
        assert G.number_of_nodes() == 6

    def test_all_node_ids_present(self):
        G = _make_demo_graph()
        for node in ["A", "B", "C", "D", "E", "F"]:
            assert node in G.nodes

    def test_edges_have_length_m(self):
        G = _make_demo_graph()
        for u, v, k, d in G.edges(data=True, keys=True):
            assert "length_m" in d
            assert d["length_m"] > 0

    def test_edges_have_risk_score(self):
        G = _make_demo_graph()
        for u, v, k, d in G.edges(data=True, keys=True):
            assert "risk_score" in d
            assert d["risk_score"] is not None

    def test_edges_not_blocked_initially(self):
        G = _make_demo_graph()
        for u, v, k, d in G.edges(data=True, keys=True):
            assert d.get("blocked", False) is False


# ---------------------------------------------------------------------------
# _resolve_origin
# ---------------------------------------------------------------------------

class TestResolveOrigin:
    def test_uses_node_id_when_valid(self, fresh_state):
        node = _resolve_origin(fresh_state.graph, 0.0, 0.0, "B")
        assert node == "B"

    def test_snaps_gps_when_no_node_id(self, fresh_state):
        # (0,0) is exactly node A
        node = _resolve_origin(fresh_state.graph, 0.0, 0.0, None)
        assert node == "A"

    def test_snaps_gps_when_node_id_not_in_graph(self, fresh_state):
        # Unknown node_id → fall back to nearest GPS snap
        node = _resolve_origin(fresh_state.graph, 0.0, 0.0, "UNKNOWN_NODE")
        assert node == "A"

    def test_snaps_far_coord_to_nearest_node(self, fresh_state):
        # (0, 0.018) should snap to C
        node = _resolve_origin(fresh_state.graph, 0.0, 0.018, None)
        assert node == "C"


# ---------------------------------------------------------------------------
# _serialise_route
# ---------------------------------------------------------------------------

class TestSerialiseRoute:
    def test_returns_RouteResultResponse(self, fresh_state):
        r = _serialise_route(fresh_state.primary_route)
        assert isinstance(r, RouteResultResponse)

    def test_edges_are_lists_not_tuples(self, fresh_state):
        r = _serialise_route(fresh_state.primary_route)
        for edge in r.edges:
            assert isinstance(edge, list)
            assert len(edge) == 3

    def test_edge_key_is_int(self, fresh_state):
        r = _serialise_route(fresh_state.primary_route)
        for edge in r.edges:
            assert isinstance(edge[2], int)

    def test_mode_is_string(self, fresh_state):
        r = _serialise_route(fresh_state.primary_route)
        assert isinstance(r.mode, str)
        assert r.mode == "risk_aware"

    def test_path_contains_strings(self, fresh_state):
        r = _serialise_route(fresh_state.primary_route)
        for node in r.path:
            assert isinstance(node, str)

    def test_origin_and_destination_are_strings(self, fresh_state):
        r = _serialise_route(fresh_state.primary_route)
        assert isinstance(r.origin, str)
        assert isinstance(r.destination, str)

    def test_feasible_route_fields(self, fresh_state):
        r = _serialise_route(fresh_state.primary_route)
        assert r.feasible is True
        assert r.total_length_m > 0
        assert r.estimated_travel_time_s > 0


# ---------------------------------------------------------------------------
# _serialise_risk_records
# ---------------------------------------------------------------------------

class TestSerialiseRiskRecords:
    def test_count(self, fresh_state):
        out = _serialise_risk_records(fresh_state.risk_records)
        assert len(out) == 6

    def test_all_RiskOutputRecordResponse(self, fresh_state):
        for r in _serialise_risk_records(fresh_state.risk_records):
            assert isinstance(r, RiskOutputRecordResponse)

    def test_risk_category_is_string(self, fresh_state):
        for r in _serialise_risk_records(fresh_state.risk_records):
            assert isinstance(r.risk_category, str)
            assert r.risk_category in {"LOW", "MODERATE", "HIGH", "CRITICAL", "UNKNOWN"}

    def test_risk_status_is_string(self, fresh_state):
        for r in _serialise_risk_records(fresh_state.risk_records):
            assert isinstance(r.risk_status, str)

    def test_scoring_method_forwarded(self, fresh_state):
        out = _serialise_risk_records(
            fresh_state.risk_records, scoring_method="direct_proxy_uncalibrated"
        )
        for r in out:
            assert r.scoring_method == "direct_proxy_uncalibrated"

    def test_scoring_method_none_when_omitted(self, fresh_state):
        out = _serialise_risk_records(fresh_state.risk_records)
        for r in out:
            assert r.scoring_method is None

    def test_contract_version_correct(self, fresh_state):
        for r in _serialise_risk_records(fresh_state.risk_records):
            assert r.contract_version == "0.1.0"


# ---------------------------------------------------------------------------
# _serialise_shelters
# ---------------------------------------------------------------------------

class TestSerialiseShelters:
    def test_two_shelters(self, fresh_state):
        out = _serialise_shelters(fresh_state.shelters)
        assert len(out) == 2

    def test_all_ShelterResponse(self, fresh_state):
        for s in _serialise_shelters(fresh_state.shelters):
            assert isinstance(s, ShelterResponse)

    def test_status_is_string(self, fresh_state):
        for s in _serialise_shelters(fresh_state.shelters):
            assert isinstance(s.status, str)
            assert s.status in {"OPEN", "FULL", "CLOSED"}

    def test_nearest_node_is_str_or_none(self, fresh_state):
        for s in _serialise_shelters(fresh_state.shelters):
            assert s.nearest_node is None or isinstance(s.nearest_node, str)

    def test_remaining_capacity_present(self, fresh_state):
        for s in _serialise_shelters(fresh_state.shelters):
            assert s.remaining_capacity == s.capacity - s.occupied


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------

class TestBuildPlan:
    def test_returns_EvacuationPlanResponse(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert isinstance(p, EvacuationPlanResponse)

    def test_scenario_id(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.scenario_id == SCENARIO_ID

    def test_is_simulated_true(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.is_simulated is True

    def test_blockage_active_false(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.blockage_active is False

    def test_replanned_route_is_none(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.replanned_route is None

    def test_origin_node_snaps_from_gps(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.origin_node == "A"

    def test_origin_node_from_explicit_node_id(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.009, "B")
        assert p.origin_node == "B"

    def test_primary_route_feasible(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.primary_route.feasible is True

    def test_primary_route_path_starts_at_origin(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.primary_route.path[0] == p.origin_node

    def test_primary_route_path_ends_at_shelter(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.primary_route.path[-1] == _DEMO_DESTINATION

    def test_primary_route_edges_are_lists(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        for e in p.primary_route.edges:
            assert isinstance(e, list)
            assert len(e) == 3

    def test_six_zone_risks(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert len(p.zone_risks) == 6

    def test_zone_risk_categories_are_strings(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        for z in p.zone_risks:
            assert z.risk_category in {"LOW", "MODERATE", "HIGH", "CRITICAL", "UNKNOWN"}

    def test_scoring_method_present(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        for z in p.zone_risks:
            assert z.scoring_method == "direct_proxy_uncalibrated"

    def test_two_shelters(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert len(p.shelters) == 2

    def test_shelter_status_strings(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        for s in p.shelters:
            assert s.status in {"OPEN", "FULL", "CLOSED"}

    def test_allocation_positive_admitted(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.allocation.total_admitted > 0

    def test_allocation_no_unassigned(self, fresh_state):
        # Demo demand (240) fits within total capacity (350)
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.allocation.total_unassigned == 0

    def test_warnings_not_empty(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert len(p.warnings) > 0

    def test_simulated_in_warnings(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        combined = " ".join(p.warnings).upper()
        assert "SYNTHETIC" in combined or "SIMULATED" in combined

    def test_contract_version(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        assert p.contract_version == "0.1.0"

    def test_generated_at_is_iso8601(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        # Should match YYYY-MM-DDTHH:MM:SSZ
        from datetime import datetime, timezone
        dt = datetime.strptime(p.generated_at, "%Y-%m-%dT%H:%M:%SZ")
        assert dt is not None

    def test_repeated_calls_produce_same_route(self, fresh_state):
        p1 = build_plan(fresh_state, 0.0, 0.0, None)
        p2 = build_plan(fresh_state, 0.0, 0.0, None)
        assert p1.primary_route.path == p2.primary_route.path

    def test_resets_prior_blockage(self, fresh_state):
        # Apply a blockage then call /plan — should return clean route
        build_plan(fresh_state, 0.0, 0.0, None)
        build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        p = build_plan(fresh_state, 0.0, 0.0, None)
        # After reset, primary route should go through B again
        assert p.blockage_active is False
        assert p.replanned_route is None


# ---------------------------------------------------------------------------
# build_replan
# ---------------------------------------------------------------------------

class TestBuildReplan:
    def _setup(self, state: DemoState) -> None:
        """Run build_plan first so state is clean."""
        build_plan(state, 0.0, 0.0, None)

    def test_returns_EvacuationPlanResponse(self, fresh_state):
        self._setup(fresh_state)
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        assert isinstance(rp, EvacuationPlanResponse)

    def test_blockage_active_true(self, fresh_state):
        self._setup(fresh_state)
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        assert rp.blockage_active is True

    def test_replanned_route_not_none(self, fresh_state):
        self._setup(fresh_state)
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        assert rp.replanned_route is not None

    def test_replanned_route_feasible(self, fresh_state):
        self._setup(fresh_state)
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        assert rp.replanned_route.feasible is True

    def test_replanned_avoids_blocked_edge(self, fresh_state):
        self._setup(fresh_state)
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        path = rp.replanned_route.path
        # A→B→C is blocked; route should go via D/E/F
        for i in range(len(path) - 1):
            pair = (path[i], path[i + 1])
            assert pair not in {("A", "B"), ("B", "A")}, (
                f"Blocked edge {pair} appears in replanned path {path}"
            )

    def test_replanned_flag_true(self, fresh_state):
        self._setup(fresh_state)
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        assert rp.replanned_route.replanned is True

    def test_primary_route_preserved(self, fresh_state):
        self._setup(fresh_state)
        original_path = fresh_state.primary_route.path[:]
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        assert rp.primary_route.path == original_path

    def test_replanned_longer_than_primary(self, fresh_state):
        self._setup(fresh_state)
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        assert rp.replanned_route.total_length_m > rp.primary_route.total_length_m

    def test_blockage_warning_in_warnings(self, fresh_state):
        self._setup(fresh_state)
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        combined = " ".join(rp.warnings)
        assert "blockage" in combined.lower() or "blocked" in combined.lower()

    def test_replanned_edges_are_lists(self, fresh_state):
        self._setup(fresh_state)
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        for e in rp.replanned_route.edges:
            assert isinstance(e, list)
            assert len(e) == 3

    def test_invalid_node_raises_ValueError(self, fresh_state):
        self._setup(fresh_state)
        with pytest.raises(ValueError, match="not in the road-network"):
            build_replan(fresh_state, [["X", "Y"]])

    def test_invalid_u_node_raises_ValueError(self, fresh_state):
        self._setup(fresh_state)
        with pytest.raises(ValueError, match="'BOGUS'"):
            build_replan(fresh_state, [["BOGUS", "B"]])

    def test_invalid_v_node_raises_ValueError(self, fresh_state):
        self._setup(fresh_state)
        with pytest.raises(ValueError, match="'BOGUS'"):
            build_replan(fresh_state, [["A", "BOGUS"]])

    def test_all_paths_blocked_returns_infeasible_route(self, fresh_state):
        self._setup(fresh_state)
        # Block ALL exits from A
        rp = build_replan(fresh_state, [
            ["A", "B"], ["B", "A"],
            ["A", "D"], ["D", "A"],
        ])
        assert rp.blockage_active is True
        assert rp.replanned_route is not None
        assert rp.replanned_route.feasible is False

    def test_is_simulated_still_true(self, fresh_state):
        self._setup(fresh_state)
        rp = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        assert rp.is_simulated is True

    def test_deterministic_replanning(self, fresh_state):
        """Two successive replan calls with the same edges give the same path."""
        build_plan(fresh_state, 0.0, 0.0, None)
        rp1 = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        # Clear and redo
        build_plan(fresh_state, 0.0, 0.0, None)
        rp2 = build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        assert rp1.replanned_route.path == rp2.replanned_route.path


# ---------------------------------------------------------------------------
# build_clear
# ---------------------------------------------------------------------------

class TestBuildClear:
    def test_returns_EvacuationPlanResponse(self, fresh_state):
        build_plan(fresh_state, 0.0, 0.0, None)
        build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        cl = build_clear(fresh_state)
        assert isinstance(cl, EvacuationPlanResponse)

    def test_blockage_active_false_after_clear(self, fresh_state):
        build_plan(fresh_state, 0.0, 0.0, None)
        build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        cl = build_clear(fresh_state)
        assert cl.blockage_active is False

    def test_replanned_route_none_after_clear(self, fresh_state):
        build_plan(fresh_state, 0.0, 0.0, None)
        build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        cl = build_clear(fresh_state)
        assert cl.replanned_route is None

    def test_primary_route_restored_after_clear(self, fresh_state):
        original = build_plan(fresh_state, 0.0, 0.0, None).primary_route.path
        build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        cl = build_clear(fresh_state)
        assert cl.primary_route.path == original

    def test_clear_without_prior_replan_is_idempotent(self, fresh_state):
        p = build_plan(fresh_state, 0.0, 0.0, None)
        cl = build_clear(fresh_state)
        assert cl.primary_route.path == p.primary_route.path

    def test_router_unblocked_after_clear(self, fresh_state):
        build_plan(fresh_state, 0.0, 0.0, None)
        build_replan(fresh_state, [["A", "B"], ["B", "A"]])
        build_clear(fresh_state)
        # Router should now be able to use A→B again
        assert fresh_state.router.blocked_edges == []
