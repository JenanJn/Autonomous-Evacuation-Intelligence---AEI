"""
AEI — Routing: Evacuation Router
==================================
Provides three routing modes for evacuation planning on a road-network
graph produced by ``gis.network_loader``.

Routing Modes
-------------
A. Shortest-path
    Pure distance-minimising (or travel-time-minimising) Dijkstra.
    No risk information is used.  This is the baseline.

B. Static risk-aware
    Edge traversal cost = distance_component + risk_component.
    The two components are kept in separate, documented units and combined
    via a configurable weight (``risk_weight``).  Unknown risk is handled
    according to a documented, configurable policy.

C. Adaptive
    Wraps mode B.  After each call that returns a route, callers can report
    new blockages or risk changes.  The router replans over a working copy
    of the graph that excludes blocked edges.  If no feasible path exists
    it returns ``RouteResult(feasible=False)`` rather than raising.

Cost function (mode B and C)
-----------------------------
    cost(edge) = length_m + risk_weight * risk_m_equivalent * risk_score

    where:
        risk_weight          — dimensionless multiplier (default 1.0)
        risk_m_equivalent    — converts risk [0,1] to a length-equivalent
                               penalty in metres (default 5000 m, i.e. a
                               fully CRITICAL edge costs as if it were 5 km
                               longer)
        risk_score           — value in [0,1] from RiskOutputRecord or
                               edge attribute

All units are documented.  Metres and risk scores are never added together
without an explicit conversion factor.

Unknown risk policy
-------------------
When ``risk_score`` is None on an edge, three policies are available:
    CONSERVATIVE  — treat unknown risk as 1.0 (maximum penalty)
    NEUTRAL       — treat unknown risk as 0.5 (mid-range penalty)
    OPTIMISTIC    — treat unknown risk as 0.0 (no penalty)

The policy is passed as ``unknown_risk_policy`` to the cost function.
Default is CONSERVATIVE to err on the side of caution during evacuations.
Unknown or stale risk is NEVER silently treated as zero risk unless the
caller explicitly sets OPTIMISTIC.

City-independence
-----------------
All node IDs, coordinates and graph structure come from the caller.
Nothing geographic is hardcoded here.

Limitations
-----------
* All three modes use Dijkstra's algorithm (nx.dijkstra_path).  This is
  not optimal for very large city-scale graphs; A* with a haversine
  heuristic would be faster but adds complexity.  This is documented as
  a known limitation.
* Travel-time estimation uses a fixed speed per road type.  Real travel
  times depend on traffic, time of day and emergency conditions.
* Route costs use metres as the base unit.  Do not interpret cost values
  as real travel times without applying the speed conversion.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import networkx as nx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default speed by road type (km/h) — used for travel-time estimation only.
# These are approximate evacuation speeds, NOT normal driving speeds.
# Source: generic emergency-planning guidelines (not validated for any city).
DEFAULT_ROAD_SPEEDS_KMH: Dict[str, float] = {
    "motorway":      80.0,
    "trunk":         60.0,
    "primary":       50.0,
    "secondary":     40.0,
    "tertiary":      30.0,
    "residential":   20.0,
    "unclassified":  25.0,
    "synthetic":     30.0,
    "default":       30.0,
}

# Risk penalty: 1.0 risk score → this many extra metres of effective cost.
# This makes the risk term dimensionally consistent with length_m.
DEFAULT_RISK_M_EQUIVALENT = 5_000.0  # metres per unit risk

DEFAULT_RISK_WEIGHT = 1.0   # dimensionless multiplier on risk term


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class RoutingMode(str, Enum):
    """Which routing cost function to use."""
    SHORTEST   = "shortest"    # distance only
    RISK_AWARE = "risk_aware"  # distance + risk penalty
    ADAPTIVE   = "adaptive"    # risk_aware + auto-replanning


class UnknownRiskPolicy(str, Enum):
    """
    How to treat edges whose risk_score is None.

    CONSERVATIVE : treat as risk = 1.0   (maximum penalty — safest default)
    NEUTRAL      : treat as risk = 0.5   (mid-range penalty)
    OPTIMISTIC   : treat as risk = 0.0   (no penalty)

    Default is CONSERVATIVE.  Unknown risk MUST NOT be silently treated as
    zero unless the caller explicitly sets OPTIMISTIC.
    """
    CONSERVATIVE = "conservative"
    NEUTRAL      = "neutral"
    OPTIMISTIC   = "optimistic"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class RouteResult:
    """
    The result of one routing call.

    Attributes
    ----------
    feasible : bool
        True if a path was found.
    path : list of node ids
        Ordered node sequence from origin to destination.
        Empty when feasible=False.
    edges : list of (u, v, key) tuples
        Edges traversed, in order.
    total_length_m : float
        Sum of edge ``length_m`` values (metres).  Zero when infeasible.
    total_cost : float
        Sum of edge cost values used by the chosen routing mode.
        For SHORTEST this equals total_length_m.
        For RISK_AWARE / ADAPTIVE this includes the risk penalty term.
        Units: metres (risk component converted via risk_m_equivalent).
    total_risk_penalty_m : float
        The risk-penalty portion of total_cost (metres equivalent).
        Zero for SHORTEST mode.
    estimated_travel_time_s : float
        Rough travel-time estimate in seconds, using DEFAULT_ROAD_SPEEDS_KMH.
        This is an approximation for display only; do not use for precise
        scheduling.
    mode : RoutingMode
    origin : node id
    destination : node id
    unknown_risk_policy : UnknownRiskPolicy or None
    replanned : bool
        True if this result was produced by the adaptive replanner after a
        previous route became invalid.
    notes : list of str
        Human-readable notes (e.g. warnings about unknown risk).
    """
    feasible: bool
    path: List[Any] = field(default_factory=list)
    edges: List[tuple] = field(default_factory=list)
    total_length_m: float = 0.0
    total_cost: float = 0.0
    total_risk_penalty_m: float = 0.0
    estimated_travel_time_s: float = 0.0
    mode: RoutingMode = RoutingMode.SHORTEST
    origin: Any = None
    destination: Any = None
    unknown_risk_policy: Optional[UnknownRiskPolicy] = None
    replanned: bool = False
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Routing configuration
# ---------------------------------------------------------------------------

@dataclass
class RoutingConfig:
    """
    Configuration for the routing cost function.

    Attributes
    ----------
    mode : RoutingMode
    risk_weight : float
        Multiplier on the risk penalty term (dimensionless).
        0.0 → pure shortest-path.  Higher → more risk-averse.
    risk_m_equivalent : float
        Conversion factor: one unit of risk_score = this many metres of
        extra cost.  Must be in metres to keep units consistent.
        Default 5000 m means a fully CRITICAL (risk=1.0) edge costs as
        if it were 5 km longer.
    unknown_risk_policy : UnknownRiskPolicy
        How to handle edges with risk_score=None.
    speed_table : dict
        Road-type → speed (km/h) mapping for travel-time estimation.
    """
    mode: RoutingMode = RoutingMode.SHORTEST
    risk_weight: float = DEFAULT_RISK_WEIGHT
    risk_m_equivalent: float = DEFAULT_RISK_M_EQUIVALENT
    unknown_risk_policy: UnknownRiskPolicy = UnknownRiskPolicy.CONSERVATIVE
    speed_table: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_ROAD_SPEEDS_KMH)
    )

    def __post_init__(self) -> None:
        if self.risk_weight < 0:
            raise ValueError(f"risk_weight must be >= 0, got {self.risk_weight}.")
        if self.risk_m_equivalent <= 0:
            raise ValueError(
                f"risk_m_equivalent must be > 0, got {self.risk_m_equivalent}."
            )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class EvacuationRouter:
    """
    Stateful evacuation router.

    The router keeps a working copy of the graph so blockages and risk
    updates can be applied incrementally without modifying the caller's
    original graph.

    Parameters
    ----------
    graph : nx.MultiDiGraph
        Road-network graph from gis.network_loader.  The router makes
        a shallow working copy; the original is not modified.
    config : RoutingConfig, optional

    Usage
    -----
    >>> router = EvacuationRouter(G, RoutingConfig(mode=RoutingMode.RISK_AWARE))
    >>> result = router.route(origin_node, dest_node)
    >>> router.block_edge(u, v)
    >>> result2 = router.replan(origin_node, dest_node)
    """

    def __init__(
        self,
        graph: nx.MultiDiGraph,
        config: Optional[RoutingConfig] = None,
    ) -> None:
        self._original = graph
        self._graph = _make_working_copy(graph)
        self.config = config or RoutingConfig()
        self._blocked_edges: List[tuple] = []

    # ------------------------------------------------------------------
    # Public routing interface
    # ------------------------------------------------------------------

    def route(
        self,
        origin: Any,
        destination: Any,
        mode: Optional[RoutingMode] = None,
    ) -> RouteResult:
        """
        Find the best evacuation route from origin to destination.

        Parameters
        ----------
        origin : node id in the graph
        destination : node id in the graph
        mode : RoutingMode, optional
            Override the instance config mode for this call only.

        Returns
        -------
        RouteResult
            feasible=True if a path was found, False otherwise.
        """
        effective_mode = mode or self.config.mode
        return self._compute_route(origin, destination, effective_mode,
                                   replanned=False)

    def replan(
        self,
        origin: Any,
        destination: Any,
        mode: Optional[RoutingMode] = None,
    ) -> RouteResult:
        """
        Replan a route using the current (potentially updated) working graph.

        Call this after ``block_edge()``, ``update_edge_risk()``, or any
        other graph modification to get a route that avoids new hazards.

        Returns
        -------
        RouteResult
            feasible=False with an explanatory note when no path exists.
        """
        effective_mode = mode or self.config.mode
        result = self._compute_route(origin, destination, effective_mode,
                                     replanned=True)
        if not result.feasible:
            result.notes.append(
                "No feasible route found after replanning. "
                "All paths to destination may be blocked or costs infinite."
            )
        return result

    def block_edge(self, u: Any, v: Any) -> None:
        """
        Mark all parallel edges (u→v) as blocked in the working graph.

        Blocked edges are excluded from routing cost calculations.
        This does NOT remove them from the graph; they can be unblocked.
        """
        if not self._graph.has_edge(u, v):
            logger.warning("block_edge: edge (%s→%s) not in working graph.", u, v)
            return
        for key in self._graph[u][v]:
            self._graph[u][v][key]["blocked"] = True
        self._blocked_edges.append((u, v))
        logger.info("Router: edge (%s→%s) blocked.", u, v)

    def unblock_edge(self, u: Any, v: Any) -> None:
        """Unblock all parallel edges (u→v) in the working graph."""
        if not self._graph.has_edge(u, v):
            logger.warning("unblock_edge: edge (%s→%s) not in working graph.", u, v)
            return
        for key in self._graph[u][v]:
            self._graph[u][v][key]["blocked"] = False
        self._blocked_edges = [(a, b) for a, b in self._blocked_edges
                               if not (a == u and b == v)]
        logger.info("Router: edge (%s→%s) unblocked.", u, v)

    def update_edge_risk(self, u: Any, v: Any, risk_score: float) -> None:
        """
        Update the risk_score on all parallel edges (u→v).

        Parameters
        ----------
        risk_score : float in [0, 1]
        """
        if not (0.0 <= risk_score <= 1.0):
            raise ValueError(f"risk_score must be in [0, 1], got {risk_score}.")
        if not self._graph.has_edge(u, v):
            logger.warning("update_edge_risk: edge (%s→%s) not found.", u, v)
            return
        for key in self._graph[u][v]:
            self._graph[u][v][key]["risk_score"] = risk_score

    def reset_graph(self) -> None:
        """Reset the working graph to the original loaded state."""
        self._graph = _make_working_copy(self._original)
        self._blocked_edges = []
        logger.info("Router: working graph reset to original state.")

    @property
    def blocked_edges(self) -> List[tuple]:
        """List of (u, v) tuples currently blocked in the working graph."""
        return list(self._blocked_edges)

    @property
    def graph(self) -> nx.MultiDiGraph:
        """The current working graph (read-only access)."""
        return self._graph

    # ------------------------------------------------------------------
    # Internal routing engine
    # ------------------------------------------------------------------

    def _compute_route(
        self,
        origin: Any,
        destination: Any,
        mode: RoutingMode,
        replanned: bool,
    ) -> RouteResult:
        G = self._graph

        if origin not in G:
            return _infeasible(origin, destination, mode,
                               f"Origin node {origin!r} not in graph.",
                               replanned=replanned)
        if destination not in G:
            return _infeasible(origin, destination, mode,
                               f"Destination node {destination!r} not in graph.",
                               replanned=replanned)
        if origin == destination:
            return RouteResult(
                feasible=True, path=[origin], edges=[],
                total_length_m=0.0, total_cost=0.0,
                mode=mode, origin=origin, destination=destination,
                replanned=replanned,
                notes=["Origin equals destination — zero-length route."],
            )

        # Build a subgraph view that excludes all blocked edges.
        # This is the correct way to prevent Dijkstra traversing blocked
        # edges: nx.dijkstra_path with weight=inf still traverses edges;
        # filtering by subgraph view removes them entirely.
        G_active = nx.subgraph_view(
            G,
            filter_edge=lambda u, v, k: not G[u][v][k].get("blocked", False),
        )

        weight_fn = self._make_weight_function(mode)

        try:
            path = nx.dijkstra_path(G_active, origin, destination,
                                    weight=weight_fn)
        except nx.NetworkXNoPath:
            return _infeasible(origin, destination, mode,
                               "No path exists (graph may be disconnected or all "
                               "edges to destination are blocked).",
                               replanned=replanned)
        except nx.NodeNotFound as exc:
            return _infeasible(origin, destination, mode, str(exc),
                               replanned=replanned)

        return self._build_result(path, mode, origin, destination,
                                  replanned, weight_fn)

    def _make_weight_function(self, mode: RoutingMode):
        """
        Return a weight callable compatible with nx.dijkstra_path.

        IMPORTANT: For nx.MultiDiGraph, nx.dijkstra_path passes the
        *dict of parallel keys* {0: edge_data, 1: edge_data, ...} as the
        ``data`` argument, NOT the individual edge attribute dict.
        We pick the minimum-cost key to be consistent with _best_edge_key.

        Blocked edges return float('inf') so Dijkstra avoids them.

        Cost formula (RISK_AWARE / ADAPTIVE)
        -------------------------------------
            cost = length_m + risk_weight * risk_m_equivalent * effective_risk

        where effective_risk is determined by the unknown_risk_policy when
        risk_score is None.

        Units: all terms are in metres.
        """
        cfg = self.config
        risk_m_eq = cfg.risk_m_equivalent
        risk_w = cfg.risk_weight
        policy = cfg.unknown_risk_policy

        def _single_edge_cost(edge_data: dict) -> float:
            """Compute cost for one parallel edge's attribute dict."""
            if edge_data.get("blocked", False):
                return float("inf")

            length_m = float(edge_data.get("length_m", 0.0))

            if mode == RoutingMode.SHORTEST:
                return length_m

            # RISK_AWARE or ADAPTIVE
            raw_risk = edge_data.get("risk_score")
            if raw_risk is None:
                if policy == UnknownRiskPolicy.CONSERVATIVE:
                    effective_risk = 1.0
                elif policy == UnknownRiskPolicy.NEUTRAL:
                    effective_risk = 0.5
                else:  # OPTIMISTIC
                    effective_risk = 0.0
            else:
                effective_risk = float(raw_risk)

            return length_m + risk_w * risk_m_eq * effective_risk

        def weight(u, v, data: dict) -> float:
            # nx.dijkstra_path on a MultiDiGraph passes the parallel-keys
            # dict {key: edge_attr_dict, ...}.  Pick the minimum-cost key.
            if not data:
                return float("inf")
            # Detect whether `data` is a parallel-keys dict or a single
            # edge attribute dict.  A parallel-keys dict has integer keys;
            # a single edge dict has string attribute keys.
            first_key = next(iter(data))
            if isinstance(first_key, int):
                # data is {0: {attr_dict}, 1: {attr_dict}, ...}
                return min(_single_edge_cost(d) for d in data.values())
            else:
                # data is the attribute dict itself (fallback for DiGraph)
                return _single_edge_cost(data)

        return weight

    def _build_result(
        self,
        path: List[Any],
        mode: RoutingMode,
        origin: Any,
        destination: Any,
        replanned: bool,
        weight_fn,
    ) -> RouteResult:
        G = self._graph
        cfg = self.config

        total_length_m = 0.0
        total_cost = 0.0
        total_risk_penalty_m = 0.0
        estimated_travel_time_s = 0.0
        edges_traversed = []
        notes = []
        unknown_risk_edges = 0

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            # Use the first parallel edge (key=0) for attribute lookup.
            # nx.dijkstra_path already found this as the cheapest.
            best_key = _best_edge_key(G, u, v, weight_fn)
            data = G[u][v][best_key]

            length_m = float(data.get("length_m", 0.0))
            total_length_m += length_m

            raw_risk = data.get("risk_score")
            if raw_risk is None:
                unknown_risk_edges += 1
                policy = cfg.unknown_risk_policy
                if policy == UnknownRiskPolicy.CONSERVATIVE:
                    effective_risk = 1.0
                elif policy == UnknownRiskPolicy.NEUTRAL:
                    effective_risk = 0.5
                else:
                    effective_risk = 0.0
            else:
                effective_risk = float(raw_risk)

            if mode != RoutingMode.SHORTEST:
                rp = cfg.risk_weight * cfg.risk_m_equivalent * effective_risk
                total_risk_penalty_m += rp
                total_cost += length_m + rp
            else:
                total_cost += length_m

            # Travel-time estimate
            road_type = data.get("road_type", "default")
            speed_kmh = cfg.speed_table.get(road_type,
                                            cfg.speed_table.get("default", 30.0))
            speed_ms = speed_kmh / 3.6
            if speed_ms > 0:
                estimated_travel_time_s += length_m / speed_ms

            edges_traversed.append((u, v, best_key))

        if unknown_risk_edges > 0 and mode != RoutingMode.SHORTEST:
            notes.append(
                f"{unknown_risk_edges} edge(s) have unknown risk. "
                f"Applied policy: {cfg.unknown_risk_policy.value}. "
                "Unknown risk is NOT treated as zero unless policy=OPTIMISTIC."
            )

        return RouteResult(
            feasible=True,
            path=path,
            edges=edges_traversed,
            total_length_m=round(total_length_m, 2),
            total_cost=round(total_cost, 2),
            total_risk_penalty_m=round(total_risk_penalty_m, 2),
            estimated_travel_time_s=round(estimated_travel_time_s, 2),
            mode=mode,
            origin=origin,
            destination=destination,
            unknown_risk_policy=cfg.unknown_risk_policy,
            replanned=replanned,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def route_shortest(
    G: nx.MultiDiGraph,
    origin: Any,
    destination: Any,
) -> RouteResult:
    """
    Convenience: find the shortest (distance-only) path.

    Parameters
    ----------
    G : normalised road-network graph
    origin, destination : node ids

    Returns
    -------
    RouteResult
    """
    router = EvacuationRouter(G, RoutingConfig(mode=RoutingMode.SHORTEST))
    return router.route(origin, destination)


def route_risk_aware(
    G: nx.MultiDiGraph,
    origin: Any,
    destination: Any,
    risk_weight: float = DEFAULT_RISK_WEIGHT,
    risk_m_equivalent: float = DEFAULT_RISK_M_EQUIVALENT,
    unknown_risk_policy: UnknownRiskPolicy = UnknownRiskPolicy.CONSERVATIVE,
) -> RouteResult:
    """
    Convenience: find the risk-weighted shortest path.

    Parameters
    ----------
    G : normalised road-network graph
    origin, destination : node ids
    risk_weight : float — multiplier on the risk term
    risk_m_equivalent : float — metres penalty per unit risk
    unknown_risk_policy : UnknownRiskPolicy

    Returns
    -------
    RouteResult
    """
    cfg = RoutingConfig(
        mode=RoutingMode.RISK_AWARE,
        risk_weight=risk_weight,
        risk_m_equivalent=risk_m_equivalent,
        unknown_risk_policy=unknown_risk_policy,
    )
    router = EvacuationRouter(G, cfg)
    return router.route(origin, destination)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_working_copy(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Return a deep copy of G for use as the router's working graph."""
    return deepcopy(G)


def _infeasible(
    origin: Any,
    destination: Any,
    mode: RoutingMode,
    reason: str,
    replanned: bool = False,
) -> RouteResult:
    logger.warning("Route infeasible (%s→%s): %s", origin, destination, reason)
    return RouteResult(
        feasible=False,
        path=[],
        edges=[],
        total_length_m=0.0,
        total_cost=0.0,
        mode=mode,
        origin=origin,
        destination=destination,
        replanned=replanned,
        notes=[reason],
    )


def _best_edge_key(G: nx.MultiDiGraph, u: Any, v: Any, weight_fn) -> int:
    """
    Return the parallel-edge key with the lowest weight for edge (u, v).
    """
    best_key = 0
    best_w = float("inf")
    for key, data in G[u][v].items():
        w = weight_fn(u, v, data)
        if w < best_w:
            best_w = w
            best_key = key
    return best_key
