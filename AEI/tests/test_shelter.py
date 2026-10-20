"""
Tests for src/shelter/shelter_manager.py
==========================================
All shelter data is SYNTHETIC.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from shelter.shelter_manager import (
    AllocationResult,
    Assignment,
    Shelter,
    ShelterManager,
    ShelterStatus,
    load_shelters_from_csv,
    load_shelters_from_list,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_shelters(capacities=None):
    if capacities is None:
        capacities = [100, 50, 30]
    return [
        Shelter(
            shelter_id=f"SH_{i}",
            name=f"Shelter {i} (SYNTHETIC)",
            lat=float(i * 0.01),
            lon=float(i * 0.01),
            capacity=cap,
            data_source="SYNTHETIC",
        )
        for i, cap in enumerate(capacities)
    ]


@pytest.fixture
def three_shelters():
    return _make_shelters([100, 50, 30])


@pytest.fixture
def manager(three_shelters):
    return ShelterManager(three_shelters)


# ---------------------------------------------------------------------------
# Shelter properties
# ---------------------------------------------------------------------------

class TestShelterProperties:
    def test_remaining_capacity_initial(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=100)
        assert s.remaining_capacity == 100

    def test_remaining_capacity_after_admit(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=100)
        s.admit(40)
        assert s.remaining_capacity == 60

    def test_remaining_never_negative(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=10)
        s.admit(100)  # over-admit is capped
        assert s.remaining_capacity == 0

    def test_is_available_true_when_open_and_capacity(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=50)
        assert s.is_available

    def test_is_available_false_when_full(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=10)
        s.admit(10)
        assert not s.is_available

    def test_is_available_false_when_closed(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=100)
        s.close()
        assert not s.is_available


# ---------------------------------------------------------------------------
# Shelter state transitions
# ---------------------------------------------------------------------------

class TestShelterStateTransitions:
    def test_admit_returns_actual_count(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=20)
        admitted = s.admit(15)
        assert admitted == 15
        assert s.occupied == 15

    def test_admit_capped_at_remaining(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=20)
        s.admit(15)
        admitted = s.admit(10)  # only 5 remaining
        assert admitted == 5
        assert s.occupied == 20

    def test_admit_sets_full_status(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=10)
        s.admit(10)
        assert s.status == ShelterStatus.FULL

    def test_admit_zero_when_closed(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=100)
        s.close()
        admitted = s.admit(50)
        assert admitted == 0
        assert s.occupied == 0

    def test_close_sets_closed_status(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=100)
        s.close()
        assert s.status == ShelterStatus.CLOSED

    def test_reopen_after_close(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=100)
        s.close()
        s.reopen()
        assert s.status == ShelterStatus.OPEN

    def test_reopen_with_reset_occupancy(self):
        s = Shelter("S1", "Test", 0.0, 0.0, capacity=100)
        s.admit(60)
        s.close()
        s.reopen(reset_occupancy=True)
        assert s.occupied == 0
        assert s.status == ShelterStatus.OPEN

    def test_to_dict_keys(self):
        s = Shelter("S1", "Test", 10.0, 20.0, capacity=50)
        d = s.to_dict()
        for key in ("shelter_id", "name", "lat", "lon", "capacity",
                    "occupied", "remaining_capacity", "status"):
            assert key in d


# ---------------------------------------------------------------------------
# ShelterManager registry
# ---------------------------------------------------------------------------

class TestShelterManagerRegistry:
    def test_initialises_with_correct_count(self, manager):
        assert len(manager.all_shelters()) == 3

    def test_get_returns_shelter(self, manager):
        s = manager.get("SH_0")
        assert s is not None
        assert s.shelter_id == "SH_0"

    def test_get_missing_returns_none(self, manager):
        assert manager.get("NONEXISTENT") is None

    def test_available_shelters_excludes_full(self, manager):
        manager.get("SH_0").status = ShelterStatus.FULL
        avail = manager.available_shelters()
        assert all(s.shelter_id != "SH_0" for s in avail)

    def test_available_shelters_excludes_closed(self, manager):
        manager.close_shelter("SH_1")
        avail = manager.available_shelters()
        assert all(s.shelter_id != "SH_1" for s in avail)

    def test_close_shelter_by_id(self, manager):
        manager.close_shelter("SH_0")
        assert manager.get("SH_0").status == ShelterStatus.CLOSED

    def test_close_missing_shelter_raises(self, manager):
        with pytest.raises(KeyError):
            manager.close_shelter("NO_SUCH_SHELTER")

    def test_reopen_shelter(self, manager):
        manager.close_shelter("SH_0")
        manager.reopen_shelter("SH_0")
        assert manager.get("SH_0").status == ShelterStatus.OPEN

    def test_add_shelter(self, manager):
        new_s = Shelter("SH_NEW", "New", 0.1, 0.1, capacity=25)
        manager.add_shelter(new_s)
        assert manager.get("SH_NEW") is not None

    def test_summary_keys_present(self, manager):
        s = manager.summary()
        for key in ("total_shelters", "open", "full", "closed",
                    "total_capacity", "total_occupied", "total_remaining"):
            assert key in s

    def test_summary_total_capacity(self, manager):
        s = manager.summary()
        assert s["total_capacity"] == 100 + 50 + 30

    def test_summary_all_open(self, manager):
        s = manager.summary()
        assert s["open"] == 3
        assert s["closed"] == 0


# ---------------------------------------------------------------------------
# ShelterManager.snap_to_network
# ---------------------------------------------------------------------------

class TestSnapToNetwork:
    def test_snap_sets_nearest_node(self, three_shelters):
        from gis.network_loader import from_synthetic
        nodes = [
            {"id": "N0", "x": 0.000, "y": 0.000},
            {"id": "N1", "x": 0.010, "y": 0.010},
            {"id": "N2", "x": 0.020, "y": 0.020},
        ]
        edges = [
            {"u": "N0", "v": "N1", "length_m": 1000, "one_way": False},
            {"u": "N1", "v": "N2", "length_m": 1000, "one_way": False},
        ]
        G = from_synthetic(nodes, edges)
        mgr = ShelterManager(three_shelters)
        mgr.snap_to_network(G)
        for s in mgr.all_shelters():
            assert s.nearest_node is not None


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------

class TestAllocation:
    def test_basic_allocation_succeeds(self, manager):
        # Manually set nearest_nodes (no graph needed for haversine allocation)
        for s in manager.all_shelters():
            s.nearest_node = s.shelter_id  # dummy

        demand = [{"demand_id": "ZONE_1", "origin_node": "SH_0", "count": 30}]
        result = manager.allocate(demand, router=None)

        assert result.total_admitted == 30
        assert len(result.assignments) == 1

    def test_allocation_respects_capacity(self, manager):
        for s in manager.all_shelters():
            s.nearest_node = s.shelter_id

        # Request more than total capacity
        total_cap = sum(s.capacity for s in manager.all_shelters())
        demand = [{"demand_id": "BIG", "origin_node": "SH_0",
                   "count": total_cap + 50}]
        result = manager.allocate(demand, router=None)

        assert result.total_admitted <= total_cap

    def test_unassigned_reported_when_no_capacity(self, manager):
        # Close all shelters
        for s in manager.all_shelters():
            s.close()
        demand = [{"demand_id": "Z", "origin_node": "X", "count": 10}]
        result = manager.allocate(demand, router=None)
        assert result.total_unassigned == 10
        assert len(result.unassigned) > 0

    def test_unassigned_entries_have_reason(self, manager):
        for s in manager.all_shelters():
            s.close()
        demand = [{"demand_id": "Z", "origin_node": "X", "count": 5}]
        result = manager.allocate(demand, router=None)
        for u in result.unassigned:
            assert "reason" in u
            assert len(u["reason"]) > 0

    def test_full_shelter_not_reassigned(self, manager):
        """A FULL shelter must not receive further admits."""
        for s in manager.all_shelters():
            s.nearest_node = s.shelter_id

        # Fill SH_0 to capacity
        manager.get("SH_0").admit(100)  # capacity = 100
        demand = [{"demand_id": "X", "origin_node": "SH_0", "count": 10}]
        result = manager.allocate(demand, router=None)

        # SH_0 must not appear in assignments
        for a in result.assignments:
            assert a.shelter_id != "SH_0", "Full shelter must not be assigned"

    def test_closed_shelter_excluded_from_assignments(self, manager):
        for s in manager.all_shelters():
            s.nearest_node = s.shelter_id
        manager.close_shelter("SH_0")

        demand = [{"demand_id": "Z", "origin_node": "SH_0", "count": 10}]
        result = manager.allocate(demand, router=None)

        for a in result.assignments:
            assert a.shelter_id != "SH_0", "Closed shelter must not be assigned"

    def test_allocation_result_totals_consistent(self, manager):
        for s in manager.all_shelters():
            s.nearest_node = s.shelter_id
        demand = [
            {"demand_id": "A", "origin_node": "SH_0", "count": 20},
            {"demand_id": "B", "origin_node": "SH_0", "count": 30},
        ]
        result = manager.allocate(demand, router=None)
        assert result.total_requested == 50
        assert result.total_admitted + result.total_unassigned == 50

    def test_notes_present_in_result(self, manager):
        for s in manager.all_shelters():
            s.nearest_node = s.shelter_id
        demand = [{"demand_id": "Z", "origin_node": "SH_0", "count": 1}]
        result = manager.allocate(demand, router=None)
        assert len(result.notes) > 0

    def test_allocation_with_router(self):
        """Allocation uses routing cost to rank shelters."""
        from gis.network_loader import from_synthetic
        from routing.router import EvacuationRouter, RoutingConfig, RoutingMode

        nodes = [
            {"id": "O", "x": 0.00, "y": 0.00},   # origin
            {"id": "S1", "x": 0.01, "y": 0.00},   # near shelter
            {"id": "S2", "x": 0.02, "y": 0.00},   # far shelter
        ]
        edges = [
            {"u": "O", "v": "S1", "length_m": 500,  "one_way": False},
            {"u": "S1", "v": "S2", "length_m": 1000, "one_way": False},
        ]
        G = from_synthetic(nodes, edges)

        shelters = [
            Shelter("SH_NEAR", "Near (SYNTHETIC)", 0.00, 0.01, 100, data_source="SYNTHETIC"),
            Shelter("SH_FAR",  "Far (SYNTHETIC)",  0.00, 0.02, 100, data_source="SYNTHETIC"),
        ]
        shelters[0].nearest_node = "S1"
        shelters[1].nearest_node = "S2"

        mgr = ShelterManager(shelters)
        cfg = RoutingConfig(mode=RoutingMode.SHORTEST)
        router = EvacuationRouter(G, cfg)

        demand = [{"demand_id": "Z", "origin_node": "O", "count": 10}]
        result = mgr.allocate(demand, router=router)

        assert result.total_admitted == 10
        # Should prefer the nearer shelter
        assert result.assignments[0].shelter_id == "SH_NEAR"


# ---------------------------------------------------------------------------
# load_shelters_from_list / from_csv
# ---------------------------------------------------------------------------

class TestLoadHelpers:
    def test_load_from_list(self):
        data = [
            {"shelter_id": "X", "name": "X", "lat": 1.0, "lon": 2.0,
             "capacity": 50, "data_source": "SYNTHETIC"},
        ]
        shelters = load_shelters_from_list(data)
        assert len(shelters) == 1
        assert shelters[0].capacity == 50
        assert shelters[0].data_source == "SYNTHETIC"

    def test_load_from_list_invalid_status_defaults_open(self):
        data = [
            {"shelter_id": "X", "name": "X", "lat": 0.0, "lon": 0.0,
             "capacity": 10, "status": "BADVALUE"},
        ]
        shelters = load_shelters_from_list(data)
        assert shelters[0].status == ShelterStatus.OPEN

    def test_load_from_csv(self, tmp_path):
        import csv
        p = tmp_path / "shelters.csv"
        with open(p, "w", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["shelter_id", "name", "lat", "lon",
                                "capacity", "data_source"]
            )
            writer.writeheader()
            writer.writerow({"shelter_id": "SH_CSV", "name": "CSV Shelter",
                             "lat": "10.0", "lon": "20.0", "capacity": "75",
                             "data_source": "SYNTHETIC"})
        shelters = load_shelters_from_csv(p)
        assert len(shelters) == 1
        assert shelters[0].shelter_id == "SH_CSV"
        assert shelters[0].capacity == 75

    def test_load_from_csv_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_shelters_from_csv(tmp_path / "missing.csv")
