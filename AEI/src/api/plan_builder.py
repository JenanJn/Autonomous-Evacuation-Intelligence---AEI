"""
AEI — API: Evacuation Plan Builder
=====================================
Assembles the ``EvacuationPlanResponse`` from the existing routing,
shelter, risk-mapping, and GIS modules.

This module owns **all** domain logic needed to answer a /plan request.
The FastAPI endpoints in ``main.py`` only validate HTTP input and call
into this module; they contain no domain logic themselves.

Synthetic-demo design
----------------------
There is no live OSM feed in the current deployment.  The builder
initialises a deterministic in-memory graph (``_make_demo_graph``) at
import time and reuses it across every request.  Every response carries
``is_simulated=True`` and warnings that make the synthetic origin clear.

Cross-request state safety
---------------------------
``DemoState`` holds a **fresh** ``EvacuationRouter`` per *session* so
that blockages introduced by one /plan/replan call persist until the
session is cleared via /plan/replan/clear.  A ``DemoState`` object is
created once at server startup and stored in the FastAPI app state.

Calling ``DemoState.reset()`` restores the unmodified working graph —
the original graph is never mutated.

Limitations (documented)
--------------------------
* Single demo session — all HTTP clients share the same ``DemoState``.
  Concurrent /plan/replan calls from different mobile clients will
  interfere.  This is acceptable for a single-user demo; production
  would need per-session state keyed by session token.
* GPS → nearest-node uses a linear haversine scan (O(n) over graph
  nodes).  Fast enough for the 6-node demo; not for city-scale graphs.
* Risk scores use deterministic fixed values, not live model inference.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from gis.network_loader import from_synthetic, nearest_node
from integration.schemas import (
    CONTRACT_VERSION,
    HazardPredictionRecord,
    PredictionStatus,
    RiskCategory,
    RiskOutputRecord,
    RiskStatus,
)
from risk_engine.risk_mapper import (
    apply_zone_node_mapping,
    build_synthetic_risk_records,
)
from routing.router import (
    EvacuationRouter,
    RouteResult,
    RoutingConfig,
    RoutingMode,
    UnknownRiskPolicy,
)
from shelter.shelter_manager import (
    AllocationResult,
    Assignment,
    Shelter,
    ShelterManager,
    load_shelters_from_list,
)
from api.models import (
    AllocationResultResponse,
    CONTRACT_VERSION as API_CONTRACT_VERSION,
    EvacuationPlanResponse,
    RiskOutputRecordResponse,
    RouteResultResponse,
    ShelterAssignmentResponse,
    ShelterResponse,
    UnassignedDemandResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synthetic demo graph definition
# ---------------------------------------------------------------------------
# Topology (all bidirectional):
#
#   A ── B ── C
#   │    │    │
#   D ── E ── F
#
# Nodes: A-F  (WGS-84 coordinates near (0, 0) — not a real place)
# Shelters: SH_C at node C (cap 200), SH_F at node F (cap 150)
# Zone→node mapping: ZONE_X ↔ node X for X in {A,B,C,D,E,F}
# ---------------------------------------------------------------------------

_DEMO_NODES: List[Dict] = [
    {"id": "A", "x":  0.000, "y":  0.000},
    {"id": "B", "x":  0.009, "y":  0.000},
    {"id": "C", "x":  0.018, "y":  0.000},
    {"id": "D", "x":  0.000, "y": -0.005},
    {"id": "E", "x":  0.009, "y": -0.005},
    {"id": "F", "x":  0.018, "y": -0.005},
]

_DEMO_EDGES: List[Dict] = [
    {"u": "A", "v": "B", "length_m": 1200, "road_type": "primary",   "one_way": False},
    {"u": "B", "v": "C", "length_m": 1200, "road_type": "primary",   "one_way": False},
    {"u": "A", "v": "D", "length_m":  600, "road_type": "secondary", "one_way": False},
    {"u": "B", "v": "E", "length_m":  600, "road_type": "secondary", "one_way": False},
    {"u": "C", "v": "F", "length_m":  600, "road_type": "secondary", "one_way": False},
    {"u": "D", "v": "E", "length_m": 1200, "road_type": "tertiary",  "one_way": False},
    {"u": "E", "v": "F", "length_m": 1200, "road_type": "tertiary",  "one_way": False},
]

# Fixed risk scores (deterministic proxy values — NOT calibrated)
_DEMO_ZONE_RISK_MAP: Dict[str, float] = {
    "ZONE_A": 0.45,
    "ZONE_B": 0.44,
    "ZONE_C": 0.46,
    "ZONE_D": 0.46,
    "ZONE_E": 0.44,
    "ZONE_F": 0.43,
}

# Zone → node mapping (one zone per node)
_DEMO_ZONE_NODE_MAP: Dict[str, List[str]] = {
    "ZONE_A": ["A"],
    "ZONE_B": ["B"],
    "ZONE_C": ["C"],
    "ZONE_D": ["D"],
    "ZONE_E": ["E"],
    "ZONE_F": ["F"],
}

_DEMO_SHELTER_DICTS: List[Dict] = [
    {
        "shelter_id":  "SH_C",
        "name":        "Evacuation Point C [SYNTHETIC]",
        "lat":          0.000,
        "lon":          0.018,
        "capacity":    200,
        "data_source": "SYNTHETIC",
        "notes":       "Synthetic shelter — not a real evacuation facility.",
    },
    {
        "shelter_id":  "SH_F",
        "name":        "Evacuation Point F [SYNTHETIC]",
        "lat":         -0.005,
        "lon":          0.018,
        "capacity":    150,
        "data_source": "SYNTHETIC",
        "notes":       "Synthetic shelter — not a real evacuation facility.",
    },
]

# The destination node is the shelter node nearest to all origins.
# With this graph, C is the primary destination (nearest open shelter
# accessible from A via the shortest/risk-aware path A→B→C).
_DEMO_DESTINATION: str = "C"

_DEMO_ROUTING_CFG = RoutingConfig(
    mode=RoutingMode.RISK_AWARE,
    risk_weight=1.0,
    risk_m_equivalent=5000.0,
    unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE,
)

# Demand used for shelter allocation (one representative demand per zone)
_DEMO_DEMAND: List[Dict] = [
    {"demand_id": "ZONE_A", "origin_node": "A", "count": 80,
     "lat":  0.000, "lon":  0.000},
    {"demand_id": "ZONE_B", "origin_node": "B", "count": 60,
     "lat":  0.000, "lon":  0.009},
    {"demand_id": "ZONE_D", "origin_node": "D", "count": 100,
     "lat": -0.005, "lon":  0.000},
]

SCENARIO_ID = "DEMO_SYNTHETIC_001"

# ---------------------------------------------------------------------------
# Graph / risk-record factory
# ---------------------------------------------------------------------------

def _make_demo_graph() -> nx.MultiDiGraph:
    """
    Build the synthetic demo graph with risk scores pre-applied.

    Returns a fresh deep-copy each time so callers can mutate it freely.
    """
    G = from_synthetic(_DEMO_NODES, _DEMO_EDGES)
    risk_records = build_synthetic_risk_records(_DEMO_ZONE_RISK_MAP)
    apply_zone_node_mapping(G, risk_records, _DEMO_ZONE_NODE_MAP)
    return G


def _make_demo_risk_records() -> List[RiskOutputRecord]:
    """Return the fixed synthetic RiskOutputRecord list."""
    return build_synthetic_risk_records(_DEMO_ZONE_RISK_MAP)


# ---------------------------------------------------------------------------
# Per-session demo state
# ---------------------------------------------------------------------------

class DemoState:
    """
    Holds all mutable server-side state for the single demo session.

    Attributes
    ----------
    graph       : the current working copy of the road graph
    router      : EvacuationRouter wrapping ``graph``
    shelter_mgr : ShelterManager with shelters snapped to ``graph``
    primary_route : the unblocked primary route from origin → SH_C
                    (cached at startup / after clear)
    origin_node : default origin node for the demo (node "A")

    Thread safety
    -------------
    No locking.  Single-user demo only.  Document this limitation.
    """

    def __init__(self) -> None:
        self._base_graph: nx.MultiDiGraph = _make_demo_graph()
        self.reset()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Restore the unblocked state (called at startup and by /clear)."""
        # Always start from a deep copy of the pristine base graph.
        self.graph: nx.MultiDiGraph = deepcopy(self._base_graph)
        self.router: EvacuationRouter = EvacuationRouter(
            self.graph, _DEMO_ROUTING_CFG
        )
        shelters = load_shelters_from_list(_DEMO_SHELTER_DICTS)
        self.shelter_mgr: ShelterManager = ShelterManager(shelters)
        self.shelter_mgr.snap_to_network(self.graph)
        self.origin_node: str = "A"
        # Cache the clean primary route
        self.primary_route: RouteResult = self.router.route(
            self.origin_node, _DEMO_DESTINATION
        )
        logger.info("DemoState reset. Primary route: %s", self.primary_route.path)

    def apply_blockages(self, block_edges: List[List[str]]) -> None:
        """Block each (u, v) pair in the working router."""
        for u, v in block_edges:
            self.router.block_edge(u, v)
            logger.info("Blocked edge %s → %s", u, v)

    @property
    def risk_records(self) -> List[RiskOutputRecord]:
        return _make_demo_risk_records()

    @property
    def shelters(self) -> List[Shelter]:
        return self.shelter_mgr.all_shelters()

    def fresh_allocation(self, router: Optional[EvacuationRouter] = None) -> AllocationResult:
        """
        Run a fresh allocation with the current shelter state.

        The shelter manager is re-initialised from scratch so that
        occupancy from a previous request does not contaminate this one.
        """
        shelters = load_shelters_from_list(_DEMO_SHELTER_DICTS)
        mgr = ShelterManager(shelters)
        mgr.snap_to_network(self.graph)
        return mgr.allocate(_DEMO_DEMAND, router=router or self.router)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _serialise_route(route: RouteResult) -> RouteResultResponse:
    """
    Convert a ``RouteResult`` dataclass to the API response model.

    ``edges`` contains Python tuples (u, v, key); the mobile contract
    expects JSON arrays [u, v, key].  Convert explicitly.
    ``mode`` is a ``RoutingMode`` enum; use ``.value`` for the string.
    ``origin`` / ``destination`` may be any type (graph node id) — cast
    to ``str`` so Pydantic validation succeeds even for int node ids.
    ``unknown_risk_policy`` is an internal field not in the mobile
    contract; it is intentionally omitted.
    """
    return RouteResultResponse(
        feasible=route.feasible,
        path=[str(n) for n in route.path],
        edges=[[str(u), str(v), int(k)] for u, v, k in route.edges],
        total_length_m=route.total_length_m,
        total_cost=route.total_cost,
        total_risk_penalty_m=route.total_risk_penalty_m,
        estimated_travel_time_s=route.estimated_travel_time_s,
        mode=route.mode.value if hasattr(route.mode, "value") else str(route.mode),
        origin=str(route.origin),
        destination=str(route.destination),
        replanned=route.replanned,
        notes=list(route.notes),
    )


