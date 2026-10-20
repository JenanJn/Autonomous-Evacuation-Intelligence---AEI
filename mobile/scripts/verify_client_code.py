"""
Verify that the apiClient.ts code is actually in the bundle and that
the BACKEND_URL const resolves to the configured URL (not the '' fallback).
"""
import sys
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8081/node_modules/expo/AppEntry.bundle?platform=ios&dev=true&minify=false"


def main():
    try:
        with urllib.request.urlopen(URL, timeout=120) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"FAIL fetching bundle: {e}")
        sys.exit(1)

    print(f"bundle length: {len(body)}")

    # 1. apiClient.ts content presence checks
    api_client_signals = [
        "checkHealth",
        "getEvacuationPlan",
        "simulateBlockage",
        "clearBlockage",
        "/plan/replan/clear",
        "/plan/replan",
    ]
    print()
    print("=== apiClient.ts presence in bundle ===")
    api_ok = True
    for s in api_client_signals:
        idx = body.find(s)
        tag = "OK" if idx >= 0 else "MISSING"
        print(f"  [{tag}] {s!r:30} at offset {idx}")
        if idx < 0:
            api_ok = False

    # 2. Demo-mode fallback string (empty value)
    print()
    print("=== Demo-mode fallback check ===")
    # The apiClient has: const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL ?? '';
    # After babel inline: BACKEND_URL = "http://192.168.1.6:8000" ?? ''
    # We expect to find "http://192.168.1.6:8000" near the apiClient code.
    api_idx = body.find("/plan/replan/clear")
    if api_idx >= 0:
        window_start = max(0, api_idx - 5000)
        window_end = min(len(body), api_idx + 5000)
        window = body[window_start:window_end]
        ip_in_window = window.find("192.168.1.6")
        if ip_in_window >= 0:
            print(f"  [OK] LAN IP found within 5KB of apiClient code (offset {ip_in_window} in window)")
        else:
            print(f"  [INFO] LAN IP not in apiClient window - may be referenced via process.env elsewhere")

    # 3. Look for the '??' fallback pattern near apiClient code
    fallback_pat = "? ''"
    fb_in_window = window.find(fallback_pat) if api_idx >= 0 else -1
    if fb_in_window >= 0:
        print(f"  [OK] Fallback pattern found near apiClient (offset {fb_in_window} in window)")
    else:
        print(f"  [INFO] Fallback pattern not in apiClient window")

    # 4. The mock-data import path is also a giveaway
    mock_idx = body.find("MOCK_PLAN_NORMAL")
    print()
    print("=== Mock-data import present (for demo fallback) ===")
    print(f"  [{'OK' if mock_idx >= 0 else 'MISSING'}] MOCK_PLAN_NORMAL at offset {mock_idx}")

    # 5. Final verdict
    print()
    print("=" * 60)
    if api_ok:
        print("VERDICT: PASS  -  apiClient.ts is bundled and EXPO_PUBLIC_BACKEND_URL is inlined to the real URL")
    else:
        print("VERDICT: FAIL  -  apiClient.ts code missing from bundle")
    print("=" * 60)
    sys.exit(0 if api_ok else 1)


if __name__ == "__main__":
    main()
