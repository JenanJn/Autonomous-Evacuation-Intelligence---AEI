# Run the redesigned mobile app

Extract the complete ZIP into a new folder. On Windows, open AEI and double-click **RUN-MOBILE.cmd**. It installs dependencies if required, detects the laptop Wi-Fi address, chooses a free development port and launches Expo with that address in the QR code. It makes no persistent network/firewall changes. Node.js 24 LTS and compatible Expo Go are required.

Manual alternative, from AEI/mobile:

```powershell
npm ci
node scripts/start-phone.cjs
```

Keep the phone and laptop on the same Wi-Fi. Keep the terminal open. If Windows asks, allow Node.js on your trusted Private network. This project now uses Expo SDK 57. Keep the SDK 57 Expo Go already on your phone. If needed, get the matching version from the [official Expo Go download page](https://expo.dev/go?sdkVersion=57&platform=android&device=true). Native store/development builds need their map provider's Android/iOS credentials and configuration.

## Use and demonstrate

- Use my current location → Find safe shelter → choose a card → View this route → Start navigation.
- Tap a map marker for shelter details.
- Menu → Training studio → choose a disaster. Close the studio to see its water/fire/disaster-specific zone on the map.
- Start navigation, then Menu → Training studio → Block the road ahead to demonstrate re-routing. Make this shelter unreachable demonstrates automatic alternative-shelter navigation. Demo walk advances one simulated road.
- SOS opens location and stored demo medical information. Sharing uses the native share sheet and does not dispatch emergency services.
- Menu → Offline readiness shows connection, package timestamp/save status and schematic mode. Save the package before disconnecting. Foreground GPS and routing use local data. Full offline street basemap downloads and background navigation are not implemented.

For an offline cold start without Metro, install a standalone native build. Expo Go is the development workflow. No Python server is required for the local mobile demonstration. The optional browser QA adapter can be started with `npm run web`; the mobile implementation remains native react-native-maps and SQLite.

## Optional training updates between devices

From AEI on a trusted classroom network:

```powershell
$env:AEI_BIND_HOST = '0.0.0.0'
python demo/server.py
```

Set `EXPO_PUBLIC_DEMO_SERVER_URL=http://YOUR_COMPUTER_LAN_IP:8080` in mobile/.env, then restart Expo. Use HTTPS for deployment; native transport rules can reject plain HTTP. Sign into the training server from Training studio with the temporary terminal password, then publish. Incoming packages are accepted only near the loaded scenario origin (100 m). Local training edits do not grant government access or publish official alerts.

See UX-REDESIGN.md for screen design and the remaining government-deployment work, and VALIDATION-MOBILE.md for verification. This is a training prototype with synthetic infrastructure, not an operational evacuation tool.
