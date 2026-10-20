"""
Live HTTP smoke-test against the running AEI FastAPI server.

Run AFTER starting the server:
    uvicorn api.main:app --port 8000

Then:
    python scripts/smoke_test_live.py
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"

PASS = "OK"
FAIL = "FAIL"

results = []


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return r.status, json.loads(r.read())


def post(path, body=None):
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read())


def check(label, got, expected):
    ok = got == expected
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {label}: got={got!r}")
    results.append(ok)
    return ok


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
print()
print("=== GET /health ===")
_, h = get("/health")
check("status == 'ok'", h["status"], "ok")
check("version == '0.1.0'", h["version"], "0.1.0")
check("backend_url present", "backend_url" in h, True)
check("backend_url is string", isinstance(h["backend_url"], str), True)

# ---------------------------------------------------------------------------
# POST /plan  — GPS origin
# ---------------------------------------------------------------------------
print()
print("=== POST /plan  (GPS origin, lat=0 lon=0) ===")
st, p = post("/plan", {"lat": 0.0, "lon": 0.0})
check("HTTP 200", st, 200)
check("scenario_id", p["scenario_id"], "DEMO_SYNTHETIC_001")
check("is_simulated=True", p["is_simulated"], True)
check("blockage_active=False", p["blockage_active"], False)
check("origin_node=A", p["origin_node"], "A")
check("primary_route.feasible=True", p["primary_route"]["feasible"], True)
check("primary_route.path", p["primary_route"]["path"], ["A", "B", "C"])
check("mode string", p["primary_route"]["mode"], "risk_aware")
check("replanned_route=null", p["replanned_route"], None)
check("zone_risks count=6", len(p["zone_risks"]), 6)
check("scoring_method present", p["zone_risks"][0].get("scoring_method"),
      "direct_proxy_uncalibrated")
check("shelters count=2", len(p["shelters"]), 2)
check("admitted>0", p["allocation"]["total_admitted"] > 0, True)
check("unassigned=0", p["allocation"]["total_unassigned"], 0)
check("contract_version", p["contract_version"], "0.1.0")
# edges are [[u, v, key], ...]
edges_ok = all(isinstance(e, list) and len(e) == 3
               for e in p["primary_route"]["edges"])
check("edges are [u,v,key] lists", edges_ok, True)
# SIMULATED in warnings
simulated_in_warnings = any(
    "SYNTHETIC" in w.upper() or "SIMULATED" in w.upper()
    for w in p["warnings"]
)
check("SIMULATED/SYNTHETIC in warnings", simulated_in_warnings, True)

# ---------------------------------------------------------------------------
# POST /plan  — explicit node_id
# ---------------------------------------------------------------------------
print()
print("=== POST /plan  (explicit node_id=B) ===")
st, pb = post("/plan", {"lat": 0.0, "lon": 0.009, "node_id": "B"})
check("HTTP 200", st, 200)
check("origin_node=B", pb["origin_node"], "B")
check("route feasible", pb["primary_route"]["feasible"], True)

# ---------------------------------------------------------------------------
# POST /plan  — unknown node_id falls back to GPS snap
# ---------------------------------------------------------------------------
print()
print("=== POST /plan  (unknown node_id -> GPS fallback) ===")
st, pu = post("/plan", {"lat": 0.0, "lon": 0.0, "node_id": "NOTANODE"})
check("HTTP 200", st, 200)
check("origin_node snapped to A", pu["origin_node"], "A")

# ---------------------------------------------------------------------------
# POST /plan  — bad coordinates → 422
# ---------------------------------------------------------------------------
print()
print("=== POST /plan  (invalid coordinates -> 422) ===")
try:
    post("/plan", {"lat": 999.0, "lon": 0.0})
    check("422 for lat=999", False, True)
except urllib.error.HTTPError as e:
    check("422 for lat=999", e.code, 422)

try:
    post("/plan", {"lat": 0.0, "lon": 999.0})
    check("422 for lon=999", False, True)
except urllib.error.HTTPError as e:
    check("422 for lon=999", e.code, 422)

# ---------------------------------------------------------------------------
# POST /plan/replan  — normal blockage
# ---------------------------------------------------------------------------
print()
print("=== POST /plan/replan  (block A-B) ===")
post("/plan", {"lat": 0.0, "lon": 0.0})   # reset to clean state
st, rp = post("/plan/replan", {
    "scenario_id": "DEMO_SYNTHETIC_001",
    "block_edges": [["A", "B"], ["B", "A"]],
})
check("HTTP 200", st, 200)
check("blockage_active=True", rp["blockage_active"], True)
check("replanned_route not null", rp["replanned_route"] is not None, True)
check("replanned feasible", rp["replanned_route"]["feasible"], True)
check("replanned.replanned=True", rp["replanned_route"]["replanned"], True)
path = rp["replanned_route"]["path"]
no_AB = all(
    (path[i], path[i + 1]) not in {("A", "B"), ("B", "A")}
    for i in range(len(path) - 1)
)
check("path avoids A-B", no_AB, True)
check("replanned longer", (rp["replanned_route"]["total_length_m"]
                           > rp["primary_route"]["total_length_m"]), True)
check("primary path preserved", rp["primary_route"]["path"], ["A", "B", "C"])
# replanned edges are lists
rep_edges_ok = all(isinstance(e, list) and len(e) == 3
                   for e in rp["replanned_route"]["edges"])
check("replanned edges are [u,v,key]", rep_edges_ok, True)
blockage_in_warnings = any("block" in w.lower() for w in rp["warnings"])
check("blockage warning present", blockage_in_warnings, True)

# ---------------------------------------------------------------------------
# POST /plan/replan  — all exits blocked → infeasible route, still HTTP 200
# ---------------------------------------------------------------------------
print()
print("=== POST /plan/replan  (all exits blocked -> infeasible HTTP 200) ===")
post("/plan", {"lat": 0.0, "lon": 0.0})
st, inf = post("/plan/replan", {
    "scenario_id": "DEMO_SYNTHETIC_001",
    "block_edges": [["A", "B"], ["B", "A"], ["A", "D"], ["D", "A"]],
})
check("HTTP 200 even when infeasible", st, 200)
check("blockage_active=True", inf["blockage_active"], True)
check("replanned_route present", inf["replanned_route"] is not None, True)
check("replanned_route.feasible=False", inf["replanned_route"]["feasible"], False)

# ---------------------------------------------------------------------------
# POST /plan/replan  — invalid nodes → 422
# ---------------------------------------------------------------------------
print()
print("=== POST /plan/replan  (invalid node -> 422) ===")
post("/plan", {"lat": 0.0, "lon": 0.0})
try:
    post("/plan/replan", {
        "scenario_id": "DEMO_SYNTHETIC_001",
        "block_edges": [["X", "Y"]],
    })
    check("422 for unknown node", False, True)
except urllib.error.HTTPError as e:
    check("422 for unknown node", e.code, 422)

try:
    post("/plan/replan", {
        "scenario_id": "DEMO_SYNTHETIC_001",
        "block_edges": [],
    })
    check("422 for empty block_edges", False, True)
except urllib.error.HTTPError as e:
    check("422 for empty block_edges", e.code, 422)

# ---------------------------------------------------------------------------
# POST /plan/replan/clear
# ---------------------------------------------------------------------------
print()
print("=== POST /plan/replan/clear ===")
post("/plan", {"lat": 0.0, "lon": 0.0})
post("/plan/replan", {
    "scenario_id": "DEMO_SYNTHETIC_001",
    "block_edges": [["A", "B"], ["B", "A"]],
})
st, cl = post("/plan/replan/clear")
check("HTTP 200", st, 200)
check("blockage_active=False", cl["blockage_active"], False)
check("replanned_route=null", cl["replanned_route"], None)
check("primary path restored", cl["primary_route"]["path"], ["A", "B", "C"])
check("route feasible", cl["primary_route"]["feasible"], True)

# clear without prior blockage is idempotent
st2, cl2 = post("/plan/replan/clear")
check("clear idempotent HTTP 200", st2, 200)
check("still no blockage", cl2["blockage_active"], False)

# subsequent /plan still works
st3, p3 = post("/plan", {"lat": 0.0, "lon": 0.0})
check("plan after clear HTTP 200", st3, 200)
check("plan after clear not blocked", p3["blockage_active"], False)

# ---------------------------------------------------------------------------
# Determinism: two clean plan+replan cycles give the same path
# ---------------------------------------------------------------------------
print()
print("=== Determinism check ===")

def _cycle():
    post("/plan", {"lat": 0.0, "lon": 0.0})
    _, r = post("/plan/replan", {
        "scenario_id": "DEMO_SYNTHETIC_001",
        "block_edges": [["A", "B"], ["B", "A"]],
    })
    return r["replanned_route"]["path"]

path1 = _cycle()
path2 = _cycle()
check("replanned path deterministic", path1, path2)

# ---------------------------------------------------------------------------
# OpenAPI docs
# ---------------------------------------------------------------------------
print()
print("=== /docs ===")
status, _ = get("/openapi.json")
check("/openapi.json HTTP 200", status, 200)
with urllib.request.urlopen(BASE + "/docs", timeout=5) as r:
    check("/docs HTTP 200", r.status, 200)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
passed = sum(results)
total = len(results)
print()
print(f"{'='*60}")
print(f"SMOKE TEST RESULT: {passed}/{total} checks passed")
if passed == total:
    print("ALL SMOKE TESTS PASSED")
else:
    failed = total - passed
    print(f"{failed} CHECK(S) FAILED")
print(f"{'='*60}")

sys.exit(0 if passed == total else 1)