def _serialise_risk_records(
    risk_records: List[RiskOutputRecord],
    scoring_method: Optional[str] = None,
) -> List[RiskOutputRecordResponse]:
    """
    Convert ``RiskOutputRecord`` Pydantic models to API response models.

    ``scoring_method`` is forwarded from ``ScoredRiskRecord.scoring_method``
    when available; the mobile type marks it optional.
    ``risk_category`` and ``risk_status`` are Pydantic Enum objects —
    ``.value`` gives the plain string the mobile app expects.
    """
    out = []
    for r in risk_records:
        out.append(RiskOutputRecordResponse(
            zone_id=r.zone_id,
            risk_score=r.risk_score,
            risk_category=r.risk_category.value if hasattr(r.risk_category, "value") else str(r.risk_category),
            data_freshness=r.data_freshness,
            risk_status=r.risk_status.value if hasattr(r.risk_status, "value") else str(r.risk_status),
            contributing_factors=list(r.contributing_factors),
            contract_version=r.contract_version,
            scoring_method=scoring_method,
        ))
    return out


def _serialise_shelters(shelters: List[Shelter]) -> List[ShelterResponse]:
    return [
        ShelterResponse(
            shelter_id=s.shelter_id,
            name=s.name,
            lat=s.lat,
            lon=s.lon,
            capacity=s.capacity,
            occupied=s.occupied,
            remaining_capacity=s.remaining_capacity,
            status=s.status.value if hasattr(s.status, "value") else str(s.status),
            nearest_node=str(s.nearest_node) if s.nearest_node is not None else None,
            data_source=s.data_source,
            notes=s.notes,
        )
        for s in shelters
    ]


