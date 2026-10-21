# Current mobile implementation — location-independent update

Home is the entry screen, followed by disaster/location setup and the shared evacuation session. The runtime downloads actual OpenStreetMap road geometry for the user-selected position; it does not create the legacy grid. Leaflet is bundled in the mobile WebView, with downloaded street vectors for offline display. The project remains on SDK 53. A native MapLibre migration was not included.

See README-LOCATION-INDEPENDENT.md for the current flow, shared operations, build instructions, test limits and implemented versus simulated features. The optional current operations console is `/operations.html`. The older standalone browser demo and its synthetic scenario are retained as legacy material.

## Earlier documentation (historical context)

# AEI mobile redesign — clearer evacuation under stress

This release redesigns the native Expo app. The old science/backend project and optional browser companion remain included. The citizen UI is now a map with a short action panel, rather than a scrolling collection of demo controls.

## What makes this version stand out

1. A disaster you can recognize: floodwater is blue with wave marks; fire is orange with flame symbols; cyclone, earthquake damage and landslide zones use distinct labels, symbols, colors and patterns. Symbols are anchored to the hazard extent, not fixed decorations on the screen. The label sits above the extent so it does not cover the water or fire pattern.
2. One decision at a time: locate yourself → find shelters → choose → preview → navigate. Context changes the bottom panel. Settings and training controls do not compete with navigation.
3. Explain the recommendation: display the walking estimate, distance and free spaces, plus the number of hazard zones and closed roads excluded from the route search. The score remains a synthetic risk-aware cost, not a safety guarantee.
4. Recovery is visible: a closure triggers a prominent route-update message. If the destination becomes unreachable, the app names the alternative shelter and continues there. With no route, it stops clearly.
5. Offline confidence with honest limits: a dedicated readiness screen shows saved data, connection state, timestamp and schematic mode. Unknown connectivity is not asserted to be online. A save failure is not labeled as saved.
6. Emergency help stays within reach: SOS is always in the header; the help screen shows the position source and coordinates, refresh GPS and native share controls, and stored demo medical information.

## Screen design

- Map/home: larger map, compact incident banner, location control, route-data status and one Find safe shelter action. The training banner persists.
- Choose: numbered shelter cards; recommendation, walking time, distance and capacity; a single View this route action. Numbers match map markers even after ranking changes.
- Preview: destination, time/distance, reason for recommendation and Start navigation. Detailed facilities are available separately.
- Navigate: large direction card at the top, the route on the map, concise destination/time panel below, alternatives and End navigation. Camera framing accounts for the panel and hazard extent.
- Details: status, spaces, medical support, food/water, accessibility, toilets and demo contact. A missing route is explicit.
- Offline: connectivity, save state and freshness, preserved routing and schematic map. Full offline basemaps remain unimplemented.
- SOS: accurate position label (GPS vs saved/sample), selectable coordinates and native share sheet. No fake emergency-service numbers or simulated dispatch.
- Menu/training: accessible routes and map key live in the menu. A separate Training studio contains disaster selection, severity, closures, shelter availability, demo walking and optional authenticated publication.

The main action buttons are at least 54 logical pixels tall, icon controls 48, and actionable text controls at least 44. Colors are paired with symbols and text. Primary actions stay outside the scrollable shelter list. Body content can scroll on compact screens or with larger system text. No automatically animated hazard effect is needed to recognize a disaster, which reduces visual distraction.

## Code structure

- `useEvacuation.ts`: GPS, package persistence, connectivity, phase transitions, online synchronization, rerouting and arrival detection.
- `presentation.ts`: disaster presentation metadata, extent textures, route explanation and next-step labels.
- `ui/EvacuationMap.tsx`: native georeferenced map layers and camera framing.
- `ui/EvacuationMap.web.tsx`: browser QA adapter using the same model and UI; this is not a substitute for the native app.
- `ui/primitives.tsx`: reusable accessible actions, icons, status pills and information rows.
- `ui/TrainingPanel.tsx`: isolated teaching/operations controls.
- `EvacuationMapScreen.tsx`: citizen layout and focused detail/settings/SOS sheets.

Native persistence remains SQLite. The browser QA adapter uses browser storage and online OSM tiles. No public OSM tile downloads are added. Native basemap availability is provider/device-dependent; schematic mode renders stored overlays.

## What still separates this from government deployment

This is a more usable prototype, not a government-ready certification. Government deployment still requires verified shelters and real routable roads; authoritative feeds and validated disaster-specific risk rules; signed regional offline map packages; enterprise authentication and role enforcement; reliable capacity updates; localization, offline voice guidance and accessibility testing; GPS/arrival/off-route field validation; security/load/backup/incident operations review.

The best next differentiators are local-language voice instructions, a verified regional offline download with a readiness check, and official source/freshness information for every incident. Family location sharing should be opt-in and privacy-preserving. These are roadmap ideas, not features claimed by this release.
