"""
AEI — Shelter: Capacity-Aware Shelter Manager
===============================================
Maintains a registry of shelters, tracks remaining capacity, and assigns
evacuation demand to shelters in a documented, reproducible way.

Design rules
------------
* All shelter locations are configurable at runtime.  No coordinates are
  hardcoded.  Shelters may be loaded from a dict list or a CSV file.
* A shelter can be in one of three states: OPEN, FULL, CLOSED.
  Full and closed shelters MUST NOT receive further assignments.
* Capacity is tracked as integer headcount (people).  Fractional demand is
  rounded up (ceiling) to be conservative.
* Assignment algorithm: greedy nearest-feasible.  For each demand unit the
  algorithm finds the nearest open shelter (by nearest-node routing cost)
  with remaining capacity, assigns demand to it, and deducts from capacity.
  This is NOT guaranteed optimal (bin-packing with travel cost is NP-hard)
  but it is fast, deterministic, and documented.
* When a shelter becomes full or is closed, unassigned demand is NOT
  silently discarded.  It is returned in ``AllocationResult.unassigned``
  so callers know how many people lack shelter.
* Shelter data provenance must be set honestly (real vs synthetic).

Disclaimer
----------
The mapped shelters in synthetic examples are SYNTHETIC.  Do not claim
that any location is a verified operational evacuation shelter.
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ShelterStatus(str, Enum):
    """Operational status of a shelter."""
    OPEN   = "OPEN"    # accepting evacuees
    FULL   = "FULL"    # at maximum capacity
    CLOSED = "CLOSED"  # not available (structural damage, inaccessible, etc.)


# ---------------------------------------------------------------------------
# Shelter data record
# ---------------------------------------------------------------------------

@dataclass
class Shelter:
    """
    One candidate evacuation shelter.

    Attributes
    ----------
    shelter_id : str
        Stable unique identifier.  Must match GIS layer IDs when used
        in a real deployment.
    name : str
        Human-readable name (e.g. school name).
    lat : float
        Latitude of the shelter (WGS 84).
    lon : float
        Longitude of the shelter (WGS 84).
    capacity : int
        Maximum number of people this shelter can accommodate.
    occupied : int
        Current occupancy.  Defaults to 0 at load time.
    status : ShelterStatus
        Operational status.  Changes to FULL when remaining == 0.
    nearest_node : any
        The road-network node nearest to this shelter.  Set by
        ``ShelterManager.snap_to_network()``.
    data_source : str
        'SYNTHETIC' | 'REAL' | 'ESTIMATED'.  Must be set honestly.
    notes : str
        Free-text notes (e.g. accessibility constraints, data caveats).
    """
    shelter_id: str
    name: str
    lat: float
    lon: float
    capacity: int
    occupied: int = 0
    status: ShelterStatus = ShelterStatus.OPEN
    nearest_node: Any = None
    data_source: str = "SYNTHETIC"
    notes: str = ""

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def remaining_capacity(self) -> int:
        """Remaining headcount capacity (never negative)."""
        return max(0, self.capacity - self.occupied)

    @property
    def is_available(self) -> bool:
        """True if this shelter can currently accept evacuees."""
        return self.status == ShelterStatus.OPEN and self.remaining_capacity > 0

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def admit(self, count: int) -> int:
        """
        Admit ``count`` people into this shelter.

        Returns the actual number admitted (may be < count if capacity
        is limited).  Updates ``occupied`` and ``status``.
        """
        if not self.is_available:
            return 0
        actual = min(count, self.remaining_capacity)
        self.occupied += actual
        if self.remaining_capacity == 0:
            self.status = ShelterStatus.FULL
            logger.info("Shelter '%s' is now FULL.", self.shelter_id)
        return actual

    def close(self) -> None:
        """Mark shelter as CLOSED (e.g. structural damage or inaccessible)."""
        self.status = ShelterStatus.CLOSED
        logger.info("Shelter '%s' CLOSED.", self.shelter_id)

    def reopen(self, reset_occupancy: bool = False) -> None:
        """
        Reopen a closed or full shelter.

        Parameters
        ----------
        reset_occupancy : bool
            If True, also reset occupied count to 0.
        """
        if reset_occupancy:
            self.occupied = 0
        self.status = ShelterStatus.OPEN if self.remaining_capacity > 0 else ShelterStatus.FULL
        logger.info("Shelter '%s' reopened (status=%s).", self.shelter_id, self.status.value)

    def to_dict(self) -> dict:
        return {
            "shelter_id": self.shelter_id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "capacity": self.capacity,
            "occupied": self.occupied,
            "remaining_capacity": self.remaining_capacity,
            "status": self.status.value,
            "nearest_node": self.nearest_node,
            "data_source": self.data_source,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Allocation result
# ---------------------------------------------------------------------------

@dataclass
class Assignment:
    """
    One demand-unit → shelter assignment.

    Attributes
    ----------
    demand_id : str  — identifier for the demand unit (e.g. zone_id)
    shelter_id : str
    admitted : int   — people successfully assigned
    requested : int  — people originally requested
    route_cost_m : float  — routing cost from demand origin to shelter
    notes : list of str
    """
    demand_id: str
    shelter_id: str
    admitted: int
    requested: int
    route_cost_m: float = 0.0
    notes: List[str] = field(default_factory=list)


@dataclass
class AllocationResult:
    """
    Summary of one complete shelter-allocation run.

    Attributes
    ----------
    assignments : list of Assignment
        All successful assignments.
    unassigned : list of dict
        Demand units that could not be assigned
        (no capacity, no route, shelter closed).
        Each dict has keys: demand_id, requested, reason.
    total_admitted : int
    total_requested : int
    total_unassigned : int
    notes : list of str
    """
    assignments: List[Assignment] = field(default_factory=list)
    unassigned: List[Dict] = field(default_factory=list)
    total_admitted: int = 0
    total_requested: int = 0
    total_unassigned: int = 0
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shelter manager
# ---------------------------------------------------------------------------

class ShelterManager:
    """
    Registry for candidate evacuation shelters.

    Parameters
    ----------
    shelters : list of Shelter
        Initial shelter list.

    Usage
    -----
    >>> mgr = ShelterManager(shelters)
    >>> mgr.snap_to_network(G)   # find nearest road node for each shelter
    >>> result = mgr.allocate(demand_list, router)
    """

    def __init__(self, shelters: List[Shelter]) -> None:
        self._shelters: Dict[str, Shelter] = {s.shelter_id: s for s in shelters}
        logger.info("ShelterManager initialised with %d shelters.", len(shelters))

    # ------------------------------------------------------------------
    # Registry access
    # ------------------------------------------------------------------

    def get(self, shelter_id: str) -> Optional[Shelter]:
        """Return shelter by id, or None if not found."""
        return self._shelters.get(shelter_id)

    def all_shelters(self) -> List[Shelter]:
        return list(self._shelters.values())

    def available_shelters(self) -> List[Shelter]:
        """Return shelters that are currently OPEN with remaining capacity."""
        return [s for s in self._shelters.values() if s.is_available]

    def add_shelter(self, shelter: Shelter) -> None:
        self._shelters[shelter.shelter_id] = shelter

    def close_shelter(self, shelter_id: str) -> None:
        """Close a shelter by id."""
        s = self._shelters.get(shelter_id)
        if s is None:
            raise KeyError(f"Shelter '{shelter_id}' not found.")
        s.close()

    def reopen_shelter(
        self, shelter_id: str, reset_occupancy: bool = False
    ) -> None:
        s = self._shelters.get(shelter_id)
        if s is None:
            raise KeyError(f"Shelter '{shelter_id}' not found.")
        s.reopen(reset_occupancy=reset_occupancy)

    # ------------------------------------------------------------------
    # Snap shelters to road network
    # ------------------------------------------------------------------

    def snap_to_network(self, G: nx.MultiDiGraph) -> None:
        """
        Find the nearest road-network node for each shelter.

        After this call, ``shelter.nearest_node`` is set.  This must be
        called before ``allocate()`` if routing costs are to be computed.

        Parameters
        ----------
        G : road-network graph (nodes must have 'x' longitude, 'y' latitude)
        """
        from gis.network_loader import nearest_node as _nearest_node
        for s in self._shelters.values():
            s.nearest_node = _nearest_node(G, s.lat, s.lon)
        logger.info(
            "Snapped %d shelters to network nodes.", len(self._shelters)
        )

    # ------------------------------------------------------------------
    # Allocation
    # ------------------------------------------------------------------

    def allocate(
        self,
        demand: List[Dict],
        router=None,   # EvacuationRouter | None
    ) -> AllocationResult:
        """
        Assign demand to shelters using the greedy nearest-feasible algorithm.

        Algorithm
        ---------
        For each demand unit (in input order):
          1. Check if any shelter is available.
          2. For each available shelter (sorted by routing cost from the
             demand origin if a router is provided, else by haversine
             distance from demand lat/lon to shelter lat/lon):
             a. Compute route from demand origin to shelter's nearest_node.
             b. If route is feasible and shelter has capacity, assign and
                break.
          3. If no shelter can be reached or all are full, record as
             unassigned with an explanatory reason.

        The algorithm does NOT guarantee a global optimum (optimal bin-
        packing with travel cost is NP-hard).  It is documented as greedy.

        Parameters
        ----------
        demand : list of dict
            Each dict must have:
                demand_id  : str   — identifier (e.g. zone_id)
                origin_node: any   — road-network node id for this demand
                count      : int   — number of people to place
            Optional keys:
                lat, lon           — fallback for haversine ranking when
                                     no router is supplied

        router : EvacuationRouter, optional
            If supplied, routing cost is used to rank shelters.
            If None, haversine distance is used (requires demand lat/lon).

        Returns
        -------
        AllocationResult
        """
        result = AllocationResult()
        result.total_requested = sum(d.get("count", 1) for d in demand)

        for demand_unit in demand:
            did   = demand_unit["demand_id"]
            count = demand_unit.get("count", 1)
            o_node = demand_unit.get("origin_node")

            # Rank available shelters by cost
            available = self.available_shelters()
            if not available:
                result.unassigned.append({
                    "demand_id": did,
                    "requested": count,
                    "reason": "No shelters available (all full or closed).",
                })
                result.total_unassigned += count
                continue

            ranked = self._rank_shelters(available, demand_unit, router)

            assigned = False
            remaining_count = count
            original_did = did

            for shelter, cost_m in ranked:
                if remaining_count <= 0:
                    break
                # Skip unreachable shelters only when a router was used to
                # compute the cost.  cost_m=inf means the router found no
                # feasible path; do not admit to an unreachable shelter.
                # When router=None the cost is haversine distance (never inf
                # for valid coordinates) or inf only when lat/lon is absent —
                # in that case we still allow admission (no routing constraint).
                if router is not None and cost_m == float("inf"):
                    continue
                admitted = shelter.admit(remaining_count)
                if admitted > 0:
                    result.assignments.append(Assignment(
                        demand_id=original_did,
                        shelter_id=shelter.shelter_id,
                        admitted=admitted,
                        requested=remaining_count,
                        route_cost_m=cost_m,
                    ))
                    result.total_admitted += admitted
                    remaining_count -= admitted
                    assigned = True
                    # Continue loop to fill leftover at next shelter

            if remaining_count > 0:
                # Some or all demand could not be assigned
                reason = (
                    "No shelters available (all full or closed)."
                    if not assigned
                    else (
                        f"Partial assignment across shelters: "
                        f"{count - remaining_count} of {count} admitted. "
                        f"{remaining_count} remain after exhausting all capacity."
                    )
                )
                result.unassigned.append({
                    "demand_id": original_did,
                    "requested": remaining_count,
                    "reason": reason,
                })
                result.total_unassigned += remaining_count

        result.notes.append(
            "Algorithm: greedy nearest-feasible. NOT guaranteed optimal."
        )
        if result.total_unassigned > 0:
            result.notes.append(
                f"{result.total_unassigned} person(s) could not be assigned. "
                "Increase shelter capacity or add new shelters."
            )

        logger.info(
            "Allocation complete: %d/%d assigned, %d unassigned.",
            result.total_admitted, result.total_requested, result.total_unassigned,
        )
        return result

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        total_cap   = sum(s.capacity  for s in self._shelters.values())
        total_occ   = sum(s.occupied  for s in self._shelters.values())
        open_count  = sum(1 for s in self._shelters.values()
                         if s.status == ShelterStatus.OPEN)
        full_count  = sum(1 for s in self._shelters.values()
                         if s.status == ShelterStatus.FULL)
        closed_count = sum(1 for s in self._shelters.values()
                           if s.status == ShelterStatus.CLOSED)
        return {
            "total_shelters": len(self._shelters),
            "open": open_count,
            "full": full_count,
            "closed": closed_count,
            "total_capacity": total_cap,
            "total_occupied": total_occ,
            "total_remaining": total_cap - total_occ,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _rank_shelters(
        self,
        shelters: List[Shelter],
        demand_unit: dict,
        router,
    ) -> List[tuple]:
        """
        Return shelters sorted by cost from demand origin (ascending).

        Returns list of (Shelter, cost_m) tuples.
        """
        ranked = []
        o_node = demand_unit.get("origin_node")

        for s in shelters:
            cost_m = float("inf")

            if router is not None and o_node is not None and s.nearest_node is not None:
                from routing.router import RoutingMode
                res = router.route(o_node, s.nearest_node,
                                   mode=RoutingMode.RISK_AWARE)
                if res.feasible:
                    cost_m = res.total_cost
            elif "lat" in demand_unit and "lon" in demand_unit:
                # Haversine fallback
                cost_m = _haversine_m(
                    demand_unit["lat"], demand_unit["lon"], s.lat, s.lon
                )

            ranked.append((s, cost_m))

        ranked.sort(key=lambda x: x[1])
        return ranked


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def load_shelters_from_list(shelter_dicts: List[Dict]) -> List[Shelter]:
    """
    Build a list of Shelter objects from a list of dicts.

    Required keys per dict: shelter_id, name, lat, lon, capacity.
    Optional: occupied, status, data_source, notes.
    """
    shelters = []
    for d in shelter_dicts:
        status_val = d.get("status", "OPEN")
        try:
            status = ShelterStatus(status_val)
        except ValueError:
            logger.warning(
                "Unknown shelter status '%s' for '%s' — defaulting to OPEN.",
                status_val, d.get("shelter_id", "?")
            )
            status = ShelterStatus.OPEN

        shelters.append(Shelter(
            shelter_id  = str(d["shelter_id"]),
            name        = str(d.get("name", d["shelter_id"])),
            lat         = float(d["lat"]),
            lon         = float(d["lon"]),
            capacity    = int(d["capacity"]),
            occupied    = int(d.get("occupied", 0)),
            status      = status,
            data_source = str(d.get("data_source", "SYNTHETIC")),
            notes       = str(d.get("notes", "")),
        ))
    return shelters


def load_shelters_from_csv(path: str | Path) -> List[Shelter]:
    """
    Load shelters from a CSV file.

    The CSV must have header columns matching the keys expected by
    ``load_shelters_from_list``.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    list of Shelter
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Shelter CSV not found: {path}")

    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    return load_shelters_from_list(rows)


# ---------------------------------------------------------------------------
# Geometry helper
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return 2.0 * R * math.asin(math.sqrt(a))