def _serialise_allocation(alloc: AllocationResult) -> AllocationResultResponse:
    assignments = [
        ShelterAssignmentResponse(
            demand_id=a.demand_id,
            shelter_id=a.shelter_id,
            admitted=a.admitted,
            requested=a.requested,
            route_cost_m=a.route_cost_m,
        )
        for a in alloc.assignments
    ]
    unassigned = [
        UnassignedDemandResponse(
            demand_id=u["demand_id"],
            requested=u["requested"],
            reason=u["reason"],
        )
        for u in alloc.unassigned
    ]
    return AllocationResultResponse(
        assignments=assignments,
        unassigned=unassigned,
        total_admitted=alloc.total_admitted,
        total_requested=alloc.total_requested,
        total_unassigned=alloc.total_unassigned,
        notes=list(alloc.notes),
    )


# ---------------------------------------------------------------------------
# Origin-label helper
# ---------------------------------------------------------------------------

def _origin_label(node_id: str, lat: Optional[float], lon: Optional[float]) -> str:
    """
    Return a human-readable label for the origin.

    For the synthetic demo all coordinates are near (0, 0); the label
    makes the synthetic nature explicit.
    """
    if lat is not None and lon is not None:
        return f"GPS ({lat:.5f}, {lon:.5f}) → node {node_id} [SYNTHETIC]"
    return f"Node {node_id} [SYNTHETIC]"


