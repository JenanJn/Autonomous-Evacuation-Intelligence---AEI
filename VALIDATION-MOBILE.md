# Mobile verification

Completed on 20 October 2026:

- Full project TypeScript check: PASS (`tsc --noEmit`).
- Native mobile routing module behavior tests: PASS (multiple shelters, location anchoring, segment/hazard exclusion, blocked-edge avoidance, alternative route, unreachable destination fallback, shelter closure/capacity and accessibility).
- npm dependency tree for maps, SQLite, assets and navigation elements: PASS. Navigation elements are pinned and deduplicated to 2.3.8.
- Android Metro JavaScript export: PASS, 846 modules, 1.55 MB bundle.
- Hermes compilation of that final JavaScript bundle: PASS, exit 0. Output was placed in the workspace because Expo's default temporary bytecode directory was blocked by Windows permissions.
- Updated archive integrity and exclusion checks: PASS. Installed dependencies, credentials, SQLite runtime databases and generated build caches are excluded.

Not completed: installation on a physical Android/iOS phone, native visual/GPS/SQLite field tests, signed APK/IPA build, background navigation, a complete downloadable offline basemap, or validation of real infrastructure. This remains a simulated classroom prototype. The standard Expo runtime/device acceptance sequence is in RUN-MOBILE.md.

Reproduce the code checks from the extracted AEI folder after installing mobile dependencies:

```powershell
cd mobile
npm run type-check
cd ..
node demo/tests/routing.test.cjs ../../mobile/src/evacuation/engine.js
```
