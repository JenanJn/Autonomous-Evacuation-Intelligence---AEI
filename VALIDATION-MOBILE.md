# Mobile redesign verification — 21 October 2026

Completed:

- Full TypeScript project check: PASS.
- Mobile routing behavior tests: PASS (location anchoring, multiple shelters, segment-level hazard exclusion, blocked-road avoidance, alternative route, unreachable destination, closed/full shelter and accessibility filtering).
- Presentation tests: PASS (five distinct disaster styles, water/flame textures, texture centers inside hazard extents, guidance and route-exclusion explanation).
- Phone launcher tests: PASS (prefers Wi-Fi IPv4, excludes localhost and invalid link-local addresses); launcher syntax check: PASS.
- Dependency tree: PASS. SDK 53 compatibility updates are included: Expo 53.0.27, React Native 0.79.6, constants 17.1.8, location 18.1.6, screens 4.11.1, Babel preset 13.0.0; navigation elements 2.3.8 are deduplicated.
- Final Android Metro export: PASS, 873 modules, 1.64 MB JavaScript, 18 assets.
- Hermes compilation of the final Android bundle: PASS, exit 0 (2,541,425-byte test bytecode output, excluded from source ZIP).
- PNG asset decoding: PASS with Jimp. Icon/adaptive/splash images decode at 1024×1024 and favicon at 64×64. This replaces the original invalid two-byte files.
- Shared mobile UI reviewed in a browser adapter at 390×844 and 320×640. The native app uses react-native-maps and SQLite; the browser adapter is only for UI testing.
- Interaction checks: shelter selection → route preview → navigation; simulated road closure → new route and prominent notification; isolated destination → automatic alternative shelter with explanatory alert.
- Fire and flood visuals inspected. The final fire preview shows the label above the extent and flame symbols inside the zone. Symbol metadata for all five disaster types is covered by presentation tests.
- Offline readiness and schematic switch inspected. Schematic mode retained all three shelter markers and removed every OSM basemap image request from the rendered UI (0 tile images, 3 shelter markers).
- Main action bounds checked in the 390×844 preview; Find safe shelter remained fully inside the viewport. Compact layouts use numbered markers without overlapping full-name labels; names remain in shelter cards/details.

Screenshots are in previews/. These are phone-sized browser captures of the shared mobile UI, not screenshots from a physical Android phone.

Not completed: native phone visual/GPS/SQLite field testing, signed APK/IPA installation, a full network-loss/cold-start test on a standalone native build, background navigation, full downloadable offline basemaps, validated real infrastructure or government security/operational certification. The current data remains synthetic.

Reproduce from AEI after installing mobile dependencies:

```powershell
cd mobile
npm run type-check
cd ..
node demo/tests/routing.test.cjs ../../mobile/src/evacuation/engine.js
node demo/tests/presentation.test.cjs
node demo/tests/launcher.test.cjs
```
