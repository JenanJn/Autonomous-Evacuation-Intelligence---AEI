"""
AEI — GIS: Road-Network Loader
================================
Loads and validates a road network as a NetworkX graph whose edges carry
geometry, length, and traversal-cost attributes consumed by the routing
module.

Design rules
------------
* No city, coordinates or road IDs are hardcoded.  Every geographic
  parameter is supplied by the caller at runtime.
* Two loading strategies are supported:
    - ``from_osm``      — query OpenStreetMap via the Overpass API
                          (requires internet; wraps osmnx).
    - ``from_synthetic``— build a purely in-memory graph from a caller-
                          supplied node/edge specification.  This is the
                          primary path for tests and offline scenarios.
* Both strategies produce graphs in the same normalised format so the
  routing module never needs to know the original data source.

Normalised edge attributes after loading
-----------------------------------------
  length_m   float   — Euclidean distance between endpoints (metres).
                        For synthetic graphs this is derived from node
                        coordinates; for OSM graphs it is preserved from
                        the osmnx 'length' field.
  road_type  str     — OSM highway tag or 'synthetic'.
  blocked    bool    — True if this edge is currently impassable.
                        Always False after initial load; set via
                        block_edge() / unblock_edge().
  risk_score float|None — Risk value in [0, 1] injected by the risk
                          mapper.  None until mapped.
  zone_id    str|None   — Geographic zone this edge belongs to.  None
                          until mapped.

CRS handling
------------
All coordinates are stored in EPSG:4326 (WGS 84 geographic) in the node
attributes 'x' (longitude) and 'y' (latitude).  Length calculations use
the haversine approximation when pyproj is available and fall back to a
flat-earth Euclidean approximation otherwise.  The active CRS is recorded
in ``graph.graph['crs']``.

Data-quality notes
------------------
* OSM data represents the road network as it existed at query time.
  It may contain errors, missing roads, or outdated connectivity.
* Synthetic graphs are deterministic and reproducible but do not represent
  any real place.  Always label outputs with their data source.
* The OSM loader filters to drivable roads by default (network_type='drive')
  to avoid pedestrian and private roads appearing in evacuation routes.

Internet-access handling
------------------------
``from_osm`` catches connection errors and raises a descriptive
``NetworkLoadError`` so callers can fall back gracefully to a cached or
synthetic graph.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EARTH_RADIUS_M = 6_371_000.0   # metres
DEFAULT_NETWORK_TYPE = "drive"  # osmnx network_type for drivable roads
DEFAULT_CRS = "EPSG:4326"       # WGS 84 — all node coords stored here


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class NetworkLoadError(RuntimeError):
    """Raised when the road network cannot be loaded."""


class NetworkValidationError(ValueError):
    """Raised when a loaded graph fails structural validation."""


# ---------------------------------------------------------------------------
# Graph metadata
# ---------------------------------------------------------------------------

@dataclass
class NetworkMetadata:
    """
    Records how and when a road-network graph was loaded.

    Stored in ``graph.graph['_aei_meta']`` so it travels with the graph.
    """
    source: str                        # 'osm' | 'synthetic' | 'file'
    query_area: Optional[str] = None   # human-readable query description
    crs: str = DEFAULT_CRS
    node_count: int = 0
    edge_count: int = 0
    data_disclaimer: str = (
        "Road network data may be incomplete, outdated or inaccurate. "
        "Do not rely on it as the sole source for operational decisions."
    )
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def from_osm(
    query: str,
    network_type: str = DEFAULT_NETWORK_TYPE,
    simplify: bool = True,
    retain_all: bool = False,
    timeout: int = 180,
) -> nx.MultiDiGraph:
    """
    Download a road network from OpenStreetMap via the Overpass API.

    Parameters
    ----------
    query : str
        A place name, address, or GeoJSON-like area string understood by
        osmnx (e.g. ``"Chennai, India"``).  No city is hardcoded.
    network_type : str
        osmnx network type.  Defaults to ``"drive"`` (drivable roads only).
    simplify : bool
        If True, osmnx simplifies the graph topology (removes degree-2 nodes
        that are not intersections).
    retain_all : bool
        If True, keep all graph components (including isolated nodes).
    timeout : int
        HTTP request timeout in seconds.

    Returns
    -------
    nx.MultiDiGraph
        Normalised graph with AEI edge attributes attached.

    Raises
    ------
    NetworkLoadError
        If the download fails (no internet, Overpass timeout, bad query).

    Notes
    -----
    * This function requires internet access.
    * The returned network represents OSM data at the time of download.
      It may contain errors or missing roads.
    * Only drivable roads are included by default; pedestrian and private
      roads are excluded.
    """
    try:
        import osmnx as ox
    except ImportError as exc:
        raise NetworkLoadError(
            "osmnx is required for OSM loading. "
            "Install it with: pip install osmnx==1.9.4"
        ) from exc

    logger.info("Downloading OSM road network for: %s  (type=%s)", query, network_type)
    try:
        ox.settings.timeout = timeout
        G = ox.graph_from_place(
            query,
            network_type=network_type,
            simplify=simplify,
            retain_all=retain_all,
        )
    except Exception as exc:
        raise NetworkLoadError(
            f"Failed to download OSM road network for '{query}': {exc}"
        ) from exc

    G = _normalise_osm_graph(G)
    meta = NetworkMetadata(
        source="osm",
        query_area=query,
        crs=DEFAULT_CRS,
        node_count=G.number_of_nodes(),
        edge_count=G.number_of_edges(),
    )
    G.graph["_aei_meta"] = meta
    G.graph["crs"] = DEFAULT_CRS

    logger.info(
        "OSM graph loaded: %d nodes, %d edges", meta.node_count, meta.edge_count
    )
    validate_graph(G)
    return G


def from_synthetic(
    nodes: List[Dict],
    edges: List[Dict],
    crs: str = DEFAULT_CRS,
) -> nx.MultiDiGraph:
    """
    Build a road-network graph from explicit node and edge dictionaries.

    Use this for tests, offline scenarios, and synthetic demonstrations
    where OSM data is unavailable.

    Parameters
    ----------
    nodes : list of dict
        Each dict must have ``id`` (any hashable), ``x`` (longitude or
        easting) and ``y`` (latitude or northing).  Additional attributes
        are preserved.

    edges : list of dict
        Each dict must have ``u`` (source node id), ``v`` (target node id).
        Optional keys: ``length_m`` (float), ``road_type`` (str),
        ``one_way`` (bool, default False).  If ``length_m`` is absent it
        is computed from node coordinates using the haversine formula.

    crs : str
        Coordinate reference system string (e.g. ``"EPSG:4326"``).

    Returns
    -------
    nx.MultiDiGraph
        Normalised graph suitable for the AEI routing module.

    Notes
    -----
    * Graphs built here are SYNTHETIC.  They do not represent any real
      road network.  Label outputs accordingly.
    * If ``one_way=False`` (default), both directed edges (u→v and v→u)
      are added so the graph is traversable in both directions.
    """
    G: nx.MultiDiGraph = nx.MultiDiGraph()
    G.graph["crs"] = crs

    # Add nodes
    for n in nodes:
        node_id = n["id"]
        attrs = {k: v for k, v in n.items() if k != "id"}
        G.add_node(node_id, **attrs)

    # Add edges
    for e in edges:
        u, v = e["u"], e["v"]
        one_way = e.get("one_way", False)

        length_m = e.get("length_m")
        if length_m is None:
            length_m = _haversine_m(
                G.nodes[u]["y"], G.nodes[u]["x"],
                G.nodes[v]["y"], G.nodes[v]["x"],
            )

        road_type = e.get("road_type", "synthetic")
        extra = {k: v for k, v in e.items()
                 if k not in ("u", "v", "length_m", "road_type", "one_way")}

        edge_attrs = _default_edge_attrs(length_m, road_type, extra)
        G.add_edge(u, v, **edge_attrs)
        if not one_way:
            G.add_edge(v, u, **edge_attrs)

    meta = NetworkMetadata(
        source="synthetic",
        query_area="synthetic_in_memory",
        crs=crs,
        node_count=G.number_of_nodes(),
        edge_count=G.number_of_edges(),
    )
    G.graph["_aei_meta"] = meta

    logger.info(
        "Synthetic graph built: %d nodes, %d edges", meta.node_count, meta.edge_count
    )
    validate_graph(G)
    return G


def from_graphml(path: str | Path, crs: str = DEFAULT_CRS) -> nx.MultiDiGraph:
    """
    Load a road network from a GraphML file (e.g. saved by osmnx).

    Parameters
    ----------
    path : str or Path
        Path to the .graphml file.
    crs : str
        CRS of the coordinates stored in the file.

    Returns
    -------
    nx.MultiDiGraph

    Raises
    ------
    FileNotFoundError  — if the file does not exist.
    NetworkLoadError   — if the file cannot be parsed.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"GraphML file not found: {path}")

    try:
        import osmnx as ox
        G = ox.load_graphml(str(path))
    except Exception:
        try:
            G = nx.read_graphml(str(path))
            G = nx.MultiDiGraph(G)
        except Exception as exc:
            raise NetworkLoadError(f"Cannot load GraphML file '{path}': {exc}") from exc

    G = _normalise_osm_graph(G)
    G.graph["crs"] = crs
    meta = NetworkMetadata(
        source="file",
        query_area=str(path),
        crs=crs,
        node_count=G.number_of_nodes(),
        edge_count=G.number_of_edges(),
    )
    G.graph["_aei_meta"] = meta
    validate_graph(G)
    return G


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_graph(G: nx.MultiDiGraph) -> None:
    """
    Check that the graph satisfies the minimum structural requirements for
    AEI routing.

    Raises NetworkValidationError with a descriptive message if any check
    fails.

    Checks performed
    ----------------
    1. Graph is a MultiDiGraph (directed, supports parallel edges).
    2. At least two nodes (cannot route in a single-node graph).
    3. All nodes have numeric ``x`` and ``y`` attributes.
    4. All edges have finite numeric ``length_m`` > 0.
    5. All edges have a ``blocked`` attribute (bool).
    """
    if not isinstance(G, nx.MultiDiGraph):
        raise NetworkValidationError(
            f"Expected nx.MultiDiGraph, got {type(G).__name__}."
        )
    if G.number_of_nodes() < 2:
        raise NetworkValidationError(
            f"Graph has {G.number_of_nodes()} node(s) — need at least 2 to route."
        )

    bad_nodes = []
    for n, data in G.nodes(data=True):
        if not (_is_finite_number(data.get("x")) and _is_finite_number(data.get("y"))):
            bad_nodes.append(n)
    if bad_nodes:
        raise NetworkValidationError(
            f"{len(bad_nodes)} node(s) missing valid x/y coordinates: "
            f"{bad_nodes[:5]}{'...' if len(bad_nodes) > 5 else ''}"
        )

    bad_edges = []
    for u, v, k, data in G.edges(data=True, keys=True):
        lm = data.get("length_m")
        if not (_is_finite_number(lm) and lm > 0):
            bad_edges.append((u, v, k))
        if "blocked" not in data:
            bad_edges.append((u, v, k))
    if bad_edges:
        raise NetworkValidationError(
            f"{len(bad_edges)} edge(s) missing valid length_m or blocked attribute: "
            f"{bad_edges[:3]}{'...' if len(bad_edges) > 3 else ''}"
        )

    logger.debug(
        "Graph validated OK: %d nodes, %d edges",
        G.number_of_nodes(), G.number_of_edges(),
    )


