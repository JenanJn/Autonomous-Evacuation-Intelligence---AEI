# Run AEI on your phone

The app opens on Home again. Select Current Location, Choose on Map, or Demo Mode, then select the disaster and prepare the location.

On Windows, double-click `RUN-MOBILE.cmd` inside AEI. Keep the phone and computer on the same Wi-Fi. The launcher installs missing dependencies and selects the local Wi-Fi address for the QR code.

Manual method inside `mobile`:

```powershell
npm ci
node scripts/start-phone.cjs
```

The project remains on Expo SDK 53. Use an SDK-53-compatible Expo Go. Your SDK 57 Expo Go cannot open it. Do not upgrade dependencies just to resolve this mismatch. For an installable APK, use the included EAS preview build instructions in [README-LOCATION-INDEPENDENT.md](README-LOCATION-INDEPENDENT.md).

No Python server is needed for local demonstration. Internet is needed to download the chosen area's real roads initially; public services may be unavailable. No synthetic grid is substituted on failure. The downloaded vectors and local routing continue offline within that area.

Start navigation and tap **Trigger Blockage Ahead**. The app marks a real road segment blocked and recomputes the route, or explains a shelter fallback. **Demo walk** advances the simulated position. **Fill shelter** demonstrates capacity-based fallback.

For shared capacity and road updates, optional operations setup is documented in [README-LOCATION-INDEPENDENT.md](README-LOCATION-INDEPENDENT.md). The dashboard is `/operations.html` on the training server. A matching mobile area must be published first.

This source archive is not an APK. Full physical-phone testing and live road download remain necessary. No official emergency service, automatic SMS or remote push delivery is configured.
