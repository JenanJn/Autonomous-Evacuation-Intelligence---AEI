"""
AEI — Risk Engine: Zone-to-Road Risk Mapper
=============================================
Maps risk information from geographic zones (AI prediction output) onto
road-network edges so the routing module can compute risk-aware costs.

Integration contract
--------------------
This module sits between the AI prediction module and the GIS routing module.

Input  : List[RiskOutputRecord]  — from integration.schemas
           zone_id → risk_score, risk_category, risk_status
Output : Annotated road-network graph (nx.MultiDiGraph) with
           edge["risk_score"] set to a float in [0, 1] or None.

Zone-to-road mapping
--------------------
Real deployment requires a spatial join between zone polygons and road
segments.  Without that spatial data we cannot automatically assign zones
to edges.  This module provides:

  1. ``apply_risk_records_to_graph``
       Applies a list of RiskOutputRecord objects to a graph that already
       has ``edge["zone_id"]`` set on each edge (i.e. the spatial join has
       already been done externally or by the caller).

  2. ``apply_zone_node_mapping``
       Accepts an explicit dict {zone_id → list_of_node_ids} supplied by
       the caller.  All edges whose source node is in the zone receive the
       zone's risk score.  This allows callers to supply the mapping without
       requiring GeoPandas or a spatial database.

  3. ``apply_uniform_risk``
       Applies the same risk score to all edges.  Useful for synthetic
       scenarios and testing.

Design rules
------------
* Risk score (float [0,1]) and risk category (LOW/MODERATE/HIGH/CRITICAL)
  are SEPARATE concepts from routing cost.  The router converts risk_score
  to a cost penalty via its own configurable function.  We do NOT multiply
  risk into distance here.
* Stale, missing, or UNKNOWN risk is NOT silently treated as zero.
  Edges with no applicable risk record retain risk_score=None, which the
  router handles via its UnknownRiskPolicy.
* Model target (FloodProbability) and risk_score are kept distinct.
  risk_score is derived from the AI output by the risk engine; it is NOT
  the raw predicted_value.

Limitations (documented)
------------------------
* Automatic spatial join (zone polygon → road edge) requires:
    - Zone polygon GeoJSON/Shapefile (not included in this repository).
    - GeoPandas spatial join.
  Until spatial data is supplied, callers must provide the zone→node mapping
  via ``apply_zone_node_mapping`` or pre-set edge["zone_id"].
* Temporal staleness is not propagated to individual edges here.  The
  RiskOutputRecord.risk_status field is checked; STALE_DATA or NO_DATA
  records do NOT update edge risk.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import networkx as nx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Risk categories to numeric midpoint values.
# Used when a RiskOutputRecord has no risk_score but has a risk_category.
CATEGORY_MIDPOINTS: Dict[str, float] = {
    "LOW":      0.15,
    "MODERATE": 0.40,
    "HIGH":     0.70,
    "CRITICAL": 0.90,
    "UNKNOWN":  None,  # treated as missing
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_risk_records_to_graph(
    G: nx.MultiDiGraph,
    records,                     # List[RiskOutputRecord]
    zone_id_attr: str = "zone_id",
    skip_non_ok: bool = True,
) -> Dict[str, int]:
    """
    Apply RiskOutputRecord objects to a graph that already has
    ``edge[zone_id_attr]`` set on each edge.

    For each edge, looks up its zone_id in the records dict.
    If the record's risk_status == OK, sets edge["risk_score"].
    If skip_non_ok=True (default), edges whose zone has a non-OK record
    keep risk_score=None (unknown) rather than receiving a stale or error
    value.

    Parameters
    ----------
    G : road-network graph (edges must have zone_id_attr attribute)
    records : list of RiskOutputRecord (from integration.schemas)
    zone_id_attr : str — edge attribute name that stores the zone id
    skip_non_ok : bool — if True, do not propagate non-OK risk to edges

    Returns
    -------
    dict with keys:
        updated   — edges updated with a risk_score
        skipped   — edges skipped (no matching record or non-OK status)
        total     — total edges processed

    Notes
    -----
    * This function requires that the spatial join (zone polygon → edge)
      has already been done.  It only performs the attribute lookup.
    * Edges with zone_id=None are counted as skipped.
    """
    # Build lookup dict
    from integration.schemas import RiskStatus
    record_map: Dict[str, Any] = {r.zone_id: r for r in records}

    updated = 0
    skipped = 0
    total = 0

    for u, v, k, data in G.edges(data=True, keys=True):
        total += 1
        zone_id = data.get(zone_id_attr)
        if not zone_id:
            skipped += 1
            continue

        rec = record_map.get(zone_id)
        if rec is None:
            skipped += 1
            continue

        # Only apply OK records unless caller opts in to non-OK
        if skip_non_ok and rec.risk_status != RiskStatus.OK:
            logger.debug(
                "Edge (%s→%s) zone %s: risk_status=%s — skipping (not OK).",
                u, v, zone_id, rec.risk_status.value,
            )
            skipped += 1
            continue

        score = rec.risk_score
        if score is None and rec.risk_category.value in CATEGORY_MIDPOINTS:
            score = CATEGORY_MIDPOINTS[rec.risk_category.value]

        G[u][v][k]["risk_score"] = score
        updated += 1

    logger.info(
        "apply_risk_records_to_graph: %d updated, %d skipped, %d total edges.",
        updated, skipped, total,
    )
    return {"updated": updated, "skipped": skipped, "total": total}


def apply_zone_node_mapping(
    G: nx.MultiDiGraph,
    records,                        # List[RiskOutputRecord]
    zone_node_map: Dict[str, List], # {zone_id: [node_id, ...]}
    skip_non_ok: bool = True,
) -> Dict[str, int]:
    """
    Map zone risk onto edges using an explicit zone→nodes dictionary.

    For each zone_id, all edges whose source node (u) is in the zone's
    node list receive the zone's risk_score and zone_id attribute.

    This is the primary mapping path when spatial polygon data is
    unavailable.  The caller is responsible for constructing zone_node_map;
    this module cannot invent the mapping.

    Parameters
    ----------
    G : road-network graph
    records : list of RiskOutputRecord
    zone_node_map : dict {zone_id: [node_id, ...]}
        Caller-supplied mapping from zone id to the set of road-network
        node ids that fall within (or are associated with) that zone.
    skip_non_ok : bool

    Returns
    -------
    dict with keys: updated, skipped, total

    Notes
    -----
    * If a node appears in multiple zones the LAST zone processed wins.
      Pass zone_node_map with disjoint node sets to avoid this ambiguity.
    * Spatial accuracy depends entirely on the caller-supplied mapping.
      This function cannot validate it.
    """
    from integration.schemas import RiskStatus

    record_map = {r.zone_id: r for r in records}

    # Build inverse: node_id → (zone_id, risk_score)
    node_zone: Dict[Any, tuple] = {}
    for zone_id, node_ids in zone_node_map.items():
        rec = record_map.get(zone_id)
        if rec is None:
            continue
        if skip_non_ok and rec.risk_status != RiskStatus.OK:
            continue
        score = rec.risk_score
        if score is None and rec.risk_category.value in CATEGORY_MIDPOINTS:
            score = CATEGORY_MIDPOINTS[rec.risk_category.value]
        for nid in node_ids:
            node_zone[nid] = (zone_id, score)

    updated = 0
    skipped = 0
    total = 0

    for u, v, k in G.edges(keys=True):
        total += 1
        mapping = node_zone.get(u)
        if mapping is None:
            skipped += 1
            continue
        zone_id, score = mapping
        G[u][v][k]["zone_id"] = zone_id
        G[u][v][k]["risk_score"] = score
        updated += 1

    logger.info(
        "apply_zone_node_mapping: %d updated, %d skipped, %d total edges.",
        updated, skipped, total,
    )
    return {"updated": updated, "skipped": skipped, "total": total}


def apply_uniform_risk(
    G: nx.MultiDiGraph,
    risk_score: float,
    zone_id: Optional[str] = None,
) -> int:
    """
    Apply the same risk_score to every edge in the graph.

    Use for synthetic scenarios and testing only.

    Parameters
    ----------
    G : road-network graph
    risk_score : float in [0, 1]
    zone_id : str, optional — also set this zone_id on all edges

    Returns
    -------
    int — number of edges updated
    """
    if not (0.0 <= risk_score <= 1.0):
        raise ValueError(f"risk_score must be in [0, 1], got {risk_score}.")

    count = 0
    for u, v, k in G.edges(keys=True):
        G[u][v][k]["risk_score"] = risk_score
        if zone_id is not None:
            G[u][v][k]["zone_id"] = zone_id
        count += 1

    logger.info("apply_uniform_risk: set risk=%.3f on %d edges.", risk_score, count)
    return count


def get_risk_coverage(G: nx.MultiDiGraph) -> dict:
    """
    Return a summary of how many edges have known vs unknown risk.

    Returns
    -------
    dict with keys:
        total_edges, edges_with_risk, edges_without_risk, coverage_pct,
        mean_risk (of known-risk edges), max_risk, min_risk
    """
    total = 0
    known = 0
    risk_values = []

    for _, _, data in G.edges(data=True):
        total += 1
        score = data.get("risk_score")
        if score is not None:
            known += 1
            risk_values.append(float(score))

    coverage = (known / total * 100) if total > 0 else 0.0
    mean_r = (sum(risk_values) / len(risk_values)) if risk_values else None
    max_r  = max(risk_values) if risk_values else None
    min_r  = min(risk_values) if risk_values else None

    return {
        "total_edges": total,
        "edges_with_risk": known,
        "edges_without_risk": total - known,
        "coverage_pct": round(coverage, 2),
        "mean_risk": round(mean_r, 4) if mean_r is not None else None,
        "max_risk":  round(max_r,  4) if max_r  is not None else None,
        "min_risk":  round(min_r,  4) if min_r  is not None else None,
    }


def build_synthetic_risk_records(
    zone_risk_map: Dict[str, float],
    model_version: str = "0.1.0",
) -> list:
    """
    Build a list of RiskOutputRecord objects from a simple {zone_id: score}
    dict.  Useful for tests and synthetic demonstrations.

    Parameters
    ----------
    zone_risk_map : dict {zone_id: risk_score}
    model_version : str — passed through to the schema

    Returns
    -------
    List[RiskOutputRecord]
    """
    from integration.schemas import RiskOutputRecord, RiskStatus, RiskCategory

    def _category(score: float) -> RiskCategory:
        if score >= 0.75:
            return RiskCategory.CRITICAL
        if score >= 0.50:
            return RiskCategory.HIGH
        if score >= 0.25:
            return RiskCategory.MODERATE
        return RiskCategory.LOW

    records = []
    for zone_id, score in zone_risk_map.items():
        records.append(RiskOutputRecord(
            zone_id=zone_id,
            risk_score=float(score),
            risk_category=_category(float(score)),
            data_freshness="PT0S",   # synthetic — instantaneous
            risk_status=RiskStatus.OK,
            contributing_factors=["synthetic_risk_value"],
        ))
    return records