# ---------------------------------------------------------------------------
# Edge-state management
# ---------------------------------------------------------------------------

def block_edge(G: nx.MultiDiGraph, u: Any, v: Any) -> None:
    """
    Mark all parallel edges between u and v as blocked.

    This does NOT remove the edges from the graph; the routing module
    checks the ``blocked`` attribute and skips blocked edges.  This
    preserves graph topology so edges can be unblocked later.

    Parameters
    ----------
    u, v : node identifiers
    """
    if not G.has_edge(u, v):
        logger.warning("block_edge called for non-existent edge (%s, %s)", u, v)
        return
    for key in G[u][v]:
        G[u][v][key]["blocked"] = True
    logger.info("Edge (%s → %s) blocked.", u, v)


def unblock_edge(G: nx.MultiDiGraph, u: Any, v: Any) -> None:
    """Unblock all parallel edges between u and v."""
    if not G.has_edge(u, v):
        logger.warning("unblock_edge called for non-existent edge (%s, %s)", u, v)
        return
    for key in G[u][v]:
        G[u][v][key]["blocked"] = False
    logger.info("Edge (%s → %s) unblocked.", u, v)


def set_edge_risk(
    G: nx.MultiDiGraph, u: Any, v: Any, risk_score: float
) -> None:
    """
    Assign a risk_score to all parallel edges between u and v.

    Parameters
    ----------
    risk_score : float in [0, 1]
    """
    if not (0.0 <= risk_score <= 1.0):
        raise ValueError(
            f"risk_score must be in [0, 1], got {risk_score}."
        )
    if not G.has_edge(u, v):
        logger.warning("set_edge_risk called for non-existent edge (%s, %s)", u, v)
        return
    for key in G[u][v]:
        G[u][v][key]["risk_score"] = risk_score


