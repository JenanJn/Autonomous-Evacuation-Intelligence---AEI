"""
Verify EXPO_PUBLIC_BACKEND_URL is actually inlined into the Metro bundle.
Hits the bundler running at http://127.0.0.1:8081 with several known
Expo bundle paths and reports the first one that succeeds.
"""
import sys
import urllib.error
import urllib.request

URLS = [
    # Standard Expo SDK 53 entry bundle paths
    "http://127.0.0.1:8081/index.bundle?platform=ios&dev=true&minify=false",
    "http://127.0.0.1:8081/node_modules/expo/AppEntry.bundle?platform=ios&dev=true&minify=false",
    "http://127.0.0.1:8081/entry-*.bundle?platform=ios&dev=true&minify=false",
    "http://127.0.0.1:8081/node_modules/expo/AppEntry.bundle?platform=android&dev=true&minify=false",
]

ok = False

for url in URLS:
    print(f"\nTrying: {url}")
    try:
        with urllib.request.urlopen(url, timeout=180) as r:
            body = r.read().decode("utf-8", "replace")
            print(f"  HTTP {r.status}  body length {len(body)}")

            idx_ip = body.find("192.168.1.6")
            idx_ref = body.find("EXPO_PUBLIC_BACKEND_URL")

            if idx_ip >= 0:
                # Show a small window around the match
                start = max(0, idx_ip - 40)
                end = min(len(body), idx_ip + 60)
                snippet = body[start:end].replace("\n", " ")
                print(f"  [OK] LAN IP present at offset {idx_ip}")
                print(f"  snippet: ...{snippet}...")
            else:
                print("  [INFO] LAN IP not found in this bundle")

            if idx_ref >= 0:
                start = max(0, idx_ref - 20)
                end = min(len(body), idx_ref + 80)
                snippet = body[start:end].replace("\n", " ")
                print(f"  [OK] EXPO_PUBLIC_BACKEND_URL ref at offset {idx_ref}")
                print(f"  snippet: ...{snippet}...")

            # If we found the IP we are done
            if idx_ip >= 0:
                ok = True
                break

    except urllib.error.HTTPError as e:
        print(f"  HTTPError {e.code} {e.reason}")
    except urllib.error.URLError as e:
        print(f"  URLError {e}")
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")

print()
print("=" * 60)
if ok:
    print("VERDICT: PASS  -  EXPO_PUBLIC_BACKEND_URL is inlined into the bundle")
else:
    print("VERDICT: FAIL  -  LAN IP not found in any reachable bundle")
print("=" * 60)

sys.exit(0 if ok else 1)
