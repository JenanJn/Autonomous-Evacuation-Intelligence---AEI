# AEI: location-independent evacuation demonstration

This updates the existing AEI project. The original ML/backend project and legacy screens are retained. The mobile app opens on Home again.

## User flow

Home → Current Location / Choose on Map / Demo Mode → select Flood, Fire, Cyclone, Earthquake or Landslide → prepare the chosen location → compare reachable demo shelters → preview → navigate → Trigger Blockage Ahead → see a new route or an explained shelter fallback.

There is no fixed city or campus in the new runtime flow. Empty/new installations begin at the world map, not at a preset demonstration city. `engine.scenario()` remains only for legacy tests and the older browser demo; the new mobile session uses downloaded OpenStreetMap data.

## Run the phone app

1. Stop older Metro terminals with Ctrl+C.
2. Double-click `RUN-MOBILE.cmd` in AEI. The launcher installs missing dependencies.
3. Keep computer and phone on the same trusted Wi-Fi and scan its QR code.
4. This release deliberately stays on Expo SDK 53. Expo Go must support SDK 53. SDK 57 Expo Go cannot open this source; do not run dependency-upgrade commands to fix that mismatch.

Manual method inside `mobile`:

```powershell
npm ci
node scripts/start-phone.cjs
```

For the browser UI adapter: `npm run web` inside mobile. It renders the same bundled map document; native persistence uses SQLite and browser persistence uses localStorage.

## Installable Android APK

The source ZIP is not an APK. An APK can run independently of Expo Go and Metro after installation. The project includes an EAS `preview` profile that produces an APK:

```powershell
cd mobile
npx eas-cli login
npx eas-cli build:configure
npx eas-cli build --platform android --profile preview
```

For shared operations in a cloud-built APK, configure `EXPO_PUBLIC_DEMO_SERVER_URL` in the EAS preview environment; a gitignored local `.env` is not automatically uploaded. Local demonstrations do not need that server.

An Expo account, project association and signing/build access are needed. No account was created and no cloud build was submitted in this implementation session. Check EAS build availability/pricing in your own account before submitting a build. GPS, map WebView, SQLite, audio and installation still require testing on the physical target phone.

## Real maps and real routes

- The map renderer is Leaflet 1.9.4, bundled locally inside the mobile WebView. It uses online OpenStreetMap tiles while available and does not use the Expo Go Google Maps key.
- This is a practical SDK-53-compatible implementation. It does not install MapLibre Native or change the Expo SDK. A future MapLibre migration would require its own native-build/version review.
- New area preparation downloads actual highway nodes/ways and available geographic features within approximately 1.6 km of the chosen point. Roads preserve OSM IDs, geometry, names, mapped public-access restrictions and vehicle one-way rules.
- Walking, driving and ambulance are planning profiles. Ambulance mode does not bypass closures or dispatch a vehicle. Unmapped turn restrictions, gates, height/weight limits and real emergency authorisations are not comprehensively modelled.
- The risk-aware Dijkstra search excludes blocked roads and hazard intersections and penalises nearby risk. Route geometry, directions, distance and time all come from the same selected path.
- A selected point may need an off-road approach to the nearest mapped street. The app displays an unverified-approach notice when this is over 25 m, rejects snaps over 350 m and rejects approaches crossing the simulated hazard. It does not claim the approach is walkable.
- View surroundings opens an external Google Maps Street View URL for the selected/current position. Coverage and connectivity are required. Imagery is historical and is not an assessment of road safety. There is no embedded panorama, Mapillary integration or offline street imagery in this release.

## No invented road fallback

Public Overpass servers are best-effort services. The app tries a fallback endpoint, supports cancellation, and reports download/coverage errors. It never substitutes the old synthetic grid when a request fails. Sparse or disconnected networks may provide fewer than two suitable destinations or no alternative road; the app explains this instead of inventing connectivity.

The live services returned an upstream error/timeouts during this implementation session. Tests validate parsing, retries, routing and UI flow with controlled OSM-format fixtures; they are not proof of successful live road download on the user's network. Test a fresh GPS-selected download with internet before presenting.

Optional `mobile/.env` setting:

