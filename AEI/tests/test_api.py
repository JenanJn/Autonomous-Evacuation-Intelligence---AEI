"""
Tests for src/api/main.py  (FastAPI endpoints)
================================================
Uses FastAPI ``TestClient`` (backed by ``httpx``) to exercise all four
endpoints over a real in-process HTTP transport.

A single shared ``client`` fixture is created per test module so the
``DemoState`` lifecycle events fire exactly once.

ALL data produced by these tests is SYNTHETIC.
These tests do NOT validate real-world evacuation safety.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from fastapi.testclient import TestClient

from api.main import app
from api.plan_builder import SCENARIO_ID, _DEMO_DESTINATION


# ---------------------------------------------------------------------------
# Shared client fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client() -> TestClient:
    """
    One TestClient per module.  The lifespan context manager fires once,
    so DemoState is initialised once and shared across all tests in this
    file — matching real server behaviour.
    """
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper — assert response is a well-formed EvacuationPlan
# ---------------------------------------------------------------------------

def _assert_plan_shape(data: dict) -> None:
    """Common field-presence assertions for every EvacuationPlan response."""
    required_top = {
        "scenario_id", "generated_at", "is_simulated", "blockage_active",
        "origin_node", "origin_label", "zone_risks", "primary_route",
        "replanned_route", "shelters", "allocation", "warnings",
        "contract_version",
    }
    for key in required_top:
        assert key in data, f"Missing top-level key: {key!r}"

    # primary_route shape
    pr = data["primary_route"]
    for key in ("feasible", "path", "edges", "total_length_m", "total_cost",
                "total_risk_penalty_m", "estimated_travel_time_s",
                "mode", "origin", "destination", "replanned", "notes"):
        assert key in pr, f"primary_route missing key: {key!r}"

    # edges serialise as [[u, v, key], ...]
    for edge in pr["edges"]:
        assert isinstance(edge, list), f"edge is not a list: {edge!r}"
        assert len(edge) == 3, f"edge should have 3 elements: {edge!r}"

    # zone_risks
    assert len(data["zone_risks"]) == 6
    for z in data["zone_risks"]:
        for key in ("zone_id", "risk_score", "risk_category", "data_freshness",
                    "risk_status", "contributing_factors", "contract_version"):
            assert key in z, f"zone_risk missing key: {key!r}"
        assert z["risk_category"] in {"LOW", "MODERATE", "HIGH", "CRITICAL", "UNKNOWN"}
        assert z["risk_status"] in {"OK", "NO_DATA", "STALE_DATA", "SCORING_ERROR", "INVALID_INPUT"}

    # shelters
    assert len(data["shelters"]) == 2
    for s in data["shelters"]:
        for key in ("shelter_id", "name", "lat", "lon", "capacity", "occupied",
                    "remaining_capacity", "status", "nearest_node",
                    "data_source", "notes"):
            assert key in s, f"shelter missing key: {key!r}"
        assert s["status"] in {"OPEN", "FULL", "CLOSED"}

    # allocation
    alloc = data["allocation"]
    for key in ("assignments", "unassigned", "total_admitted", "total_requested",
                "total_unassigned", "notes"):
        assert key in alloc, f"allocation missing key: {key!r}"

    # contract version
    assert data["contract_version"] == "0.1.0"


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_status_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_status_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_version_present(self, client):
        data = client.get("/health").json()
        assert "version" in data
        assert data["version"] == "0.1.0"

    def test_backend_url_present(self, client):
        data = client.get("/health").json()
        assert "backend_url" in data
        assert isinstance(data["backend_url"], str)

    def test_response_keys(self, client):
        data = client.get("/health").json()
        assert set(data.keys()) == {"status", "version", "backend_url"}


# ---------------------------------------------------------------------------
# POST /plan  — valid requests
# ---------------------------------------------------------------------------

class TestPlan:
    def test_status_200(self, client):
        r = client.post("/plan", json={"lat": 0.0, "lon": 0.0})
        assert r.status_code == 200

    def test_response_shape(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        _assert_plan_shape(data)

    def test_scenario_id(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["scenario_id"] == SCENARIO_ID

    def test_is_simulated_true(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["is_simulated"] is True

    def test_blockage_active_false(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["blockage_active"] is False

    def test_replanned_route_null(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["replanned_route"] is None

    def test_primary_route_feasible(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["primary_route"]["feasible"] is True

    def test_origin_snapped_to_A(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["origin_node"] == "A"

    def test_route_ends_at_shelter(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["primary_route"]["path"][-1] == _DEMO_DESTINATION

    def test_edges_are_lists(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        for edge in data["primary_route"]["edges"]:
            assert isinstance(edge, list)
            assert len(edge) == 3

    def test_mode_is_string(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert isinstance(data["primary_route"]["mode"], str)

    def test_scoring_method_present(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        for z in data["zone_risks"]:
            assert z["scoring_method"] == "direct_proxy_uncalibrated"

    def test_simulated_banner_in_warnings(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        combined = " ".join(data["warnings"]).upper()
        assert "SYNTHETIC" in combined or "SIMULATED" in combined

    def test_allocation_admitted_positive(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["allocation"]["total_admitted"] > 0

    def test_with_explicit_node_id(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.009, "node_id": "B"}).json()
        assert data["origin_node"] == "B"
        assert data["primary_route"]["feasible"] is True

    def test_different_origin_different_path(self, client):
        data_a = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        data_d = client.post("/plan", json={"lat": -0.005, "lon": 0.0}).json()
        assert data_a["origin_node"] != data_d["origin_node"]

    def test_repeated_calls_same_path(self, client):
        p1 = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        p2 = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert p1["primary_route"]["path"] == p2["primary_route"]["path"]

    def test_plan_resets_active_blockage(self, client):
        # Create a blockage then call /plan — blockage must be gone
        client.post("/plan", json={"lat": 0.0, "lon": 0.0})
        client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        })
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["blockage_active"] is False
        assert data["replanned_route"] is None

    def test_generated_at_iso8601(self, client):
        from datetime import datetime
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        dt = datetime.strptime(data["generated_at"], "%Y-%m-%dT%H:%M:%SZ")
        assert dt is not None


# ---------------------------------------------------------------------------
# POST /plan  — invalid input
# ---------------------------------------------------------------------------

class TestPlanInvalidInput:
    def test_lat_too_large_returns_422(self, client):
        r = client.post("/plan", json={"lat": 91.0, "lon": 0.0})
        assert r.status_code == 422

    def test_lat_too_small_returns_422(self, client):
        r = client.post("/plan", json={"lat": -91.0, "lon": 0.0})
        assert r.status_code == 422

    def test_lon_too_large_returns_422(self, client):
        r = client.post("/plan", json={"lat": 0.0, "lon": 181.0})
        assert r.status_code == 422

    def test_lon_too_small_returns_422(self, client):
        r = client.post("/plan", json={"lat": 0.0, "lon": -181.0})
        assert r.status_code == 422

    def test_missing_lat_returns_422(self, client):
        r = client.post("/plan", json={"lon": 0.0})
        assert r.status_code == 422

    def test_missing_lon_returns_422(self, client):
        r = client.post("/plan", json={"lat": 0.0})
        assert r.status_code == 422

    def test_empty_body_returns_422(self, client):
        r = client.post("/plan", json={})
        assert r.status_code == 422

    def test_unknown_node_id_snaps_to_nearest(self, client):
        # Unknown node_id should fall back to GPS snap, not error
        r = client.post("/plan", json={"lat": 0.0, "lon": 0.0, "node_id": "NOTANODE"})
        assert r.status_code == 200
        data = r.json()
        assert data["origin_node"] == "A"   # GPS (0,0) → nearest is A


# ---------------------------------------------------------------------------
# POST /plan/replan  — valid blockage
# ---------------------------------------------------------------------------

class TestReplan:
    @pytest.fixture(autouse=True)
    def reset_before_each(self, client):
        """Ensure a clean /plan baseline before every replan test."""
        client.post("/plan", json={"lat": 0.0, "lon": 0.0})

    def test_status_200(self, client):
        r = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        })
        assert r.status_code == 200

    def test_response_shape(self, client):
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        _assert_plan_shape(data)

    def test_blockage_active_true(self, client):
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        assert data["blockage_active"] is True

    def test_replanned_route_not_null(self, client):
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        assert data["replanned_route"] is not None

    def test_replanned_route_feasible(self, client):
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        assert data["replanned_route"]["feasible"] is True

    def test_replanned_avoids_blocked_segment(self, client):
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        path = data["replanned_route"]["path"]
        for i in range(len(path) - 1):
            assert (path[i], path[i+1]) not in {("A", "B"), ("B", "A")}, (
                f"Blocked edge appears in replanned path: {path}"
            )

    def test_replanned_longer_than_primary(self, client):
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        assert (
            data["replanned_route"]["total_length_m"]
            > data["primary_route"]["total_length_m"]
        )

    def test_replanned_flag_true(self, client):
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        assert data["replanned_route"]["replanned"] is True

    def test_primary_route_preserved_in_response(self, client):
        baseline = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        assert data["primary_route"]["path"] == baseline["primary_route"]["path"]

    def test_replanned_edges_are_json_arrays(self, client):
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        for edge in data["replanned_route"]["edges"]:
            assert isinstance(edge, list)
            assert len(edge) == 3

    def test_blockage_warning_present(self, client):
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        combined = " ".join(data["warnings"]).lower()
        assert "block" in combined

    def test_is_simulated_still_true(self, client):
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        assert data["is_simulated"] is True

    def test_all_paths_blocked_returns_200_with_infeasible(self, client):
        """All exits from A blocked → replanned_route.feasible=False, still HTTP 200."""
        r = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [
                ["A", "B"], ["B", "A"],
                ["A", "D"], ["D", "A"],
            ],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["blockage_active"] is True
        assert data["replanned_route"]["feasible"] is False

    def test_deterministic_on_repeat(self, client):
        def _replan():
            client.post("/plan", json={"lat": 0.0, "lon": 0.0})
            return client.post("/plan/replan", json={
                "scenario_id": SCENARIO_ID,
                "block_edges": [["A", "B"], ["B", "A"]],
            }).json()

        r1 = _replan()
        r2 = _replan()
        assert r1["replanned_route"]["path"] == r2["replanned_route"]["path"]


# ---------------------------------------------------------------------------
# POST /plan/replan  — invalid input
# ---------------------------------------------------------------------------

class TestReplanInvalidInput:
    @pytest.fixture(autouse=True)
    def reset(self, client):
        client.post("/plan", json={"lat": 0.0, "lon": 0.0})

    def test_empty_block_edges_returns_422(self, client):
        r = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [],
        })
        assert r.status_code == 422

    def test_missing_block_edges_returns_422(self, client):
        r = client.post("/plan/replan", json={"scenario_id": SCENARIO_ID})
        assert r.status_code == 422

    def test_missing_scenario_id_returns_422(self, client):
        r = client.post("/plan/replan", json={
            "block_edges": [["A", "B"]],
        })
        assert r.status_code == 422

    def test_single_element_edge_returns_422(self, client):
        r = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A"]],
        })
        assert r.status_code == 422

    def test_three_element_edge_returns_422(self, client):
        r = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B", "C"]],
        })
        assert r.status_code == 422

    def test_unknown_node_u_returns_422(self, client):
        r = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["BOGUS", "B"]],
        })
        assert r.status_code == 422

    def test_unknown_node_v_returns_422(self, client):
        r = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "BOGUS"]],
        })
        assert r.status_code == 422

    def test_empty_string_node_returns_422(self, client):
        r = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["", "B"]],
        })
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /plan/replan/clear
# ---------------------------------------------------------------------------

class TestClear:
    @pytest.fixture(autouse=True)
    def blockage_active(self, client):
        """Apply a blockage before each clear test."""
        client.post("/plan", json={"lat": 0.0, "lon": 0.0})
        client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        })

    def test_status_200(self, client):
        r = client.post("/plan/replan/clear")
        assert r.status_code == 200

    def test_response_shape(self, client):
        data = client.post("/plan/replan/clear").json()
        _assert_plan_shape(data)

    def test_blockage_active_false(self, client):
        data = client.post("/plan/replan/clear").json()
        assert data["blockage_active"] is False

    def test_replanned_route_null(self, client):
        data = client.post("/plan/replan/clear").json()
        assert data["replanned_route"] is None

    def test_primary_route_restored(self, client):
        # Get the original unblocked path
        original = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        # Apply blockage
        client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        })
        # Clear
        data = client.post("/plan/replan/clear").json()
        assert data["primary_route"]["path"] == original["primary_route"]["path"]

    def test_route_feasible_after_clear(self, client):
        data = client.post("/plan/replan/clear").json()
        assert data["primary_route"]["feasible"] is True

    def test_no_blockage_in_warnings_after_clear(self, client):
        data = client.post("/plan/replan/clear").json()
        combined = " ".join(data["warnings"]).lower()
        assert "blockage active" not in combined

    def test_clear_without_prior_blockage_is_safe(self, client):
        # Extra clear on a clean state
        client.post("/plan/replan/clear")  # consume the autouse blockage
        r = client.post("/plan/replan/clear")
        assert r.status_code == 200

    def test_accepts_empty_body(self, client):
        # mobile clearBlockage() sends empty POST
        r = client.post("/plan/replan/clear", content=b"")
        assert r.status_code == 200

    def test_subsequent_plan_still_works(self, client):
        client.post("/plan/replan/clear")
        r = client.post("/plan", json={"lat": 0.0, "lon": 0.0})
        assert r.status_code == 200
        data = r.json()
        assert data["blockage_active"] is False


# ---------------------------------------------------------------------------
# Mobile contract field-level checks
# ---------------------------------------------------------------------------

class TestMobileContract:
    """
    Verify that each field expected by the TypeScript mobile app is present
    with the exact name and type the mobile code reads.
    """

    def test_plan_all_top_level_fields(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        expected = {
            "scenario_id", "generated_at", "is_simulated", "blockage_active",
            "origin_node", "origin_label", "zone_risks", "primary_route",
            "replanned_route", "shelters", "allocation", "warnings",
            "contract_version",
        }
        assert expected.issubset(data.keys())

    def test_route_result_all_fields(self, client):
        pr = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()["primary_route"]
        expected = {
            "feasible", "path", "edges", "total_length_m", "total_cost",
            "total_risk_penalty_m", "estimated_travel_time_s",
            "mode", "origin", "destination", "replanned", "notes",
        }
        assert expected.issubset(pr.keys())

    def test_risk_record_all_fields(self, client):
        zr = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()["zone_risks"][0]
        expected = {
            "zone_id", "risk_score", "risk_category", "data_freshness",
            "risk_status", "contributing_factors", "contract_version",
        }
        assert expected.issubset(zr.keys())

    def test_shelter_all_fields(self, client):
        s = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()["shelters"][0]
        expected = {
            "shelter_id", "name", "lat", "lon", "capacity", "occupied",
            "remaining_capacity", "status", "nearest_node",
            "data_source", "notes",
        }
        assert expected.issubset(s.keys())

    def test_allocation_all_fields(self, client):
        a = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()["allocation"]
        expected = {
            "assignments", "unassigned", "total_admitted",
            "total_requested", "total_unassigned", "notes",
        }
        assert expected.issubset(a.keys())

    def test_assignment_all_fields(self, client):
        alloc = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()["allocation"]
        if alloc["assignments"]:
            a = alloc["assignments"][0]
            expected = {"demand_id", "shelter_id", "admitted", "requested", "route_cost_m"}
            assert expected.issubset(a.keys())

    def test_health_all_fields(self, client):
        data = client.get("/health").json()
        assert set(data.keys()) == {"status", "version", "backend_url"}

    def test_route_mode_is_valid_string(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["primary_route"]["mode"] in {"shortest", "risk_aware", "adaptive"}

    def test_risk_category_valid_values(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        valid = {"LOW", "MODERATE", "HIGH", "CRITICAL", "UNKNOWN"}
        for z in data["zone_risks"]:
            assert z["risk_category"] in valid

    def test_shelter_status_valid_values(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        valid = {"OPEN", "FULL", "CLOSED"}
        for s in data["shelters"]:
            assert s["status"] in valid

    def test_contract_version_0_1_0(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        assert data["contract_version"] == "0.1.0"

    def test_scoring_method_optional_string(self, client):
        data = client.post("/plan", json={"lat": 0.0, "lon": 0.0}).json()
        for z in data["zone_risks"]:
            assert z["scoring_method"] is None or isinstance(z["scoring_method"], str)

    def test_replan_edges_are_triplets(self, client):
        client.post("/plan", json={"lat": 0.0, "lon": 0.0})
        data = client.post("/plan/replan", json={
            "scenario_id": SCENARIO_ID,
            "block_edges": [["A", "B"], ["B", "A"]],
        }).json()
        for edge in data["replanned_route"]["edges"]:
            assert isinstance(edge, list)
            u, v, key = edge
            assert isinstance(u, str)
            assert isinstance(v, str)
            assert isinstance(key, int)


# ---------------------------------------------------------------------------
# OpenAPI docs endpoint
# ---------------------------------------------------------------------------

class TestDocs:
    def test_openapi_json_available(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        data = r.json()
        assert "openapi" in data
        assert "/health" in data["paths"]
        assert "/plan" in data["paths"]
        assert "/plan/replan" in data["paths"]
        assert "/plan/replan/clear" in data["paths"]

    def test_docs_ui_available(self, client):
        r = client.get("/docs")
        assert r.status_code == 200
