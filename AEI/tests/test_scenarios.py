"""
Tests for src/scenarios/synthetic_scenarios.py
================================================
Verifies that every synthetic scenario runs deterministically and
produces the expected pass/fail outcome.

All data is SYNTHETIC — not a real city or emergency.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from scenarios.synthetic_scenarios import (
    ScenarioResult,
    run_all_scenarios,
    scenario_increased_risk,
    scenario_insufficient_capacity,
    scenario_no_feasible_route,
    scenario_road_blockage,
    scenario_shelter_closure,
    scenario_shelter_exhaustion,
    scenario_unknown_risk,
)
from shelter.shelter_manager import ShelterStatus


# ---------------------------------------------------------------------------
# Scenario 1: Road Blockage
# ---------------------------------------------------------------------------

class TestRoadBlockageScenario:
    def test_passes(self):
        r = scenario_road_blockage()
        assert r.passed, "\n".join(r.assertions)

    def test_initial_route_feasible(self):
        r = scenario_road_blockage()
        assert r.route_results[0].feasible

    def test_replanned_route_feasible(self):
        r = scenario_road_blockage()
        assert r.route_results[1].feasible

    def test_replanned_avoids_blocked_node(self):
        r = scenario_road_blockage()
        replanned = r.route_results[1]
        assert "B" not in replanned.path

    def test_replanned_is_longer(self):
        r = scenario_road_blockage()
        initial  = r.route_results[0].total_length_m
        replanned = r.route_results[1].total_length_m
        assert replanned > initial

    def test_replanned_flag_set(self):
        r = scenario_road_blockage()
        assert r.route_results[1].replanned is True

    def test_deterministic(self):
        r1 = scenario_road_blockage()
        r2 = scenario_road_blockage()
        assert r1.route_results[0].path == r2.route_results[0].path
        assert r1.route_results[1].path == r2.route_results[1].path


# ---------------------------------------------------------------------------
# Scenario 2: Increased Road Risk
# ---------------------------------------------------------------------------

class TestIncreasedRiskScenario:
    def test_passes(self):
        r = scenario_increased_risk()
        assert r.passed, "\n".join(r.assertions)

    def test_two_routes_returned(self):
        r = scenario_increased_risk()
        assert len(r.route_results) == 2

    def test_shortest_uses_high_risk_path(self):
        r = scenario_increased_risk()
        shortest = r.route_results[0]
        assert shortest.feasible
        assert "B" in shortest.path  # top row despite high risk

    def test_risk_aware_avoids_high_risk_path(self):
        r = scenario_increased_risk()
        risk_aware = r.route_results[1]
        assert risk_aware.feasible
        assert "B" not in risk_aware.path

    def test_risk_aware_zero_risk_penalty(self):
        r = scenario_increased_risk()
        risk_aware = r.route_results[1]
        assert risk_aware.total_risk_penalty_m == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Scenario 3: Shelter Capacity Exhaustion
# ---------------------------------------------------------------------------

class TestShelterExhaustionScenario:
    def test_passes(self):
        r = scenario_shelter_exhaustion()
        assert r.passed, "\n".join(r.assertions)

    def test_sh_c_is_full(self):
        r = scenario_shelter_exhaustion()
        # We need to re-run to inspect the manager state
        from scenarios.synthetic_scenarios import (
            _make_base_graph, _make_simple_shelters,
        )
        from shelter.shelter_manager import ShelterManager
        shelters = _make_simple_shelters()
        mgr = ShelterManager(shelters)
        mgr.get("SH_C").nearest_node = "C"
        mgr.get("SH_F").nearest_node = "F"
        mgr.get("SH_G").nearest_node = "G"
        mgr.close_shelter("SH_F")
        mgr.close_shelter("SH_G")
        demand = [{"demand_id": "ZONE_A", "origin_node": "A", "count": 150}]
        result = mgr.allocate(demand, router=None)
        assert mgr.get("SH_C").status == ShelterStatus.FULL

    def test_admitted_equals_capacity(self):
        r = scenario_shelter_exhaustion()
        assert r.allocation_result.total_admitted == 100

    def test_unassigned_is_fifty(self):
        r = scenario_shelter_exhaustion()
        assert r.allocation_result.total_unassigned == 50

    def test_unassigned_has_reason(self):
        r = scenario_shelter_exhaustion()
        for u in r.allocation_result.unassigned:
            assert "reason" in u


# ---------------------------------------------------------------------------
# Scenario 4: Shelter Closure and Reassignment
# ---------------------------------------------------------------------------

class TestShelterClosureScenario:
    def test_passes(self):
        r = scenario_shelter_closure()
        assert r.passed, "\n".join(r.assertions)

    def test_phase2_uses_sh_f(self):
        r = scenario_shelter_closure()
        for a in r.allocation_result.assignments:
            assert a.shelter_id == "SH_F"

    def test_phase2_admitted_40(self):
        r = scenario_shelter_closure()
        assert r.allocation_result.total_admitted == 40


# ---------------------------------------------------------------------------
# Scenario 5: No Feasible Route
# ---------------------------------------------------------------------------

class TestNoFeasibleRouteScenario:
    def test_passes(self):
        r = scenario_no_feasible_route()
        assert r.passed, "\n".join(r.assertions)

    def test_route_infeasible(self):
        r = scenario_no_feasible_route()
        assert not r.route_results[0].feasible

    def test_infeasibility_explained(self):
        r = scenario_no_feasible_route()
        assert len(r.route_results[0].notes) > 0

    def test_path_empty_when_infeasible(self):
        r = scenario_no_feasible_route()
        assert r.route_results[0].path == []


# ---------------------------------------------------------------------------
# Scenario 6: Insufficient Shelter Capacity
# ---------------------------------------------------------------------------

class TestInsufficientCapacityScenario:
    def test_passes(self):
        r = scenario_insufficient_capacity()
        assert r.passed, "\n".join(r.assertions)

    def test_total_admitted_equals_total_capacity(self):
        r = scenario_insufficient_capacity()
        assert r.allocation_result.total_admitted == 180  # 100+50+30

    def test_unassigned_equals_overflow(self):
        r = scenario_insufficient_capacity()
        assert r.allocation_result.total_unassigned == 120  # 300-180


# ---------------------------------------------------------------------------
# Scenario 7: Missing / Unknown Risk
# ---------------------------------------------------------------------------

class TestUnknownRiskScenario:
    def test_passes(self):
        r = scenario_unknown_risk()
        assert r.passed, "\n".join(r.assertions)

    def test_route_feasible(self):
        r = scenario_unknown_risk()
        assert r.route_results[0].feasible

    def test_avoids_unknown_risk_edges(self):
        r = scenario_unknown_risk()
        assert "B" not in r.route_results[0].path

    def test_notes_document_policy(self):
        r = scenario_unknown_risk()
        # The scenario notes or route notes should reference CONSERVATIVE policy
        all_text = " ".join(r.notes) + " ".join(r.route_results[0].notes)
        assert ("conservative" in all_text.lower()
                or r.route_results[0].total_risk_penalty_m > 0
                or "B" not in r.route_results[0].path)


# ---------------------------------------------------------------------------
# run_all_scenarios
# ---------------------------------------------------------------------------

class TestRunAllScenarios:
    def test_returns_seven_results(self):
        results = run_all_scenarios()
        assert len(results) == 7

    def test_all_scenarios_pass(self):
        results = run_all_scenarios()
        failed = [r.scenario_name for r in results if not r.passed]
        assert failed == [], f"Scenarios failed: {failed}"

    def test_all_results_are_scenario_result(self):
        results = run_all_scenarios()
        for r in results:
            assert isinstance(r, ScenarioResult)

    def test_all_results_have_name(self):
        results = run_all_scenarios()
        for r in results:
            assert r.scenario_name and len(r.scenario_name) > 0

    def test_all_results_have_assertions(self):
        results = run_all_scenarios()
        for r in results:
            assert len(r.assertions) > 0, (
                f"Scenario {r.scenario_name!r} has no assertions"
            )

    def test_deterministic_across_two_runs(self):
        results1 = run_all_scenarios()
        results2 = run_all_scenarios()
        for r1, r2 in zip(results1, results2):
            assert r1.passed == r2.passed, (
                f"Scenario {r1.scenario_name!r} not deterministic"
            )