def get_graph_summary(G: nx.MultiDiGraph) -> dict:
    """
    Return a summary dict of graph statistics.

    Includes node count, edge count, total length, blocked edge count, and
    edges with known vs unknown risk.
    """
    total_length = 0.0
    blocked_count = 0
    known_risk_count = 0
    unknown_risk_count = 0

    for _, _, data in G.edges(data=True):
        total_length += data.get("length_m", 0.0)
        if data.get("blocked", False):
            blocked_count += 1
        if data.get("risk_score") is not None:
            known_risk_count += 1
        else:
            unknown_risk_count += 1

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "total_length_m": round(total_length, 2),
        "blocked_edges": blocked_count,
        "edges_with_risk": known_risk_count,
        "edges_without_risk": unknown_risk_count,
        "crs": G.graph.get("crs", "unknown"),
        "source": (
            G.graph.get("_aei_meta").source
            if "_aei_meta" in G.graph else "unknown"
        ),
    }


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def edge_length_m(G: nx.MultiDiGraph, u: Any, v: Any, key: int = 0) -> float:
    """
    Return the stored length_m of a specific edge.

    Parameters
    ----------
    u, v : node ids
    key : parallel-edge key (default 0)
    """
    return G[u][v][key]["length_m"]


def node_distance_m(G: nx.MultiDiGraph, n1: Any, n2: Any) -> float:
    """
    Compute straight-line haversine distance between two nodes (metres).
    """
    return _haversine_m(
        G.nodes[n1]["y"], G.nodes[n1]["x"],
        G.nodes[n2]["y"], G.nodes[n2]["x"],
    )


