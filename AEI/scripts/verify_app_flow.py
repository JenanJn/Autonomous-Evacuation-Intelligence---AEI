"""
Simulate exactly what the running mobile app does:
  - Reads BACKEND_URL from the inlined value
  - Calls getConnectivityStatus() (GET /health)
  - Calls getEvacuationPlan()    (POST /plan with {lat,lon,node_id})
  - Calls simulateBlockage()     (POST /plan/replan with {scenario_id, block_edges})
  - Calls clearBlockage()        (POST /plan/replan/clear)

Uses the SAME URL the bundle has inlined: http://192.168.1.6:8000
This is a true end-to-end test of the API contract — not a unit test.
"""
import json
import sys
import urllib.error
import urllib.request

# Value taken DIRECTLY from the bundle (verified via verify_env_inline.py)
BACKEND_URL = "http://192.168.1.6:8000"
TIMEOUT = 6


def get(path):
    with urllib.request.urlopen(f"{BACKEND_URL}{path}", timeout=TIMEOUT) as r:
        return r.status, json.loads(r.read())


def post(path, body=None):
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        f"{BACKEND_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, json.loads(r.read())


print(f"BACKEND_URL = {BACKEND_URL!r}")
print(f"(this is the exact value inlined into the Expo bundle)")
print()

# ---- 1. checkHealth / getConnectivityStatus ----
print("[1/4] getConnectivityStatus  ->  GET /health")
try:
    code, body = get("/health")
    status = body["status"]
    connectivity = "connected" if status == "ok" else "disconnected"
    print(f"  HTTP {code}  status={status!r}  version={body['version']!r}")
    print(f"  -> ConnectivityBadge would show: {connectivity!r}")
    connectivity_ok = connectivity == "connected"
except Exception as e:
    print(f"  FAIL: {e}")
    connectivity_ok = False
print()

# ---- 2. getEvacuationPlan (GPS mode, demoMode=false) ----
print("[2/4] getEvacuationPlan (GPS, demoMode=false)  ->  POST /plan")
try:
    # Simulate GPS at (0,0) — the synthetic graph's node A
    code, plan = post("/plan", {"lat": 0.0, "lon": 0.0, "node_id": ""})
    print(f"  HTTP {code}")
    print(f"  scenario_id       = {plan['scenario_id']!r}")
    print(f"  is_simulated      = {plan['is_simulated']}   (must be true; data is synthetic)")
    print(f"  blockage_active   = {plan['blockage_active']}")
    print(f"  origin_node       = {plan['origin_node']!r}")
    print(f"  primary_route     = {plan['primary_route']['path']}")
    print(f"  route feasible    = {plan['primary_route']['feasible']}")
    print(f"  route edges       = {plan['primary_route']['edges']}")
    print(f"  zone_risks count  = {len(plan['zone_risks'])}")
    print(f"  shelters count    = {len(plan['shelters'])}")
    print(f"  admitted          = {plan['allocation']['total_admitted']}")
    print(f"  warnings[0]        = {plan['warnings'][0][:60]!r}")
    plan_ok = (code == 200
               and plan["scenario_id"] == "DEMO_SYNTHETIC_001"
               and plan["is_simulated"] is True
               and plan["primary_route"]["feasible"] is True
               and plan["primary_route"]["path"] == ["A", "B", "C"])
except Exception as e:
    print(f"  FAIL: {e}")
    plan_ok = False
print()

# ---- 3. simulateBlockage ----
print("[3/4] simulateBlockage  ->  POST /plan/replan")
try:
    code, plan = post("/plan/replan", {
        "scenario_id": "DEMO_SYNTHETIC_001",
        "block_edges": [["A", "B"], ["B", "A"]],
    })
    print(f"  HTTP {code}")
    print(f"  blockage_active   = {plan['blockage_active']}")
    print(f"  primary_route     = {plan['primary_route']['path']}  (unchanged)")
    print(f"  replanned_route   = {plan['replanned_route']['path'] if plan['replanned_route'] else None}")
    print(f"  replanned.feasible= {plan['replanned_route']['feasible']}")
    print(f"  replanned.replanned={plan['replanned_route']['replanned']}")
    replan_ok = (code == 200
                 and plan["blockage_active"] is True
                 and plan["replanned_route"] is not None
                 and plan["replanned_route"]["feasible"] is True
                 and ("A", "B") not in [
                     (plan["replanned_route"]["path"][i],
                      plan["replanned_route"]["path"][i + 1])
                     for i in range(len(plan["replanned_route"]["path"]) - 1)
                 ])
except Exception as e:
    print(f"  FAIL: {e}")
    replan_ok = False
print()

# ---- 4. clearBlockage ----
print("[4/4] clearBlockage  ->  POST /plan/replan/clear")
try:
    code, plan = post("/plan/replan/clear")
    print(f"  HTTP {code}")
    print(f"  blockage_active   = {plan['blockage_active']}")
    print(f"  replanned_route   = {plan['replanned_route']}")
    print(f"  primary_route     = {plan['primary_route']['path']}  (restored)")
    clear_ok = (code == 200
                and plan["blockage_active"] is False
                and plan["replanned_route"] is None
                and plan["primary_route"]["path"] == ["A", "B", "C"])
except Exception as e:
    print(f"  FAIL: {e}")
    clear_ok = False
print()

# ---- Verdict ----
all_ok = connectivity_ok and plan_ok and replan_ok and clear_ok
print("=" * 60)
print(f"connectivity:  {'PASS' if connectivity_ok else 'FAIL'}")
print(f"plan:          {'PASS' if plan_ok else 'FAIL'}")
print(f"replan:        {'PASS' if replan_ok else 'FAIL'}")
print(f"clear:         {'PASS' if clear_ok else 'FAIL'}")
print("=" * 60)
print()
print("RESULT:", "ALL APP-FLOW CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
print()
print("NOTE: This tests the exact URL inlined into the Expo bundle")
print("      against the live uvicorn server. It confirms the API")
print("      contract the mobile app depends on. It does NOT verify")
print("      rendering on a physical device or emulator.")

sys.exit(0 if all_ok else 1)
