# AEI — FastAPI Integration Layer

**Version:** 0.1.0 · **Contract:** `integration/schemas.py::CONTRACT_VERSION = "0.1.0"`

> ⚠ All data served by this API is **SYNTHETIC**. The road network, risk
> scores, and shelter locations are made-up demo data. This server must
> **NOT** be used to guide real emergency evacuations.

---

## Prerequisites

Python 3.11+ with all dependencies installed:

```
pip install -r requirements.txt
```

Key new dependencies (added to `requirements.txt`):

| Package | Version | Purpose |
|---|---|---|
| fastapi | 0.111.0 | Web framework |
| uvicorn[standard] | 0.30.1 | ASGI server |
| httpx | 0.27.0 | HTTP client (TestClient) |

---

## Running the server

All commands are run from the **project root** — the directory that
contains the `src/` folder (`AEI/`).

### Option 1 — uvicorn directly (recommended for development)

```bash
cd path/to/AEI
uvicorn api.main:app --reload --port 8000
```

`--reload` restarts the server automatically when source files change.

### Option 2 — Python module entry point

```bash
cd path/to/AEI/src
python -m api.main
```

### Option 3 — uvicorn with explicit app root

If you prefer to run from the `src/` directory:

```bash
cd path/to/AEI/src
uvicorn api.main:app --reload --port 8000
```

### Verify the server is running

```
GET http://localhost:8000/health
→ {"status":"ok","version":"0.1.0","backend_url":"http://127.0.0.1:8000"}
```

### OpenAPI interactive docs

```
http://localhost:8000/docs
```

---

## Mobile app configuration

In the mobile app root (`mobile/`), copy `.env.example` to `.env` and
set the backend URL to the IP address your phone/emulator can reach:

```
# mobile/.env
EXPO_PUBLIC_BACKEND_URL=http://192.168.1.100:8000
```

Replace `192.168.1.100` with the local IP of the machine running the
server.  Use `http://10.0.2.2:8000` for Android emulator on the same
machine.  Leave the variable **empty** to use the mobile app's built-in
demo mode (no server needed).

The mobile `apiClient.ts` calls these endpoints:

| Method | Path | Function |
|---|---|---|
| GET | `/health` | `checkHealth()` |
| POST | `/plan` | `getEvacuationPlan()` |
| POST | `/plan/replan` | `simulateBlockage()` |
| POST | `/plan/replan/clear` | `clearBlockage()` |

---

## Endpoint reference

### `GET /health`

Liveness probe. Returns HTTP 200 when the server is running.

**Response**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "backend_url": "http://127.0.0.1:8000"
}
```

---

### `POST /plan`

Compute a full evacuation plan for the supplied GPS location.

Calling `/plan` always resets any active blockage — it returns a clean
baseline regardless of prior `/plan/replan` calls.

**Request body**
```json
{
  "lat": 0.0,
  "lon": 0.0,
  "node_id": "A"
}
```

`node_id` is optional. When omitted (or when the value is not in the
graph) the server snaps `(lat, lon)` to the nearest road-network node.

**Response** — `EvacuationPlan` (see `mobile/src/types/api.ts`)

```json
{
  "scenario_id": "DEMO_SYNTHETIC_001",
  "generated_at": "2024-06-01T12:00:00Z",
  "is_simulated": true,
  "blockage_active": false,
  "origin_node": "A",
  "origin_label": "GPS (0.00000, 0.00000) → node A [SYNTHETIC]",
  "zone_risks": [ ... ],
  "primary_route": { "feasible": true, "path": ["A","B","C"], "edges": [["A","B",0],["B","C",0]], ... },
  "replanned_route": null,
  "shelters": [ ... ],
  "allocation": { ... },
  "warnings": ["SIMULATED DATA — ..."],
  "contract_version": "0.1.0"
}
```

**Errors**
- `422` — `lat` outside `[-90, 90]` or `lon` outside `[-180, 180]`

---

### `POST /plan/replan`

Simulate a road blockage and return a replanned evacuation plan.

**Request body**
```json
{
  "scenario_id": "DEMO_SYNTHETIC_001",
  "block_edges": [["A","B"],["B","A"]]
}
```

`block_edges` is a list of directed `[u, v]` pairs. The mobile client
sends both directions to block a bidirectional segment.

**Response** — same `EvacuationPlan` shape with:
- `blockage_active: true`
- `primary_route` — original unblocked route (for comparison)
- `replanned_route` — new route avoiding blocked edges; `feasible: false`
  if no alternative path exists (still HTTP 200)

**Errors**
- `422` — `block_edges` is empty, malformed, or references node IDs not
  present in the road-network graph

---

### `POST /plan/replan/clear`

Remove all active blockages and restore the baseline plan.

**Request body** — none (empty POST)

**Response** — same `EvacuationPlan` shape with:
- `blockage_active: false`
- `replanned_route: null`
- `primary_route` restored to the original unblocked route

---

## Running tests

From the project root (`AEI/`):

```bash
# Full suite (641 tests)
pytest

# New API tests only
pytest tests/test_api.py tests/test_plan_builder.py -v

# With coverage
pytest --cov=src --cov-report=term-missing
```

### Live smoke-test (server must be running)

```bash
python scripts/smoke_test_live.py
```

Expected output: `SMOKE TEST RESULT: 56/56 checks passed`

---

## Architecture

```
src/api/
├── __init__.py      — package docstring
├── models.py        — Pydantic request/response models (mirrors api.ts)
├── plan_builder.py  — domain logic: DemoState, build_plan/replan/clear
└── main.py          — FastAPI app, 4 endpoints, lifespan startup

tests/
├── test_api.py          — 79 endpoint tests (TestClient)
└── test_plan_builder.py — 81 builder unit tests
```

**`plan_builder.py`** owns all computation:
1. Builds the synthetic 6-node `A-F` graph with risk scores at startup
2. `DemoState` holds a `EvacuationRouter` + `ShelterManager` instance
3. `build_plan()` resets state, snaps GPS → node, routes, allocates
4. `build_replan()` applies blockages and replans
5. `build_clear()` calls `state.reset()` and rebuilds the baseline plan

**`main.py`** is a thin HTTP wrapper — no domain logic.

---

## Single-session limitation

All HTTP clients share one `DemoState` instance. Concurrent calls from
multiple mobile clients will interfere (last writer wins). This is
intentional for a single-user demo.

**Production fix:** key `DemoState` objects by session token (e.g. a
UUID in a request header) and store them in a per-session dict.

---

## Synthetic-data disclaimers

- `is_simulated: true` on every response
- Every `warnings` list contains at least one `"SIMULATED DATA"` entry
- Shelter locations are invented; `data_source: "SYNTHETIC"` on all of them
- Risk scores are fixed proxy values, **not** calibrated flood probabilities
- Travel times use a fixed speed table, **not** validated for any real network
- The road graph has 6 nodes — not suitable for any real city
