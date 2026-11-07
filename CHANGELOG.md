# TwinPanel Changelog

## 1.1.0-rc.657 — 2026-11-07

### Connection footer repaired for all protocols
- Fix shared footer initialization race: V80 previously marked an app-only footer as complete before V51/V52/V78 supplied the actual protocol actions.
- Move the **original functional** per-protocol download/add, copy-link, and copy-config controls into one canonical footer without replacing their click handlers or subscription links.
- Restore distinct download-app links inside the same footer across supported protocols; prevent repeated standalone client cards.
- Generate real text-based **copy all configurations** for OpenVPN, WireGuard and AmneziaWG, reading actual configuration text from loaded server views.
- Preserve extra per-protocol YAML/JSON operations in a secondary expandable section, without deleting them.
- Keep Windows four equally sized actions in one row and Android one full-width main action above three equal actions when four actions are available.
- Synthetic DOM audit using actual Connection HTML with generated V51 controls confirmed four action kinds for eight protocol samples (OpenVPN, WireGuard, AmneziaWG, Snell, Hysteria2, ShadowTLS, Sudoku and V2Ray). All 40 scripts passed JavaScript syntax checks.
- Complete interactive browser testing across all device types and protocols is still outstanding. No changes to VPN server runtimes, nodes, tunnels or user credentials.

## 1.1.0-rc.656 — 2026-11-07

### Connection import scripts: verified root-cause fix
- Fix repeated string rewriting that generated invalid JavaScript `async async function` in V34/V37/V38 client-import scripts.
- Preserve asynchronous V37 `buildMulti` after the public-Connection request-backpressure transformation; it must await the client import URL resolver.
- Restore execution of client import / add-to-app and multi-config action builders on all platforms without changing subscription URIs, node configuration or VPN runtime.
- Retain responsive Windows four-action and Android three-plus-one footer layouts, client download links and the V2Ray per-node copy control.
- Validated that all **40 scripts** from a live Connection HTML response pass Node.js syntax checks with **zero failures** after applying the server patch.
- Browser interactive clicks / full visual regression across all protocols still require validation; this release addresses the reproducible JavaScript parse failures.

## 1.1.0-rc.655 — 2026-11-07

### V2Ray/Xray late-loading node actions
- Observe asynchronous V2Ray server group insertion and attach a real copy-all-existing-configs action to every newly rendered server. Avoid duplicate buttons and mutation feedback loops.
- Preserve the rc.654 V2Ray cards, mobile/desktop Connection layout and protocol-specific download/import behavior.
- The public feed intentionally includes only eligible stored profiles; missing runtime/configuration inbounds are **not** fabricated by this UI update.
- No database schema, node listener or tunnel configuration changes.

## 1.1.0-rc.654 — 2026-11-07

### V2Ray/Xray Connection repair
- Add an explicit **Copy server configs** button to every V2Ray/Xray node; copies all distinct, actually available VLESS URIs for that node.
- Remove conflicting fixed-height/overflow presentation restrictions from expandable Xray profile cards, preserving all returned profile rows and their per-profile copy/import buttons.
- Keep Windows four-action footer and Android one-primary-plus-three layout, client download links and configured TwinPanel theme.
- **Data diagnostic:** the tested account's V2Ray metadata currently provides 1, 1, 1 and 2 configurations for its four nodes; this frontend fix does not provision missing inbounds or pretend the nodes have three live configurations each. Provisioning requires separate runtime/back-end verification.
- No intentional changes to VPN protocol configuration, credentials, tunnels or node runtime.

## 1.1.0-rc.653 — 2026-11-07

### Official package parity
- Rebuild the installable release from the latest GitHub source rather than reusing the older rc.652 artifact. This includes the Connection changes that had previously been applied only as production hotfixes.
- Windows: four available Connection footer actions in one horizontal row; preserve the actual client-download action and the original copy/link/import handlers.
- Android: when four actions are available, one full-width primary action above three equal actions. No placeholder controls if an action does not exist for a protocol.
- OpenVPN, WireGuard, AmneziaWG: preserve genuine config-file download and multi-server ZIP routes. Other protocols retain their original compatible-app import actions.
- Restore the supported protocol-specific client install links (including Karing, Sudoku, TrustTunnel, OpenConnect) with device-aware choices.
- Retain unified theme colors, server row layouts, and the mobile server-detail modal.
- No changes intended to VPN runtime, database, node tunnels, or credentials.

### Validation and limits
- Official prebuilt release workflow is responsible for building and hashing the candidate artifact before stable manifest publication.
- Complete interactive visual regression across all supported devices and protocols has not been verified.

## 1.1.0-rc.652 — 2026-11-07

### Connection — user interface and client delivery
- Unified desktop/mobile Connection colors with configured TwinPanel brand palette, including background, header, protocol cards, server rows, footer actions and detail dialog.
- Moved the single device-specific **Download app** action into the existing bottom action bar; removed repeated standalone client-download cards.
- Added client download access for AmneziaWG and TrustTunnel, and removed the unnecessary L2TP/IPsec app-download action.
- Improved OpenVPN/WireGuard/AmneziaWG per-server file download/copy actions while retaining existing config links and credentials.
- Normalized mobile protocol grid to show each name beneath its icon.
- Aligned native and modern server rows and made mobile copy/add buttons readable without overlap.
- Added mobile server-detail modal behavior while keeping original configuration/copy controls.
- Removed unnecessary recurring footer DOM reconciliation.

### Release scope and validation
- UI-only Connection modifications; no intentional changes to VPN runtime, database, credentials, nodes, or tunnels.
- Python/JavaScript syntax, production Connection HTTP 200 and API health HTTP 200 were verified during hotfix deployment.
- **Visual mobile browser automation for all protocols has not been completed.** Publishing and install/update checks are handled by the prebuilt release workflow.

