# TwinPanel Changelog

## 1.1.0-rc.677 — 2026-11-08

### Faster public Connection page, preserving all protocols and account data
- Eliminated a SQL N+1 pattern: request-local strong Node identity map, memoized tunnel and eligibility checks, plus a single bulk NodeProtocolConfig read instead of hundreds of individual DB lookups. No globally cached user configuration or changed account mutation paths.
- Changed QR rendering from huge inline SVG path strings to equivalent high-quality, browser-scannable compact PNG images using the existing pinned qrcode[pil] dependency and QR best-mask selection, without changing source configuration strings.
- Production performance profiling: database reads reduced from ~551 to 90 before bulk config fetch, and first render significantly reduced. Compressed response size reduced from ~340 KB to ~163 KB; exact end-to-end latency depends on concurrent provisioning/updater load.
- Added `test_connection_render_fast_v103.py` and GitHub CI regression coverage for request-scoped caches, QR validity, live-state freshness and English UI digits.
- Public /live traffic and session telemetry remain uncached; credentials, limits, subscriptions, live VPN services, downloads and copy actions unchanged.

## 1.1.0-rc.674 — 2026-11-08

### Real connection/accounting and English digits on Connection
- Persist the fast OpenVPN runtime telemetry mapping for genuinely observed node clients. A malformed imported subscription can no longer roll back otherwise valid node usage and live-session records. L2TP, Cisco and Xray reconciliation use per-client savepoints to avoid node-wide account rollback; collectors prioritize OpenVPN/L2TP rather than the expensive general scan.
- Filter runtime device reconciliation by relevant protocol instead of scanning every protocol for every client. This reduces workload and protects live-session statistics from process timeouts.
- Repair the L2TP PPP session hooks on existing affected nodes (1 and 14) without resetting VPN services; the versioned hook installation code remains in the repository.
- Treat Xray (V2Ray) counters correctly as **recent traffic activity**, not a verified live socket. Account for the slower collector cadence, render the honest status «فعال اخیراً», and highlight only country codes supported by recent live session/traffic evidence.
- Format every visible number on the public Connection UI with English digits on desktop/mobile, preserving raw config links, copyable credentials, and uploaded profile content.
- Regression suite `backend/tests/test_connection_live_telemetry_v101.py` (five checks, including JavaScript syntax); verify live API and account counters after deployment.
- Scope: UI and usage telemetry fixes; no plan duration, expiry, limit, subscription credentials, or VPN listener configurations are rewritten.

## 1.1.0-rc.669 — 2026-11-08

### Remove empty black strip in Connection popups, light and dark
- Remove empty legacy `v51-multi-card` / `v52-multi-card` containers after their real download/copy buttons have been relocated into the unified footer. Their old blank background previously appeared as a black horizontal bar above the action buttons in both Light and Dark themes.
- Provide matching CSS empty-wrapper suppression for both color schemes; **do not remove any real download, copy, add or secondary action**, and retain the responsive protocol popup.
- Restore sufficient foreground contrast for Light mode protocol headings, server names, labels and secondary action buttons. This is a theme-independent structural removal of the empty containers, not just recoloring.
- Post-fix DOM tests over all 16 protocol panels: zero leftover `v52-multi-card` containers; all 16 protocol modal open/close tests pass; V2Ray retains Copy All, Copy Link, Download Karing, Download v2rayN and Add All secondary action. Live Connection endpoint returned HTTP 200.
- Real-browser visual testing remains pending. No VPN node, user, subscription or credential changes.

## 1.1.0-rc.667 — 2026-11-08

### Connection panel theme parity and real light/dark rendering
- Restore a genuinely readable **Light mode**. The page previously stayed navy despite the theme switch because the older reference layout hard-coded many background and text colors with `!important`.
- Harmonize the complete Connection surface with TwinPanel's configurable primary/secondary brand colors, already provided as `--p` and `--s` from the server's branding settings. No hard-coded purple or blue accents in the new skin.
- Use matching theme surfaces for body, top header, subscriber/traffic block, category tabs, protocol cards, flags/rows, protocol popup, detail popup, client/footer controls, and text states in **both** light and dark.
- Keep the existing persisted theme-switch behavior and user preference. Preserve all protocol interaction handlers, copy/download buttons, category and country filters, and mobile popup-only layout.
- Tested Python/JavaScript validity, live Connection HTTP 200 with the branded root colors, active API/web HTTP 200 and synthetic popup click/close for all 16 protocols. Full browser screenshot verification of light/dark colors remains pending.
- No changes to subscriptions, credential data, nodes, tunnels, or transport configuration.

