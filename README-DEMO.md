# Current mobile implementation — location-independent update

Home is the entry screen, followed by disaster/location setup and the shared evacuation session. The runtime downloads actual OpenStreetMap road geometry for the user-selected position; it does not create the legacy grid. Leaflet is bundled in the mobile WebView, with downloaded street vectors for offline display. The project remains on SDK 53. A native MapLibre migration was not included.

See README-LOCATION-INDEPENDENT.md for the current flow, shared operations, build instructions, test limits and implemented versus simulated features. The optional current operations console is `/operations.html`. The older standalone browser demo and its synthetic scenario are retained as legacy material.

## Earlier documentation (historical context)

# Redesigned mobile release

Start with **START-HERE.txt**. On Windows, double-click **RUN-MOBILE.cmd**. The complete project now contains the redesigned native evacuation map with distinct disaster zones and a simpler step-by-step flow. See **UX-REDESIGN.md** and **VALIDATION-MOBILE.md** for the current screen design and checks. Older browser-demo instructions below are optional companion material.

# Mobile update

The Expo app now opens on a native evacuation map with SQLite offline routing, GPS navigation and training operations controls. Start with **RUN-MOBILE.md** for the current mobile instructions. The browser implementation below remains an optional companion.

# AEI — professor demonstration and architecture

## Run the new interactive demo

Requires Python 3.11+ only. From this folder:

```powershell
python demo/server.py
```

Open http://localhost:8080 in Chrome or Edge. The terminal prints a temporary operations password. Optionally set `$env:AEI_ADMIN_PASSWORD` before starting. Server binds to this computer only. Browser GPS requires permission and may provide an approximate position on a laptop.

1. Click **Use current location**. A clearly labeled training disaster, three simulated shelters and a road graph are generated around your actual coordinates. If GPS is denied, the labeled Chennai sample remains available.
2. Choose Flood / Earthquake / Cyclone / Landslide / Fire. This changes the training disaster label; disaster-specific physical models are not implemented.
3. Click **FIND SAFE SHELTER**. Review at least two reachable options when possible, then preview or start navigation.
4. Click **Simulate road ahead blocked**. The same destination is replanned around the closure.
5. Click **Make shelter unreachable**. All incident roads close and the next reachable shelter becomes the destination. If none exists, navigation stops explicitly.
6. Open **Operations console**, enter the terminal password, edit capacity/status, toggle roads or hazards, and publish. Other clients using the same local area receive the new package within ten seconds while connected.
7. Click **Prepare offline area**, let the service worker install, reload once while connected, then disconnect the internet. Shell, graph routing, hazards, shelters and schematic navigation remain available. Do not stop the local server for the initial page load.

Map base is real OpenStreetMap geography; every road overlay, shelter, hazard and facility is synthetic. Synthetic roads do not follow verified streets. Do not interpret the result as real route guidance. This is a working teaching prototype, not a government-certified platform.

## Existing mobile project

The original Expo app and Python science/backend code are retained in `mobile/` and `AEI/`. Credentials and generated dependency caches from the archive are excluded.

```powershell
cd mobile
npm ci
npx expo start
```

Use **Demo at My Current Location**. It reads real GPS, opens the existing plan flow in explicit demo mode and anchors synthetic shelter coordinates around the selected position. Replan and clear keep that anchor. The app now opens on EvacuationMapScreen, a native mobile map/navigation interface; prior report screens are retained. There is no existing authentication account system: the demo mode is the training scope, not an invented government login.

Original backend:

```powershell
cd AEI
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn api.main:app --app-dir src --port 8000
```

Consult `AEI/README.md` for the original ML experiments. Existing backend demo endpoints remain unchanged and use their original synthetic network. The new browser demo uses `demo/server.py`, not port 8000.

## Deliverable structure

```text
AEI/                    retained science pipeline, FastAPI, risk and routing modules, tests
mobile/src/
  screens/              retained mobile screens, updated GPS training flow
  services/apiClient.ts anchored synthetic plans, blockage and reset
  data/                 retained fixtures
  navigation/           existing screen navigator
  types/                existing API contracts
demo/
  server.py             HTTP API, operations authentication, SQLite snapshots and audit
  web/index.html        map, shelter cards, modal, navigation and admin shell
  web/style.css         responsive high-contrast interface
  web/engine.js         portable pure Dijkstra engine and sample generator
  web/app.js            GPS, map projection, selection, rerouting, storage, synchronization
  web/sw.js             offline application shell
  tests/routing.test.cjs behavior tests
  demo.sqlite3          generated on first run, do not distribute real personal data here
schema.sql              proposed normalized production schema
ARCHITECTURE.md         system/UI/API/offline design and deployment gaps
```

## Checks

```powershell
node demo/tests/routing.test.cjs
node --check demo/web/app.js
python -m py_compile demo/server.py
```

Routing tests cover multiple shelters, location anchoring, hazard segment intersection, alternative routes, unreachable shelter fallback, closures, full capacity and inaccessible roads. These passed during development. JavaScript syntax and Python compilation passed. Browser visual testing and full original Expo/ML test suites were not completed in this environment; run the acceptance flow above on your presentation machine.

## Offline maps

Default public OSM raster tiles are for interactive online viewing. No tile download runs against that default provider. See https://operations.osmfoundation.org/policies/tiles/ . To use a provider you operate or that explicitly licenses offline storage, set a template in browser developer tools, then reload:

```javascript
localStorage.setItem('aei-tile-template', '/tiles/{z}/{x}/{y}.png');
```

Place your licensed raster package under `demo/web/tiles/`. Prepare offline area caches only the current viewport at its current zoom; it is not a city download. Outside cached coverage, the schematic graph remains. Offline status does not imply fresh hazard data. GPS operation depends on device hardware and permissions.