# ---------------------------------------------------------------------------
# UTC timestamp helper
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

_BASE_WARNINGS = [
    "SIMULATED DATA — synthetic graph only. Not a real road network or emergency scenario.",
    "Risk scores are UNCALIBRATED decision-support proxies. NOT calibrated flood probabilities.",
    "Travel times use a fixed speed table and do not account for traffic or emergency conditions.",
    "Shelter locations are synthetic — not verified evacuation facilities.",
]


def build_plan(
    state: DemoState,
    lat: float,
    lon: float,
    node_id: Optional[str],
) -> EvacuationPlanResponse:
    """
    Build a fresh unblocked evacuation plan.

    Steps
    -----
    1. Resolve origin node (use supplied ``node_id`` if given and present
       in the graph, otherwise snap GPS → nearest node).
    2. Compute risk-aware route from origin to the primary shelter node.
    3. Run shelter allocation against the current (unblocked) router.
    4. Assemble and return ``EvacuationPlanResponse``.

    The ``state`` is reset to a clean graph before planning so that stale
    blockage state from a previous /plan/replan call does not affect a
    fresh /plan.
    """
    # Always start from a clean graph for a fresh /plan request.
    state.reset()

    # 1. Resolve origin node
    origin = _resolve_origin(state.graph, lat, lon, node_id)

    # 2. Route
    route = state.router.route(origin, _DEMO_DESTINATION)
    if not route.feasible:
        # Should not happen with the synthetic demo graph, but report honestly.
        route.notes.append(
            "No feasible route found from the requested origin. "
            "The synthetic demo graph may not connect this node to the shelter."
        )

    # 3. Allocation
    alloc = state.fresh_allocation()

    # 4. Assemble
    return EvacuationPlanResponse(
        scenario_id=SCENARIO_ID,
        generated_at=_utc_now(),
        is_simulated=True,
        blockage_active=False,
        origin_node=str(origin),
        origin_label=_origin_label(str(origin), lat, lon),
        zone_risks=_serialise_risk_records(
            state.risk_records, scoring_method="direct_proxy_uncalibrated"
        ),
        primary_route=_serialise_route(route),
        replanned_route=None,
        shelters=_serialise_shelters(state.shelters),
        allocation=_serialise_allocation(alloc),
        warnings=list(_BASE_WARNINGS),
        contract_version=CONTRACT_VERSION,
    )


