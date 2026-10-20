"""
Integration verification script.
Tests /health and /docs via both localhost and LAN IP.
Usage: python scripts/integration_verify.py [LAN_IP]
"""
import json
import sys
import urllib.error
import urllib.request

LAN_IP = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.6"
PORT = 8000

targets = [
    ("localhost",  f"http://127.0.0.1:{PORT}"),
    ("LAN IP",     f"http://{LAN_IP}:{PORT}"),
]

all_ok = True

for label, base in targets:
    print(f"\n--- {label}: {base} ---")

    # /health
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=4) as r:
            body = json.loads(r.read())
            ok = r.status == 200 and body.get("status") == "ok"
            tag = "OK" if ok else "FAIL"
            print(f"  [{tag}] GET /health  status={r.status}  body.status={body.get('status')!r}  version={body.get('version')!r}")
            all_ok = all_ok and ok
    except urllib.error.URLError as e:
        print(f"  [FAIL] GET /health  -> {e}")
        all_ok = False

    # /docs
    try:
        with urllib.request.urlopen(f"{base}/docs", timeout=4) as r:
            ok = r.status == 200
            tag = "OK" if ok else "FAIL"
            print(f"  [{tag}] GET /docs   status={r.status}")
            all_ok = all_ok and ok
    except urllib.error.URLError as e:
        print(f"  [FAIL] GET /docs  -> {e}")
        all_ok = False

    # POST /plan (quick sanity)
    try:
        data = json.dumps({"lat": 0.0, "lon": 0.0}).encode()
        req = urllib.request.Request(f"{base}/plan", data=data,
              headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=4) as r:
            body = json.loads(r.read())
            ok = (r.status == 200
                  and body.get("primary_route", {}).get("feasible") is True
                  and body.get("is_simulated") is True)
            tag = "OK" if ok else "FAIL"
            path = body.get("primary_route", {}).get("path", "?")
            print(f"  [{tag}] POST /plan  status={r.status}  route={path}  simulated={body.get('is_simulated')}")
            all_ok = all_ok and ok
    except urllib.error.URLError as e:
        print(f"  [FAIL] POST /plan  -> {e}")
        all_ok = False

print()
print("=" * 50)
result = "ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED"
print(f"RESULT: {result}")
print("=" * 50)
sys.exit(0 if all_ok else 1)
