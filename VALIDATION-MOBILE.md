# Location-independent mobile release validation — 21 October 2026

The earlier UI redesign and source/backend projects are retained. This release deliberately remains on Expo SDK 53.0.27. It is not the SDK 57 upgrade that was rolled back.

Completed checks:

- TypeScript project check and offline Expo native-package compatibility check: PASS.
- Legacy routing regression tests: PASS.
- New OSM-format network regression tests: PASS. Covers multiple geographic origins, actual supplied node/way identity, five hazard geometries, alternative-route computation, full-shelter exclusion, east/west guidance, polygon crossing, driving one-way rules, pedestrian restrictions and sparse coverage errors. Fixtures are test-only; no fixed demo city is used by the mobile runtime.
- Presentation and Wi-Fi launcher tests: PASS.
- Training operations API integration: PASS. A temporary database and local test server verified authentication, simultaneous capacity changes, over-capacity rejection, reopen-on-check-out, road closures, training alerts and audit entries. Test database connections close deterministically.
- Bundled map renderer browser test: PASS. It initialises without internet or CDN scripts, displays downloaded street vectors, renders five hazard labels, bridges shelter clicks and map selection, escapes facility text and retains markers when tile requests fail. This uses an OSM-format fixture, not a live downloaded area.
- Full mobile UI browser adapter flow: PASS. Home → demo disaster/GPS setup → parser → shelter selection → preview → navigation → transient blockage state → alternative route → full-shelter fallback → Home/resume → alternate disaster/map picker. No uncaught page errors; no horizontal page overflow at 320 pixels. A hidden duplicate navigation subtree initially confused a test locator; the test was corrected to inspect visible elements.
- Android Metro export and Hermes compilation: PASS. JavaScript export is a build check, not an APK installation or native runtime test. The final Android export contains 879 modules and 19 assets (approximately 1.85 MB JavaScript). The web export contains 532 modules and 13 assets (approximately 1.15 MB JavaScript).
- Web Metro export: PASS. An earlier attempt to overwrite a nested export directory hit a Windows permission error; exporting to a fresh test directory succeeded.
- Local Expo public configuration resolves with SDK 53.0.0 and the opt-in classroom network plugin.
- Home layout reviewed at 390 pixels. The captured Home image is from the browser adapter, not a physical phone.

Important limits:

- Live public Overpass integration could not be verified successfully here: the main service returned an upstream 502, and fallback/small probes timed out. Loading a new real area must be tested on the user's network before presenting. The app reports failures and does not substitute a generated road grid. An institution can configure its own endpoint.
- Physical-phone GPS, native WebView, SQLite, audio/vibration, permissions, network-loss behaviour and signed APK installation have not been verified in this session.
- The last area stores real street vectors and available geographic features. Full detailed raster-map coverage and street imagery are not downloaded. Standard OSM tile bulk downloading is not implemented.
- Hazards, occupancy and demo destinations remain simulated. No official shelter/hazard feed, dispatch, real SMS provider or remote/background push delivery is connected.
- Route profiles do not model every legal restriction, live traffic condition or emergency-service permission. This is not an operational evacuation service.
- EAS APK configuration/instructions are included; no account login, project creation, signing or cloud APK build was performed.

Reproduce from AEI:

```powershell
cd mobile
npm ci
npm run type-check
cd ..
node demo/tests/routing.test.cjs ../../mobile/src/evacuation/engine.js
node demo/tests/real-roads.test.cjs
node demo/tests/presentation.test.cjs
node demo/tests/launcher.test.cjs
python demo/tests/test_training_operations.py
```