def build_replan(
    state: DemoState,
    block_edges: List[List[str]],
) -> EvacuationPlanResponse:
    """
    Apply ``block_edges`` to the working graph and replan.

    The primary route (computed on the unblocked graph and cached in
    ``state.primary_route``) is preserved in the response so the mobile
    app can show both the original and the replanned route.

    Raises
    ------
    ValueError
        If any edge in ``block_edges`` references a node not present in
        the graph.  The caller (``main.py``) converts this to HTTP 422.
    """
    # Validate edge nodes are in the graph before mutating anything.
    for u, v in block_edges:
        if u not in state.graph.nodes:
            raise ValueError(f"Node {u!r} is not in the road-network graph.")
        if v not in state.graph.nodes:
            raise ValueError(f"Node {v!r} is not in the road-network graph.")

    state.apply_blockages(block_edges)

    origin = state.origin_node
    replanned = state.router.replan(origin, _DEMO_DESTINATION)

    # Allocation reflects the replanned (potentially longer) route costs.
    alloc = state.fresh_allocation()

    blocked_desc = ", ".join(f"{u}→{v}" for u, v in block_edges)
    extra_warnings = [
        f"⚠ Road blockage active: {blocked_desc}.",
        "Route has been replanned to avoid the blocked segment(s).",
    ]
    if not replanned.feasible:
        extra_warnings.append(
            "WARNING: No feasible alternative route found. "
            "All paths to the shelter may be blocked."
        )

    return EvacuationPlanResponse(
        scenario_id=SCENARIO_ID,
        generated_at=_utc_now(),
        is_simulated=True,
        blockage_active=True,
        origin_node=str(origin),
        origin_label=_origin_label(str(origin), None, None),
        zone_risks=_serialise_risk_records(
            state.risk_records, scoring_method="direct_proxy_uncalibrated"
        ),
        primary_route=_serialise_route(state.primary_route),
        replanned_route=_serialise_route(replanned),
        shelters=_serialise_shelters(state.shelters),
        allocation=_serialise_allocation(alloc),
        warnings=list(_BASE_WARNINGS) + extra_warnings,
        contract_version=CONTRACT_VERSION,
    )


def build_clear(state: DemoState) -> EvacuationPlanResponse:
    """
    Clear all blockages and return the restored baseline plan.

    Calls ``state.reset()`` which rebuilds the router from the original
    graph, then delegates to ``build_plan`` with the default demo origin.
    """
    state.reset()
    # build_plan also calls reset(), but that is idempotent; the double
    # call is harmless and keeps the logic self-contained.
    return build_plan(
        state,
        lat=0.0,
        lon=0.0,
        node_id=state.origin_node,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_origin(
    graph: nx.MultiDiGraph,
    lat: float,
    lon: float,
    node_id: Optional[str],
) -> Any:
    """
    Resolve the request's origin to a node id in ``graph``.

    Priority:
    1. If ``node_id`` is given and is present in the graph, use it directly.
    2. Otherwise snap (lat, lon) → nearest node via haversine scan.
    """
    if node_id is not None and node_id in graph.nodes:
        return node_id
    return nearest_node(graph, lat, lon)