```text
EXPO_PUBLIC_OVERPASS_URL=https://YOUR_OWN_OVERPASS_SERVICE/api/interpreter
```

Do not commit credentials. No API key is required for the default public Overpass endpoints. For institutional deployment use a managed/self-hosted service with defined availability rather than depending on free public infrastructure.

## What is simulated

Hazards, closures and shelter occupancy are training data. Demo destinations are anchored to real mapped streets near suitable mapped amenities where available; otherwise they are explicitly labelled demo assembly points. They are not verified emergency shelters. Food, water, medical and accessibility facilities are not inferred as available simply because a nearby building exists.

Fire, flood, cyclone and landslide scenarios use affected polygons. Earthquake shows an epicentre/damage zone and illustrative rings. The training studio can expand a footprint, update severity, toggle closures, check people in/out and publish a package.

## Rerouting presentation

1. Start navigation to a recommended destination.
2. Tap **Trigger Blockage Ahead** on the main navigation panel.
3. An upcoming real street segment becomes blocked/red. The route is temporarily hidden and the app announces recalculation.
4. It calculates another route using the updated graph and refreshes distance, time and guidance. If the destination is unreachable, it explains the switch to another suitable shelter. No reachable option produces an explicit unavailable state.
5. **Demo walk** advances along the actual remaining route. **Fill shelter** demonstrates capacity-based destination fallback.

The short recalculation indicator ensures the state change is visible; the resulting path is actually recomputed rather than selected from prerecorded lines. Demo road updates are local unless an authenticated training package is published or the operations server updates a road.

## Offline behaviour

The last prepared area's actual street vectors, available building/water/park geometry, hazard shapes, shelters, capacity snapshot and routing graph are stored on the phone. Downloaded vectors remain a geographical street map when online tiles fail; it is not the original generated grid. No CDN script is required to initialise the map.

Detailed raster tiles are used with normal WebView/browser HTTP caching only. The app does not bulk-download standard OSM tiles or promise full raster coverage offline. Offline base geography consists of the downloaded vectors. Outside the saved area a new download is needed. Offline capacity is a dated snapshot; no new remote alerts or closures arrive without connectivity. Expo Go still normally needs Metro to cold-start; an installed standalone APK is needed to launch independently.

## Live training operations

Run from AEI on a trusted classroom network:

```powershell
$env:AEI_BIND_HOST='0.0.0.0'
python demo/server.py
```

Open `http://COMPUTER_LAN_IP:8080/operations.html`. The server prints a temporary operator password. In `mobile/.env` set `EXPO_PUBLIC_DEMO_SERVER_URL=http://COMPUTER_LAN_IP:8080`, restart Metro, prepare an area, sign in from Training studio, and publish it once. Enter the same password in the operations page.

- Authenticated check-ins/check-outs are committed atomically in SQLite. Over-capacity updates are rejected, and zero spaces marks a shelter FULL. Capacity and road changes reach matching mobile sessions on their next 10-second sync.
- Standalone local demo check-ins update the phone immediately and persist locally. They are not globally live occupancy.
- Authenticated operations can block/reopen a selected real road and issue a foreground training warning. Changes create revisions and audit entries.
- The global foreground warning includes a bundled siren, vibration and acknowledgement that stops both. Actual sound/vibration depend on the target phone and permissions/settings.
- Real push notification and automatic SMS providers are not configured. No real emergency alert, SMS or dispatch is sent. Background/terminated-app delivery and continuous background navigation are not implemented.
- HTTPS is required for deployment. The preview APK profile explicitly enables cleartext HTTP only for the trusted classroom server through an opt-in config plugin. Production does not enable that opt-in.

## Verification

```powershell
cd mobile
npm run type-check
cd ..
node demo/tests/routing.test.cjs ../../mobile/src/evacuation/engine.js
node demo/tests/real-roads.test.cjs
node demo/tests/presentation.test.cjs
node demo/tests/launcher.test.cjs
python demo/tests/test_training_operations.py
```

See VALIDATION-MOBILE.md for actual build and UI test results and remaining physical-device limitations. This remains a prototype; verified shelter datasets, official hazard feeds, operational authentication, security review and field validation are needed before emergency deployment.
