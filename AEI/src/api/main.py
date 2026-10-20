"""
AEI — FastAPI Application
===========================
Thin HTTP layer over ``api.plan_builder``.  No domain logic lives here;
all computation is delegated to ``plan_builder``.

Endpoints
---------
GET  /health             liveness probe
POST /plan               compute a full evacuation plan for a GPS location
POST /plan/replan        apply a road blockage and replan
POST /plan/replan/clear  clear all blockages, restore baseline

Run with uvicorn
----------------
From the ``AEI/`` project root (the directory that contains ``src/``):

    uvicorn api.main:app --reload --port 8000

or via the helper script:

    python -m api.main

State model
-----------
A single ``DemoState`` is created at startup (``lifespan``).
All requests from all clients share it.  See ``plan_builder.py`` for the
single-user-demo limitation notice.

Error responses
---------------
HTTP 422  Pydantic validation failure (bad request body).
HTTP 422  Invalid node id, unknown blockage-edge nodes.
HTTP 409  /plan/replan called without a prior /plan (no active scenario).
HTTP 500  Unexpected internal error (logged, never swallowed).
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Ensure ``src/`` is on sys.path when the file is run directly or when
# uvicorn is launched from the project root without pip-installing the
# package.  ``pytest`` inserts ``src/`` via conftest.py; this guard makes
# the server runnable without additional PYTHONPATH configuration.
# ---------------------------------------------------------------------------
_SRC = Path(__file__).resolve().parents[2]   # …/AEI/src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from api.models import (
    EvacuationPlanResponse,
    HealthResponse,
    PlanRequest,
    ReplanRequest,
    API_VERSION,
)
from api.plan_builder import DemoState, build_clear, build_plan, build_replan

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialise shared state at startup; clean up at shutdown.

    ``DemoState.__init__`` builds the synthetic graph, constructs the
    router, snaps shelters to the network, and caches the baseline primary
    route.  This takes < 50 ms and happens once.
    """
    logger.info("AEI startup: initialising demo state …")
    app.state.demo = DemoState()
    logger.info(
        "AEI startup complete.  Primary demo route: %s",
        app.state.demo.primary_route.path,
    )
    yield
    logger.info("AEI shutdown.")


app = FastAPI(
    title="AEI Evacuation Intelligence API",
    description=(
        "Synthetic demo backend for the AEI mobile evacuation-planning app.\n\n"
        "**All data is SYNTHETIC.** Routes and risk scores are NOT safe for real emergencies."
    ),
    version=API_VERSION,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    tags=["health"],
)
def health(request: Request) -> HealthResponse:
    """
    Returns HTTP 200 with ``status='ok'`` when the server is running.

    The mobile ``checkHealth()`` function calls this endpoint to decide
    whether to show the 'connected' or 'disconnected' badge.
    ``backend_url`` echoes back the URL the server believes it is
    reachable at (base URL from the incoming request).
    """
    base_url = str(request.base_url).rstrip("/")
    return HealthResponse(
        status="ok",
        version=API_VERSION,
        backend_url=base_url,
    )


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

@app.post(
    "/plan",
    response_model=EvacuationPlanResponse,
    summary="Compute evacuation plan",
    tags=["plan"],
    status_code=status.HTTP_200_OK,
)
def plan(body: PlanRequest, request: Request) -> EvacuationPlanResponse:
    """
    Compute a full evacuation plan for the supplied GPS location.

    Steps performed server-side
    ---------------------------
    1. Snap (lat, lon) → nearest road-network node (or use ``node_id``
       directly if supplied and present in the graph).
    2. Compute a risk-aware route to the primary shelter node.
    3. Run greedy shelter allocation for the demo demand units.
    4. Return a fully-populated ``EvacuationPlan`` response.

    This endpoint also **resets** any active blockage so that calling
    ``/plan`` always returns a clean baseline — matching the mobile
    ``getEvacuationPlan()`` contract.

    Synthetic-data warning
    ----------------------
    ``is_simulated`` is always ``true`` and the ``warnings`` list always
    contains a SIMULATED notice.  Do not present these routes as safe.
    """
    demo: DemoState = request.app.state.demo
    try:
        return build_plan(demo, body.lat, body.lon, body.node_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in /plan")
        raise HTTPException(status_code=500, detail="Internal server error.") from exc


# ---------------------------------------------------------------------------
# Replan
# ---------------------------------------------------------------------------

@app.post(
    "/plan/replan",
    response_model=EvacuationPlanResponse,
    summary="Simulate road blockage and replan",
    tags=["plan"],
    status_code=status.HTTP_200_OK,
)
def replan(body: ReplanRequest, request: Request) -> EvacuationPlanResponse:
    """
    Block the specified edges and return a replanned evacuation plan.

    The mobile client sends:
    ``{"scenario_id": "DEMO_SYNTHETIC_001", "block_edges": [["A","B"],["B","A"]]}``

    The response includes:
    * ``primary_route``   — the original unblocked route (for comparison)
    * ``replanned_route`` — the new route avoiding the blocked edges
    * ``blockage_active`` — ``true``

    If no alternative route exists the replanned route carries
    ``feasible=false`` with an explanatory note; the endpoint still
    returns HTTP 200 so the mobile app can display the infeasibility
    clearly rather than treating it as a network error.

    Validation errors (unknown nodes, empty edge list) return HTTP 422.
    """
    demo: DemoState = request.app.state.demo
    try:
        return build_replan(demo, body.block_edges)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in /plan/replan")
        raise HTTPException(status_code=500, detail="Internal server error.") from exc


# ---------------------------------------------------------------------------
# Clear blockage
# ---------------------------------------------------------------------------

@app.post(
    "/plan/replan/clear",
    response_model=EvacuationPlanResponse,
    summary="Clear road blockage, restore baseline",
    tags=["plan"],
    status_code=status.HTTP_200_OK,
)
def clear(request: Request) -> EvacuationPlanResponse:
    """
    Remove all active road blockages and return the restored baseline plan.

    This is equivalent to calling ``/plan`` with the default demo origin,
    but it does not require the caller to supply coordinates — matching
    the mobile ``clearBlockage()`` contract which sends an empty POST body.

    After this call:
    * ``blockage_active`` is ``false``
    * ``replanned_route`` is ``null``
    * The shared router's working graph is fully restored
    """
    demo: DemoState = request.app.state.demo
    try:
        return build_clear(demo)
    except Exception as exc:
        logger.exception("Unexpected error in /plan/replan/clear")
        raise HTTPException(status_code=500, detail="Internal server error.") from exc


# ---------------------------------------------------------------------------
# Module entry-point (python -m api.main)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