def nearest_node(G: nx.MultiDiGraph, lat: float, lon: float) -> Any:
    """
    Return the node id nearest to (lat, lon) by haversine distance.

    Parameters
    ----------
    G : road-network graph
    lat : float — latitude (degrees)
    lon : float — longitude (degrees)

    Returns
    -------
    node id
    """
    best_id = None
    best_dist = float("inf")
    for n, data in G.nodes(data=True):
        d = _haversine_m(lat, lon, data["y"], data["x"])
        if d < best_dist:
            best_dist = d
            best_id = n
    return best_id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compute the haversine great-circle distance in metres between two
    (latitude, longitude) pairs.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _is_finite_number(v: Any) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _default_edge_attrs(
    length_m: float,
    road_type: str,
    extra: Optional[Dict] = None,
) -> Dict:
    attrs = {
        "length_m": float(length_m),
        "road_type": road_type,
        "blocked": False,
        "risk_score": None,
        "zone_id": None,
    }
    if extra:
        attrs.update(extra)
    return attrs


def _normalise_osm_graph(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Attach AEI-standard attributes to an osmnx-loaded graph.

    osmnx already provides ``length`` (metres) and ``highway`` on edges.
    This function renames them to AEI conventions and adds the missing
    ``blocked``, ``risk_score``, and ``zone_id`` attributes.
    """
    for u, v, k, data in G.edges(data=True, keys=True):
        # Length: osmnx stores it as 'length' (metres)
        length_m = data.get("length", None)
        if length_m is None or not _is_finite_number(length_m) or float(length_m) <= 0:
            # Fall back to haversine from node coordinates
            try:
                length_m = _haversine_m(
                    G.nodes[u].get("y", 0), G.nodes[u].get("x", 0),
                    G.nodes[v].get("y", 0), G.nodes[v].get("x", 0),
                )
            except Exception:
                length_m = 1.0  # degenerate fallback; logged below
            logger.debug("Edge (%s→%s) length fallback to haversine: %.2f m", u, v, length_m)

        G[u][v][k]["length_m"] = float(length_m)

        # Road type from OSM highway tag
        hw = data.get("highway", "unclassified")
        G[u][v][k]["road_type"] = hw if isinstance(hw, str) else (
            hw[0] if isinstance(hw, list) and hw else "unclassified"
        )

        # AEI-specific fields (not present in raw osmnx graph)
        if "blocked" not in G[u][v][k]:
            G[u][v][k]["blocked"] = False
        if "risk_score" not in G[u][v][k]:
            G[u][v][k]["risk_score"] = None
        if "zone_id" not in G[u][v][k]:
            G[u][v][k]["zone_id"] = None

    return G