## 1.1.0-rc.665 — 2026-11-08

### Mobile protocol popup only, typography refresh
- Fix mobile legacy inline protocol-panel expansion that remained visible below the grid despite the popup. Window-level capture intercepts protocol-card clicks before legacy document handlers, routing to the original panel's modal exclusively.
- Hide every unmounted protocol panel with high-specificity CSS, including panels retaining legacy `active` or `v36-open` classes. The original panel is visible only inside the protocol modal; close restores it without losing configuration actions.
- Refresh protocol card title typography using system font stack Inter/Segoe UI/Tahoma, stronger balanced text, improved spacing and responsive phone sizing. No font files or external webfont dependencies.
- Live page responded HTTP 200. Synthetic DOM click/open/close test passed for all 16 protocols. Real mobile-browser visual validation is still pending.
- Retains rc.664 protocol modal, per-country filters and rc.663 four-action V2Ray footer. No account, VPN runtime or node mutations.

## 1.1.0-rc.664 — 2026-11-07

### Protocol cards open full interactive popup
- Clicking any protocol card now opens the **entire protocol's original panel** in a responsive, scrollable modal on both mobile and desktop. Protocol content no longer expands below the grid.
- Keep the real original DOM node, config-copy buttons, download actions, country filters and live event listeners intact; on closing, move the panel back to its original location.
- Supports close button, backdrop click and Escape; preserves focus and restores page scrolling.
- Retains the rc.663 V2Ray four-button footer: Copy all configurations, Copy subscription link, Download Karing and Download v2rayN.
- Deployed and verified on the live server. Synthetic DOM click test succeeded for all 16 protocol cards (modal opens with the correct original panel and closes/restores).
- Real-device mobile visual browser validation remains pending. No VPN runtime, account, subscription or node data changed.

## 1.1.0-rc.663 — 2026-11-07

### Restore V2Ray copy-all in the four-button Windows footer
- Display **Copy all configurations** directly alongside **Copy subscription link**, **Download Karing**, and **Download v2rayN**; no longer hide copy-all under "Other configuration formats".
- Preserve the actual import-all to Karing control in expandable secondary actions without removing its original event handler.
- When normalizing buttons, include previously nested secondary actions to prevent repeated reconciliation from dropping copy-all or import-all.
- Live Connection endpoint returned HTTP 200. DOM smoke test confirmed the four visible actions are exactly `copy, link, app, client`, with real Karing and v2rayN download URLs, and `add` retained under extras.
- No VPN nodes, config-generation routines, accounts or database values changed.

## 1.1.0-rc.662 — 2026-11-07

### Connection mobile category, country selector, popup and V2Ray footer parity
- Fix the **Recommended / Modern / Classic / All protocols** mobile category selector: enforce actual protocol-card visibility with `hidden`, a dedicated data flag and a high-specificity display rule that wins over legacy mobile `display:flex!important` declarations. Keep exactly one eligible protocol panel active after category changes.
- Replace duplicated V2Ray country bars with one consistent tab row and filter the actual V2Ray node cards, retaining selected country through async rerenders.
- Correct modern protocols (AnyTLS, Naive, TUIC, ShadowTLS, Snell, etc.) to filter the **server rows**, not just style the selected country chip. Resolve real country code from the server tab, its flag or server label. **All** restores every node.
- Intercept connection-information clicks before old inline expand handlers, and move the actual detail/control nodes to an accessible, closable modal on mobile and desktop; preserve original clipboard actions.
- Put the Windows v2rayN download link in the same four-action footer row as Karing and connection actions. Preserve copy-all and other formats inside expandable secondary actions rather than creating a fifth footer item.
- Keep all named client-download actions, one-flag normalization for classic protocols, and rc.661 updater improvements.
- Live API returned HTTP 200. Node-based synthetic DOM tests: V2Ray DE=2 / all=4; five modern protocols DE=2 / all=4; modal click opens/closes with one real detail node; category counts Classic=5, Modern=11, Recommended=5, All=16 and exactly one active protocol/panel. Browser visual/interaction validation on a real phone is still outstanding.

