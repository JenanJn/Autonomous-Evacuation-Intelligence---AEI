# Run AEI on your phone — native mobile map update

The Expo app now starts on a native evacuation map. No laptop/server is needed for on-device scenario generation, shelter selection, routing, SQLite storage or rerouting. Your development computer is needed to serve Expo during development; a standalone native build is required to launch independently of Metro.

## Install and launch

Extract AEI-mobile-updated.zip into a NEW folder. Open PowerShell in its AEI/mobile folder:

```powershell
npm ci
npx expo start --clear
```

Scan with an Expo Go installation compatible with this existing project's Expo SDK 53. Keep phone and development computer on the same Wi-Fi. If necessary use `npx expo start --tunnel`. If Expo Go reports an SDK mismatch, use the Android version offered at https://expo.dev/go for SDK 53, or create a development build; current iOS Expo Go may require an SDK upgrade. This update preserves SDK 53 rather than claiming a tested upgrade to a newer SDK.

The new dependencies are react-native-maps 1.20.1 and expo-sqlite ~15.2.14, matching Expo's SDK 53 native-module catalog. Source: https://github.com/expo/expo/blob/sdk-53/packages/expo/bundledNativeModules.json . Native maps are implemented with react-native-maps, not a WebView. Native Android production builds require the map provider's platform setup/API credentials; Expo Go uses its bundled map integration. See https://docs.expo.dev/versions/latest/sdk/map-view/ .

## Demonstrate on the phone

1. App opens directly on the map. The starting sample is explicitly labeled.
2. Tap USE CURRENT LOCATION and allow GPS. A training disaster, road graph and three synthetic shelters are positioned around the phone.
3. Tap FIND SAFE SHELTER. Review at least two reachable options when available.
4. Tap a shelter marker or card. Review details, preview the route, then START NAVIGATION.
5. In navigation, tap DEMO: BLOCK ROAD AHEAD to replan. Tap DEMO: SHELTER UNREACHABLE to demonstrate destination fallback.
6. Open TRAINING OPERATIONS / ADMIN to switch disaster type, toggle hazards, edit capacity/status, block/open roads or reset. Local training controls intentionally require no government credentials and cannot send official alerts.
7. Tap SAVE OFFLINE ROUTING PACKAGE. Switch on Offline schematic map. Disable mobile data/Wi-Fi after the JavaScript bundle has loaded. Local routing and stored information remain available. For a reliable cold start with no Metro connection, install a standalone development/release build; Expo Go/Metro is a development workflow, not a production offline installer.
8. SOS displays coordinates and stored demo medical information. SHARE MY LOCATION uses the phone's native share sheet; successful delivery depends on the chosen app and connectivity. No emergency dispatch is connected.

GPS updates while the app is open. Instructions show the next graph leg and following left/right/straight turn. Arrival is detected within 45 m of the simulated shelter. Guidance stops outside the loaded demo area. Long-press the map to place a training scenario manually when not navigating. Schematic mode retains georeferenced overlays when a provider basemap is unavailable. No downloaded native basemap package is bundled.

## Optional publication between phones

This is optional and not needed for the evacuation demo itself. The training server accepts signed-in package publication and clients poll every 10 seconds. A local change does not become an official alert. Tokens stay in memory and expire after an hour.

For a trusted classroom Wi-Fi demonstration, from AEI:

```powershell
$env:AEI_BIND_HOST = '0.0.0.0'
python demo/server.py
```

Set `EXPO_PUBLIC_DEMO_SERVER_URL=http://YOUR_COMPUTER_LAN_IP:8080` in mobile/.env, then restart Expo. Do not use localhost on the phone. Allow the local firewall only on your trusted private network if prompted. For deployment use HTTPS; native platform transport rules can reject plain HTTP. Server password is printed in the server terminal. Use it in the mobile training operations sign-in, then publish. Clients must load a scenario within 100 m of the published area's origin to accept it. Long-pressing the same map point is one way to align two clients.

## Files changed

- mobile/src/screens/EvacuationMapScreen.tsx — native map, shelter flow, foreground GPS navigation, fallback, SOS and training admin UI.
- mobile/src/evacuation/engine.js + engine.d.ts — local risk-aware Dijkstra implementation and typed contract.
- mobile/src/evacuation/storage.ts — persistent SQLite snapshot.
- mobile/src/navigation/ — new map registered as initial screen; prior report screens retained.
- mobile/package.json + package-lock.json — SDK-compatible native map and SQLite packages.
- demo/server.py — optional LAN bind via AEI_BIND_HOST, loopback default retained.

This is still a training prototype: roads, shelters and hazards are simulated, not verified infrastructure. Disaster types change training scenarios; there are no calibrated disaster physics models or official data integrations. Native field testing and a full offline basemap solution remain required before real deployment.

## Verification

TypeScript, the mobile routing tests, dependency resolution, Android JavaScript bundling and Hermes bytecode compilation passed. See VALIDATION-MOBILE.md. Physical phone testing and a signed APK/IPA build have not been performed here.

