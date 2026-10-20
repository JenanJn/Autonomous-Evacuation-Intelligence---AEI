"""
AEI — API: Pydantic Request / Response Models
================================================
Every model here is a direct mirror of the TypeScript types defined in
``mobile/src/types/api.ts``.  Field names, types, and enum values MUST
stay in sync with that file.

Naming convention
-----------------
*Request*  models are used as FastAPI body parameters (POST bodies).
*Response* models are returned by endpoint functions.

Serialisation rules
-------------------
* All enums are emitted as their string value (not the Python object).
  Pydantic v2 does this automatically when ``model_config`` includes
  ``use_enum_values = True``, which all response models set.
* ``RouteResult.edges`` stores Python tuples ``(u, v, key)`` internally
  but the mobile contract expects JSON arrays ``[u, v, key]``.  The
  ``_serialise_edges`` validator converts them.
* ``None`` fields are included in JSON output so the mobile app does not
  need null-coalescence for missing keys.

CONTRACT_VERSION
----------------
All response models carry ``contract_version = "0.1.0"`` matching
``integration/schemas.py::CONTRACT_VERSION``.  Bump together.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

API_VERSION = "0.1.0"
CONTRACT_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Enumerations  (string literals matching api.ts)
# ---------------------------------------------------------------------------

# These are plain string constants rather than Python Enum objects so they
# serialise transparently in Pydantic v2 JSON mode.

PredictionStatus = str   # 'OK'|'NO_DATA'|'STALE_DATA'|'MODEL_ERROR'|'INVALID_INPUT'
RiskStatus       = str   # 'OK'|'NO_DATA'|'STALE_DATA'|'SCORING_ERROR'|'INVALID_INPUT'
RiskCategory     = str   # 'LOW'|'MODERATE'|'HIGH'|'CRITICAL'|'UNKNOWN'
RoutingMode      = str   # 'shortest'|'risk_aware'|'adaptive'
ShelterStatus    = str   # 'OPEN'|'FULL'|'CLOSED'


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class PlanRequest(BaseModel):
    """
    Body for POST /plan.

    The mobile app sends all three fields; ``node_id`` may be omitted
    when the caller wants the server to resolve GPS → nearest node.

    Validation
    ----------
    * ``lat`` must be in [-90, 90].
    * ``lon`` must be in [-180, 180].
    * At least one of ``lat``/``lon`` or ``node_id`` must be present
      (enforced in plan_builder, not here, to allow flexible fallback).
    """
    lat: float = Field(..., ge=-90.0, le=90.0,
                       description="Latitude in WGS-84 degrees.")
    lon: float = Field(..., ge=-180.0, le=180.0,
                       description="Longitude in WGS-84 degrees.")
    node_id: Optional[str] = Field(
        None,
        description="Pre-resolved nearest road-node id.  "
                    "When absent the server resolves lat/lon → nearest node.",
    )


class ReplanRequest(BaseModel):
    """
    Body for POST /plan/replan.

    ``block_edges`` is a list of ``[u, v]`` pairs identifying directed
    edges to block.  The mobile client sends ``[['A','B'],['B','A']]``
    to block both directions of a segment.

    Validation
    ----------
    * ``block_edges`` must not be empty.
    * Each element must be a two-element list of non-empty strings.
    """
    scenario_id: str = Field(..., min_length=1,
                             description="Scenario id from the current plan.")
    block_edges: List[List[str]] = Field(
        ...,
        description="Directed edges to block.  Each element is [u, v].",
    )

    @field_validator("block_edges")
    @classmethod
    def validate_block_edges(cls, v: List[List[str]]) -> List[List[str]]:
        if not v:
            raise ValueError("block_edges must not be empty.")
        for i, edge in enumerate(v):
            if not isinstance(edge, list) or len(edge) != 2:
                raise ValueError(
                    f"block_edges[{i}] must be a two-element list [u, v], "
                    f"got {edge!r}."
                )
            u, w = edge
            if not isinstance(u, str) or not u.strip():
                raise ValueError(
                    f"block_edges[{i}][0] must be a non-empty string, got {u!r}."
                )
            if not isinstance(w, str) or not w.strip():
                raise ValueError(
                    f"block_edges[{i}][1] must be a non-empty string, got {w!r}."
                )
        return v


# ---------------------------------------------------------------------------
# Response sub-models
# ---------------------------------------------------------------------------

class RouteNodeResponse(BaseModel):
    """Single road-network node (id + WGS-84 coordinates)."""
    id: str
    x: float   # longitude
    y: float   # latitude


class RouteResultResponse(BaseModel):
    """
    Mirrors ``RouteResult`` in api.ts exactly.

    ``edges`` is serialised as a list of ``[u, v, key]`` JSON arrays,
    matching the TypeScript type ``[string, string, number][]``.
    """
    feasible: bool
    path: List[str]
    edges: List[List[Any]]          # [[u, v, key], ...]  — JSON arrays
    total_length_m: float
    total_cost: float
    total_risk_penalty_m: float
    estimated_travel_time_s: float
    mode: str                       # routing mode string value
    origin: str
    destination: str
    replanned: bool
    notes: List[str]

    model_config = {"populate_by_name": True}


class RiskOutputRecordResponse(BaseModel):
    """
    Mirrors ``RiskOutputRecord`` in api.ts.

    ``scoring_method`` is an optional extension field that the mobile app
    accepts (typed ``string | undefined``).
    """
    zone_id: str
    risk_score: Optional[float]
    risk_category: str
    data_freshness: Optional[str]
    risk_status: str
    contributing_factors: List[str]
    contract_version: str
    scoring_method: Optional[str] = None   # forwarded from ScoredRiskRecord


class ShelterResponse(BaseModel):
    """Mirrors ``Shelter`` in api.ts."""
    shelter_id: str
    name: str
    lat: float
    lon: float
    capacity: int
    occupied: int
    remaining_capacity: int
    status: str
    nearest_node: Optional[str]
    data_source: str
    notes: str


class ShelterAssignmentResponse(BaseModel):
    """Mirrors ``ShelterAssignment`` in api.ts."""
    demand_id: str
    shelter_id: str
    admitted: int
    requested: int
    route_cost_m: float


class UnassignedDemandResponse(BaseModel):
    """One unassigned demand unit (part of ``AllocationResult``)."""
    demand_id: str
    requested: int
    reason: str


class AllocationResultResponse(BaseModel):
    """Mirrors ``AllocationResult`` in api.ts."""
    assignments: List[ShelterAssignmentResponse]
    unassigned: List[UnassignedDemandResponse]
    total_admitted: int
    total_requested: int
    total_unassigned: int
    notes: List[str]


class EvacuationPlanResponse(BaseModel):
    """
    Top-level response for POST /plan, POST /plan/replan,
    and POST /plan/replan/clear.

    Mirrors ``EvacuationPlan`` in api.ts exactly.

    Synthetic-data disclaimer
    --------------------------
    When ``is_simulated=True`` the plan is built from a synthetic in-memory
    graph and must never be used to guide a real emergency.  The
    ``warnings`` list will always contain at least one SIMULATED notice.
    """
    scenario_id: str
    generated_at: str           # ISO-8601 UTC
    is_simulated: bool
    blockage_active: bool
    origin_node: str
    origin_label: str
    zone_risks: List[RiskOutputRecordResponse]
    primary_route: RouteResultResponse
    replanned_route: Optional[RouteResultResponse]
    shelters: List[ShelterResponse]
    allocation: AllocationResultResponse
    warnings: List[str]
    contract_version: str


# ---------------------------------------------------------------------------
# Health response
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """
    Mirrors ``ApiHealth`` in api.ts.

    ``status`` is ``'ok'`` when the server is healthy, ``'error'``
    otherwise.  The mobile app uses this to toggle the connectivity badge.
    """
    status: str          # 'ok' | 'error'
    version: str         # API version string
    backend_url: str     # echoed back so the mobile app can display it