## 1.1.0-rc.661 — 2026-11-07

### Native flags and official updater reliability
- Fix duplicate country flags on native OpenVPN, WireGuard, AmneziaWG and Cisco server rows: retain the real V76 SVG artwork and do not add a second V80 image. Remove duplicate legacy Unicode flag glyphs from node labels without changing server IDs.
- Replace PAM-based `runuser` probes in the official prebuilt updater with direct unprivileged `setpriv` permission checks for Next.js server.js readability and cache writability. This avoids intermittent five-second `runuser` timeouts that caused official rc.659 and rc.660 install rollbacks.
- Keep all rc.660 changes: desktop/mobile connection-information modals, consistent V2Ray country filter flags, Cisco full-width download, named client installers and the dedicated Windows v2rayN download.
- Verified `setpriv` checks against the current web installation (both passed); Python and JavaScript syntax checks passed. Full interactive browser regression is still outstanding.

## 1.1.0-rc.660 — 2026-11-07

### Unified Connection countries, information dialogs, and named client downloads
- Open the existing server-connection details modal on desktop as well as mobile, without copying secrets or changing the original controls.
- Restore country-code tabs and one country flag per V2Ray/Xray node, using live public /sub/meta country codes. The **All** tab shows all delivered nodes; country tabs correctly filter only matching nodes.
- Preserve dynamically reloaded V2Ray node lists, and rebuild filters if new nodes replace existing cards.
- Normalize duplicated legacy Unicode/image flag displays for classic protocol nodes.
- Make the sole Cisco/OpenConnect client installer action span the entire footer row.
- Give every supported install action a clear client name (OpenVPN, WireGuard, AmneziaWG, OpenConnect, TrustTunnel, Sudoku or Karing) instead of generic "Download app".
- Provide a separate visible **Download v2rayN** link on Windows alongside V2Ray's existing Karing client action. The v2rayN link points to the project's release downloads.
- Retain original copy/import/download buttons, desktop four-column actions, Android 1+3 footer and panel branding.
- JavaScript syntax passed, the Connection endpoint returned HTTP 200 and a synthetic DOM test verified country filtering (4 total nodes, 2 DE nodes), V2Ray flag buttons, v2rayN link, Cisco full-width action marker and named native client buttons.
- Complete interactive browser visual testing across all protocols remains pending. No changes to VPN nodes, tunnels, credentials or config generation.

## 1.1.0-rc.659 — 2026-11-07

### Connection client-download button restored
- Stop moving hidden legacy client-card anchors into the active Connection footer. Instead create a clean, visible, keyboard-accessible action with the actual platform-specific download endpoint and no inherited hidden/inline display styles.
- Preserve the original protocol actions and four equal-width Windows footer buttons; retain Android one full-width primary action and three secondary actions.
- Verified with a synthetic DOM containing a hidden legacy app anchor that all 14 tested protocols display a distinct **دانلود برنامه** action with a valid protocol/device-specific endpoint, class and text, no `hidden` attribute or inline display suppression.
- Download endpoints for Karing, OpenVPN, WireGuard, AmneziaWG, OpenConnect, TrustTunnel and Sudoku were checked from the running server. L2TP/IPsec uses an operating-system built-in client and does not require a standalone application installer.
- This patch does not change VPN credentials, tunnels, protocol runtime or database schema. Interactive browser testing of every action remains pending.

## 1.1.0-rc.658 — 2026-11-07

### HTTP request database pool stability
- Increase the independent HTTP request DB connection pool from 10+6 overflow to 16+16 overflow, with a 10-second acquisition timeout, to better handle simultaneous node polling and Connection/admin requests.
- Preserve the separate background engine and existing database credentials, schema, and VPN runtime.
- The combined configured engine capacities remain below the standard PostgreSQL max_connections of 100, assuming no additional external clients consume the remaining connections.
- After live hotfix, API and web health returned HTTP 200; recurring long-lived idle transactions are still under investigation.
- Includes all rc.657 unified footer action fixes for every supported protocol.

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

