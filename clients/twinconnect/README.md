# TwinConnect — shared Flutter client (foundation)

One client source for Android, Windows, iOS and macOS. The app supports **Persian (RTL) and English (LTR)**: it follows the device language by default and provides an in-app language selector (automatic, فارسی, English). The selection is stored locally using shared preferences, without storing subscription credentials. All installations of TwinPanel share the **same app binaries**; the logo, brand/contact details, reseller affiliation and renewal link are retrieved from the licensed owner's panel after account verification.

**Current status: prototype/foundation. This is NOT yet a working VPN application.** The interface displays branding and contact information. The connect button is disabled until native VPN engines, secure session/bootstrap and connection lifecycle management are implemented and tested per platform.

## Identity flow

1. Customer enters a complete VPN account username, plus a valid subscription URL or short token.
2. The client extracts a \`TP<16HEX>\` installation namespace from the username (or accepts a separate namespace for existing/admin users without a prefix).
3. The client queries the **vendor directory** with only that namespace:
   \`GET /v1/app/resolve/{namespace}\`.
4. The vendor returns the public HTTPS API origin of the app-entitled, active installation. No username or subscription token reaches the vendor.
5. The client directly contacts the selected panel:
   \`POST /v1/central-app/public/brand-preview\` with the username and share token.
6. The panel checks both values against the **same existing subscription** and returns the correct owner's or reseller's brand, Telegram support, website, phone and renewal link. The response does **not** contain VPN configuration or secrets.

The username prefix is only a routing hint; the share token supplies subscription-level proof for this preview. This is **not** a user login session and must never grant VPN access by itself.

## Developer setup

Install a compatible Flutter SDK and native platform toolchain.

\`\`\`bash
cd clients/twinconnect
flutter create --platforms=android,ios,macos,windows --org com.twinpanel --project-name twinconnect .
flutter pub get
flutter analyze
flutter test
\`\`\`

Run the app with the real HTTPS vendor directory (no embedded vendor license keys):

\`\`\`bash
flutter run -d windows --dart-define=TWINCONNECT_DIRECTORY_URL=https://YOUR-VENDOR-DIRECTORY.EXAMPLE
\`\`\`

Replace \`windows\` with an available Android, iOS or macOS device. Vendor base URL is public configuration, not a client-side secret. The current client requires a globally registered and active \`central_app\` entitlement in the vendor database.

## CI

\`.github/workflows/twinconnect-flutter.yml\` analyzes and tests the source on each pull request that changes it. An optional manually triggered workflow builds platform previews via GitHub-hosted runners.

- Android: APK preview
- Windows: Release directory preview (not a signed installer)
- macOS: .app preview (not notarized)
- iOS: unsigned .app preview (not an installable signed IPA)

App Store publication requires Apple signing, provisioning profiles, VPN entitlements/Network Extensions, a valid organization developer account where applicable and platform review. macOS distribution requires code signing and notarization.

Native project directories are generated during CI at this stage; before shipping, freeze/review platform settings, bundle IDs, VPN entitlements, permissions and signing policy in the repository.

## Still to implement

- A secure short-lived subscription-scoped session service for the real connection engine.
- Native VPN adapters that are supported on each OS (WireGuard, OpenVPN, sing-box/Xray and others); **do not** assume a single engine supports all protocols.
- Real latency and health measurements, connection state, reconnect policy, kill switch and leak tests.
- Secure token storage and account switching; the current prototype intentionally does not persist credentials.
- Robust verification of panel-origin ownership and rate limiting in the vendor directory.
- Automated deployment/signing pipelines once all four OS-specific implementations pass acceptance tests.

The app must not bypass a panel-only license. No changes to active VPN traffic or existing customer subscriptions are required to run this prototype.

## Localization quality gate

`lib/app_strings.dart` contains all static Persian/English labels and error translations. Platform/framework translations use the official Flutter Material/Widgets/Cupertino delegates, with fallback to English for other device languages. `test/widget_test.dart` exercises RTL-to-LTR switching, persistence and bilingual errors; `test/tenant_client_test.dart` covers panel-brand data which must stay unmodified across language changes.
