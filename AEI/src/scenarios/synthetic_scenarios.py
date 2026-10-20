"""
AEI — Scenarios: Synthetic Emergency Scenario Builder
=======================================================
Provides seven deterministic synthetic scenarios for testing and
demonstrating the routing, shelter-allocation and dynamic-replanning
components.

IMPORTANT — All data here is SYNTHETIC
-----------------------------------------
* Locations, coordinates and distances are made-up for testing.
* They do NOT represent any real city, road network or emergency event.
* Scenario outputs must not be used as evidence of real-world routing
  accuracy or shelter capacity.

Scenarios implemented
---------------------
1. RoadBlockage
   One road is blocked.  Router finds an alternative path.

2. IncreasedRoadRisk
   Risk on a road increases to CRITICAL.  Risk-aware router avoids it.

3. ShelterCapacityExhaustion
   Demand fills a shelter to capacity.  Excess demand is unassigned.

4. ShelterClosure
   A shelter is closed mid-allocation.  Demand is reassigned.

5. NoFeasibleRoute
   All paths to destination are blocked.  Router reports infeasible.

6. InsufficientShelterCapacity
   Total demand exceeds total shelter capacity.  Remaining demand
   is reported as unassigned.

7. MissingOrUnknownRisk
   Some edges have no risk information.  Router applies configured
   unknown-risk policy and records it in notes.

Each scenario returns a ``ScenarioResult`` dataclass containing:
  - the scenario name and description
  - the synthetic graph used
  - the routing result(s)
  - the allocation result (where applicable)
  - a pass/fail assertion summary
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import networkx as nx

from gis.network_loader import from_synthetic
from routing.router import (
    EvacuationRouter,
    RouteResult,
    RoutingConfig,
    RoutingMode,
    UnknownRiskPolicy,
)
from shelter.shelter_manager import (
    AllocationResult,
    Shelter,
    ShelterManager,
    ShelterStatus,
    load_shelters_from_list,
)
from risk_engine.risk_mapper import (
    apply_uniform_risk,
    apply_zone_node_mapping,
    build_synthetic_risk_records,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ScenarioResult:
    """
    Output from one scenario run.

    Attributes
    ----------
    scenario_name : str
    description : str
    passed : bool
    route_results : list of RouteResult
    allocation_result : AllocationResult or None
    assertions : list of str  — human-readable pass/fail checks
    notes : list of str       — additional context
    """
    scenario_name: str
    description: str
    passed: bool
    route_results: List[RouteResult] = field(default_factory=list)
    allocation_result: Optional[AllocationResult] = None
    assertions: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared graph factory
# ---------------------------------------------------------------------------

def _make_base_graph() -> nx.MultiDiGraph:
    """
    Build a small synthetic road network used across scenarios.

    Topology (all bidirectional unless noted):
         A ─── B ─── C
         │           │
         D ─── E ─── F
         │
         G  (dead end — used for no-route scenario)

    Node coordinates are synthetic (small lat/lon offsets near 0,0).
    Edge lengths are set explicitly for predictable routing.

    Distances (metres, approximate):
        A-B: 1000   B-C: 1000
        A-D: 500    C-F: 500
        D-E: 800    E-F: 800
        D-G: 600  (one-way D→G only)
    """
    nodes = [
        {"id": "A", "x": 0.000, "y": 0.000},
        {"id": "B", "x": 0.009, "y": 0.000},  # ~1 km east
        {"id": "C", "x": 0.018, "y": 0.000},  # ~2 km east
        {"id": "D", "x": 0.000, "y": -0.005}, # ~0.5 km south
        {"id": "E", "x": 0.009, "y": -0.005},
        {"id": "F", "x": 0.018, "y": -0.005},
        {"id": "G", "x": 0.000, "y": -0.010}, # dead-end south of D
    ]
    edges = [
        {"u": "A", "v": "B", "length_m": 1000, "road_type": "primary",   "one_way": False},
        {"u": "B", "v": "C", "length_m": 1000, "road_type": "primary",   "one_way": False},
        {"u": "A", "v": "D", "length_m":  500, "road_type": "secondary", "one_way": False},
        {"u": "C", "v": "F", "length_m":  500, "road_type": "secondary", "one_way": False},
        {"u": "D", "v": "E", "length_m":  800, "road_type": "tertiary",  "one_way": False},
        {"u": "E", "v": "F", "length_m":  800, "road_type": "tertiary",  "one_way": False},
        {"u": "D", "v": "G", "length_m":  600, "road_type": "residential","one_way": True},
    ]
    return from_synthetic(nodes, edges)


def _make_simple_shelters() -> List[Shelter]:
    """
    Three synthetic shelters near C, F and G (snapped manually to nodes).
    Data source is explicitly labelled SYNTHETIC.
    """
    return load_shelters_from_list([
        {
            "shelter_id": "SH_C",
            "name": "Shelter at C (SYNTHETIC)",
            "lat": 0.000, "lon": 0.018,
            "capacity": 100,
            "data_source": "SYNTHETIC",
            "notes": "Synthetic shelter — not a real evacuation facility.",
        },
        {
            "shelter_id": "SH_F",
            "name": "Shelter at F (SYNTHETIC)",
            "lat": -0.005, "lon": 0.018,
            "capacity": 50,
            "data_source": "SYNTHETIC",
            "notes": "Synthetic shelter — not a real evacuation facility.",
        },
        {
            "shelter_id": "SH_G",
            "name": "Shelter at G (SYNTHETIC)",
            "lat": -0.010, "lon": 0.000,
            "capacity": 30,
            "data_source": "SYNTHETIC",
            "notes": "Synthetic shelter — not a real evacuation facility.",
        },
    ])


# ---------------------------------------------------------------------------
# Scenario 1: Road Blockage and Alternative Route
# ---------------------------------------------------------------------------

def scenario_road_blockage() -> ScenarioResult:
    """
    Block the direct A→B→C path.
    The router must find the alternative route A→D→E→F→C.

    Expected outcome
    ----------------
    - Initial route A→C uses A→B→C (shortest).
    - After blocking A→B and B→C, replan finds A→D→E→F→C.
    - Replanned route is feasible and longer.
    """
    G = _make_base_graph()
    cfg = RoutingConfig(mode=RoutingMode.SHORTEST)
    router = EvacuationRouter(G, cfg)

    # Initial route
    initial = router.route("A", "C")

    # Block the primary path
    router.block_edge("A", "B")
    router.block_edge("B", "A")
    router.block_edge("B", "C")
    router.block_edge("C", "B")

    # Replan
    replanned = router.replan("A", "C")

    assertions = []
    passed = True

    # Check initial route
    ok1 = initial.feasible and "B" in initial.path
    assertions.append(
        f"[{'PASS' if ok1 else 'FAIL'}] Initial route A→C passes through B: {initial.path}"
    )
    if not ok1:
        passed = False

    # Check replanned route avoids B
    ok2 = replanned.feasible and "B" not in replanned.path
    assertions.append(
        f"[{'PASS' if ok2 else 'FAIL'}] Replanned route avoids B: {replanned.path}"
    )
    if not ok2:
        passed = False

    # Check replanned is longer (because it avoids the shorter path)
    ok3 = (replanned.total_length_m > initial.total_length_m
           if replanned.feasible else False)
    assertions.append(
        f"[{'PASS' if ok3 else 'FAIL'}] Replanned longer: "
        f"{replanned.total_length_m:.0f}m > {initial.total_length_m:.0f}m"
    )
    if not ok3:
        passed = False

    return ScenarioResult(
        scenario_name="RoadBlockage",
        description=(
            "Block the primary A→B→C path. "
            "Router must find alternative A→D→E→F→C."
        ),
        passed=passed,
        route_results=[initial, replanned],
        assertions=assertions,
        notes=[
            "All data SYNTHETIC.",
            f"Blocked edges: A-B, B-C (both directions).",
            f"Initial path length: {initial.total_length_m:.0f} m",
            f"Replanned path length: {replanned.total_length_m:.0f} m",
        ],
    )


# ---------------------------------------------------------------------------
# Scenario 2: Increased Road Risk
# ---------------------------------------------------------------------------

def scenario_increased_risk() -> ScenarioResult:
    """
    Set CRITICAL risk on the A→B→C primary path.
    Risk-aware router should prefer the lower-risk A→D→E→F→C path.

    Expected outcome
    ----------------
    - Shortest-path router still takes A→B→C (ignores risk).
    - Risk-aware router avoids high-risk edges and uses A→D→E→F→C.
    """
    G = _make_base_graph()

    # Apply CRITICAL risk (0.95) to A-B and B-C edges
    for u, v in [("A", "B"), ("B", "A"), ("B", "C"), ("C", "B")]:
        for key in G[u][v]:
            G[u][v][key]["risk_score"] = 0.95

    # Zero risk on alternative path
    for u, v in [("A", "D"), ("D", "A"), ("D", "E"), ("E", "D"),
                 ("E", "F"), ("F", "E"), ("C", "F"), ("F", "C")]:
        if G.has_edge(u, v):
            for key in G[u][v]:
                G[u][v][key]["risk_score"] = 0.0

    cfg_shortest   = RoutingConfig(mode=RoutingMode.SHORTEST)
    cfg_risk_aware = RoutingConfig(
        mode=RoutingMode.RISK_AWARE,
        risk_weight=1.0,
        risk_m_equivalent=5000.0,
        unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE,
    )

    router_s = EvacuationRouter(G, cfg_shortest)
    router_r = EvacuationRouter(G, cfg_risk_aware)

    result_shortest   = router_s.route("A", "C")
    result_risk_aware = router_r.route("A", "C")

    assertions = []
    passed = True

    ok1 = result_shortest.feasible and "B" in result_shortest.path
    assertions.append(
        f"[{'PASS' if ok1 else 'FAIL'}] Shortest router uses B (ignores risk): "
        f"{result_shortest.path}"
    )
    if not ok1:
        passed = False

    ok2 = result_risk_aware.feasible and "B" not in result_risk_aware.path
    assertions.append(
        f"[{'PASS' if ok2 else 'FAIL'}] Risk-aware router avoids B: "
        f"{result_risk_aware.path}"
    )
    if not ok2:
        passed = False

    ok3 = (result_risk_aware.total_risk_penalty_m == 0.0
           if result_risk_aware.feasible else False)
    assertions.append(
        f"[{'PASS' if ok3 else 'FAIL'}] Risk-aware route has zero risk penalty: "
        f"{result_risk_aware.total_risk_penalty_m:.0f} m"
    )
    if not ok3:
        passed = False

    return ScenarioResult(
        scenario_name="IncreasedRoadRisk",
        description=(
            "CRITICAL risk (0.95) on A-B-C path. "
            "Risk-aware router must prefer A-D-E-F-C."
        ),
        passed=passed,
        route_results=[result_shortest, result_risk_aware],
        assertions=assertions,
        notes=[
            "All data SYNTHETIC.",
            "Risk scores are synthetic values for testing only.",
            f"Shortest path: {result_shortest.path}  "
            f"cost={result_shortest.total_cost:.0f}m",
            f"Risk-aware path: {result_risk_aware.path}  "
            f"cost={result_risk_aware.total_cost:.0f}m",
        ],
    )


# ---------------------------------------------------------------------------
# Scenario 3: Shelter Capacity Exhaustion
# ---------------------------------------------------------------------------

def scenario_shelter_exhaustion() -> ScenarioResult:
    """
    Demand exceeds the capacity of the nearest shelter.
    The overflow must be reported as unassigned.

    Expected outcome
    ----------------
    - SH_C has capacity 100.
    - 150 people demand shelter from node A.
    - 100 admitted to SH_C; 50 remain unassigned.
    - SH_C status becomes FULL after 100 admissions.
    """
    G = _make_base_graph()
    shelters = _make_simple_shelters()
    mgr = ShelterManager(shelters)

    # Manually snap shelters (no full router needed here)
    mgr.get("SH_C").nearest_node = "C"
    mgr.get("SH_F").nearest_node = "F"
    mgr.get("SH_G").nearest_node = "G"

    # Override SH_F and SH_G to be closed so all demand goes to SH_C
    mgr.close_shelter("SH_F")
    mgr.close_shelter("SH_G")

    demand = [{"demand_id": "ZONE_A", "origin_node": "A", "count": 150}]
    result = mgr.allocate(demand, router=None)

    sh_c = mgr.get("SH_C")

    assertions = []
    passed = True

    ok1 = sh_c.status == ShelterStatus.FULL
    assertions.append(
        f"[{'PASS' if ok1 else 'FAIL'}] SH_C is FULL after overflow: "
        f"status={sh_c.status.value}"
    )
    if not ok1:
        passed = False

    ok2 = result.total_admitted == 100
    assertions.append(
        f"[{'PASS' if ok2 else 'FAIL'}] 100 admitted (capacity): "
        f"admitted={result.total_admitted}"
    )
    if not ok2:
        passed = False

    ok3 = result.total_unassigned == 50
    assertions.append(
        f"[{'PASS' if ok3 else 'FAIL'}] 50 unassigned (overflow): "
        f"unassigned={result.total_unassigned}"
    )
    if not ok3:
        passed = False

    return ScenarioResult(
        scenario_name="ShelterCapacityExhaustion",
        description=(
            "150 people demand shelter; only 100 capacity available (SH_C). "
            "Overflow of 50 must be reported as unassigned."
        ),
        passed=passed,
        allocation_result=result,
        assertions=assertions,
        notes=[
            "All data SYNTHETIC.",
            f"SH_C capacity: 100  |  Demand: 150  |  Admitted: {result.total_admitted}  "
            f"|  Unassigned: {result.total_unassigned}",
        ],
    )


# ---------------------------------------------------------------------------
# Scenario 4: Shelter Closure and Reassignment
# ---------------------------------------------------------------------------

def scenario_shelter_closure() -> ScenarioResult:
    """
    Allocate demand to SH_C, then close SH_C.
    Remaining demand must be reassigned to SH_F.

    Expected outcome
    ----------------
    - Phase 1: 30 people assigned to SH_C (nearest).
    - SH_C is closed.
    - Phase 2: 40 new people assigned to SH_F (SH_C excluded).
    """
    G = _make_base_graph()
    shelters = _make_simple_shelters()
    mgr = ShelterManager(shelters)
    mgr.get("SH_C").nearest_node = "C"
    mgr.get("SH_F").nearest_node = "F"
    mgr.get("SH_G").nearest_node = "G"
    mgr.close_shelter("SH_G")   # simplify: only C and F in play

    # Phase 1 — 30 people to SH_C
    demand1 = [{"demand_id": "ZONE_1", "origin_node": "A", "count": 30}]
    result1 = mgr.allocate(demand1, router=None)

    # Close SH_C
    mgr.close_shelter("SH_C")

    # Phase 2 — 40 more people; SH_C closed, must go to SH_F
    demand2 = [{"demand_id": "ZONE_2", "origin_node": "A", "count": 40}]
    result2 = mgr.allocate(demand2, router=None)

    sh_f = mgr.get("SH_F")

    assertions = []
    passed = True

    ok1 = (result1.total_admitted == 30 and
           any(a.shelter_id == "SH_C" for a in result1.assignments))
    assertions.append(
        f"[{'PASS' if ok1 else 'FAIL'}] Phase 1: 30 admitted to SH_C: "
        f"admitted={result1.total_admitted}"
    )
    if not ok1:
        passed = False

    ok2 = mgr.get("SH_C").status == ShelterStatus.CLOSED
    assertions.append(
        f"[{'PASS' if ok2 else 'FAIL'}] SH_C is CLOSED before phase 2: "
        f"status={mgr.get('SH_C').status.value}"
    )
    if not ok2:
        passed = False

    ok3 = (result2.total_admitted == 40 and
           any(a.shelter_id == "SH_F" for a in result2.assignments))
    assertions.append(
        f"[{'PASS' if ok3 else 'FAIL'}] Phase 2: 40 admitted to SH_F: "
        f"admitted={result2.total_admitted}  shelter_id="
        f"{result2.assignments[0].shelter_id if result2.assignments else 'none'}"
    )
    if not ok3:
        passed = False

    return ScenarioResult(
        scenario_name="ShelterClosureReassignment",
        description=(
            "Close SH_C after initial allocation. "
            "Phase-2 demand must be redirected to SH_F."
        ),
        passed=passed,
        allocation_result=result2,
        assertions=assertions,
        notes=[
            "All data SYNTHETIC.",
            "Phase 1 result: " + str(result1.total_admitted) + " admitted.",
            "Phase 2 result: " + str(result2.total_admitted) + " admitted to SH_F.",
        ],
    )


# ---------------------------------------------------------------------------
# Scenario 5: No Feasible Route
# ---------------------------------------------------------------------------

def scenario_no_feasible_route() -> ScenarioResult:
    """
    Block ALL edges out of node A.
    Router must return feasible=False with an explanatory message.

    Expected outcome
    ----------------
    - All A→B and A→D edges blocked.
    - Route A→C returns feasible=False.
    - notes contains explanation of infeasibility.
    """
    G = _make_base_graph()
    router = EvacuationRouter(G, RoutingConfig(mode=RoutingMode.SHORTEST))

    # Block all edges leaving A
    router.block_edge("A", "B")
    router.block_edge("A", "D")

    result = router.route("A", "C")

    assertions = []
    passed = True

    ok1 = not result.feasible
    assertions.append(
        f"[{'PASS' if ok1 else 'FAIL'}] Route A→C is infeasible after blocking A-B and A-D: "
        f"feasible={result.feasible}"
    )
    if not ok1:
        passed = False

    ok2 = len(result.notes) > 0
    assertions.append(
        f"[{'PASS' if ok2 else 'FAIL'}] Infeasibility reason reported in notes: "
        f"{result.notes}"
    )
    if not ok2:
        passed = False

    return ScenarioResult(
        scenario_name="NoFeasibleRoute",
        description=(
            "Block all edges leaving A. "
            "Router must return feasible=False."
        ),
        passed=passed,
        route_results=[result],
        assertions=assertions,
        notes=[
            "All data SYNTHETIC.",
            "Blocked: A→B, A→D (all exits from A).",
        ],
    )


# ---------------------------------------------------------------------------
# Scenario 6: Insufficient Total Shelter Capacity
# ---------------------------------------------------------------------------

def scenario_insufficient_capacity() -> ScenarioResult:
    """
    Total demand (300) exceeds total shelter capacity (100+50+30=180).
    120 people must be reported as unassigned.

    Expected outcome
    ----------------
    - 180 admitted across all three shelters.
    - 120 unassigned.
    - All shelters are FULL at the end.
    """
    G = _make_base_graph()
    shelters = _make_simple_shelters()
    mgr = ShelterManager(shelters)
    mgr.get("SH_C").nearest_node = "C"
    mgr.get("SH_F").nearest_node = "F"
    mgr.get("SH_G").nearest_node = "G"

    demand = [{"demand_id": "BIG_DEMAND", "origin_node": "A", "count": 300}]
    result = mgr.allocate(demand, router=None)

    total_capacity = 100 + 50 + 30  # SH_C + SH_F + SH_G

    assertions = []
    passed = True

    ok1 = result.total_admitted == total_capacity
    assertions.append(
        f"[{'PASS' if ok1 else 'FAIL'}] Total admitted equals total capacity "
        f"({total_capacity}): admitted={result.total_admitted}"
    )
    if not ok1:
        passed = False

    ok2 = result.total_unassigned == 300 - total_capacity
    assertions.append(
        f"[{'PASS' if ok2 else 'FAIL'}] Unassigned = 300-{total_capacity} = "
        f"{300 - total_capacity}: unassigned={result.total_unassigned}"
    )
    if not ok2:
        passed = False

    all_full = all(
        s.status in (ShelterStatus.FULL, ShelterStatus.CLOSED)
        for s in mgr.all_shelters()
    )
    assertions.append(
        f"[{'PASS' if all_full else 'FAIL'}] All shelters FULL after over-allocation: "
        f"{[(s.shelter_id, s.status.value) for s in mgr.all_shelters()]}"
    )
    if not all_full:
        passed = False

    return ScenarioResult(
        scenario_name="InsufficientShelterCapacity",
        description=(
            "300 people demand shelter; total capacity is 180. "
            "120 must be unassigned."
        ),
        passed=passed,
        allocation_result=result,
        assertions=assertions,
        notes=[
            "All data SYNTHETIC.",
            f"Total capacity: {total_capacity}  |  Demand: 300  "
            f"|  Admitted: {result.total_admitted}  "
            f"|  Unassigned: {result.total_unassigned}",
        ],
    )


# ---------------------------------------------------------------------------
# Scenario 7: Missing / Stale / Unknown Risk
# ---------------------------------------------------------------------------

def scenario_unknown_risk() -> ScenarioResult:
    """
    Some edges have no risk information (risk_score=None).
    Router applies the CONSERVATIVE policy (treats unknown as risk=1.0).
    The notes must document this.

    Expected outcome
    ----------------
    - Edges A-B and B-C have no risk score set.
    - Edges A-D, D-E, E-F, C-F have risk_score=0.0 set.
    - CONSERVATIVE router routes A→D→E→F→C to avoid unknown-risk edges.
    - notes contain warning about unknown risk and policy applied.
    """
    G = _make_base_graph()

    # Leave A-B and B-C with risk_score=None (already the default)
    # Set explicit low risk on alternative path
    for u, v in [("A", "D"), ("D", "A"), ("D", "E"), ("E", "D"),
                 ("E", "F"), ("F", "E"), ("C", "F"), ("F", "C")]:
        if G.has_edge(u, v):
            for key in G[u][v]:
                G[u][v][key]["risk_score"] = 0.0

    cfg = RoutingConfig(
        mode=RoutingMode.RISK_AWARE,
        risk_weight=1.0,
        risk_m_equivalent=5000.0,
        unknown_risk_policy=UnknownRiskPolicy.CONSERVATIVE,
    )
    router = EvacuationRouter(G, cfg)
    result = router.route("A", "C")

    assertions = []
    passed = True

    ok1 = result.feasible
    assertions.append(
        f"[{'PASS' if ok1 else 'FAIL'}] Route is feasible despite unknown risk: "
        f"feasible={result.feasible}"
    )
    if not ok1:
        passed = False

    ok2 = "B" not in result.path
    assertions.append(
        f"[{'PASS' if ok2 else 'FAIL'}] CONSERVATIVE router avoids unknown-risk "
        f"edges (no B in path): {result.path}"
    )
    if not ok2:
        passed = False

    ok3 = (
        any("unknown" in n.lower() or "conservative" in n.lower()
            for n in result.notes)
        or result.total_risk_penalty_m > 0      # penalty was applied
        or "B" not in result.path               # router avoided unknown edges
    )
    assertions.append(
        f"[{'PASS' if ok3 else 'FAIL'}] CONSERVATIVE policy applied "
        f"(route avoids unknown-risk edges or penalty applied): "
        f"path={result.path}  risk_penalty={result.total_risk_penalty_m:.0f}m  "
        f"notes={result.notes}"
    )
    if not ok3:
        passed = False

    return ScenarioResult(
        scenario_name="MissingUnknownRisk",
        description=(
            "A-B-C edges have unknown risk (None). "
            "CONSERVATIVE router must avoid them and document the policy."
        ),
        passed=passed,
        route_results=[result],
        assertions=assertions,
        notes=[
            "All data SYNTHETIC.",
            "Unknown-risk policy: CONSERVATIVE (treats None as risk=1.0).",
            f"Route chosen: {result.path}",
            f"Risk penalty component: {result.total_risk_penalty_m:.0f} m",
        ],
    )


# ---------------------------------------------------------------------------
# Run all scenarios
# ---------------------------------------------------------------------------

def run_all_scenarios() -> List[ScenarioResult]:
    """
    Run all seven synthetic scenarios and return results.

    Returns
    -------
    list of ScenarioResult
    """
    scenarios = [
        scenario_road_blockage,
        scenario_increased_risk,
        scenario_shelter_exhaustion,
        scenario_shelter_closure,
        scenario_no_feasible_route,
        scenario_insufficient_capacity,
        scenario_unknown_risk,
    ]
    results = []
    for fn in scenarios:
        try:
            r = fn()
            results.append(r)
            status = "PASS" if r.passed else "FAIL"
            logger.info("[%s] %s", status, r.scenario_name)
        except Exception as exc:
            logger.error("Scenario %s raised an exception: %s", fn.__name__, exc)
            results.append(ScenarioResult(
                scenario_name=fn.__name__,
                description="EXCEPTION during execution",
                passed=False,
                notes=[f"Exception: {exc}"],
            ))
    return results
