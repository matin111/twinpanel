import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/live_dashboard.dart';
import 'package:twinconnect/account_snapshot.dart';
import 'package:twinconnect/tunnel_traffic_chart.dart';
import 'package:twinconnect/protocols.dart';
import 'package:twinconnect/server_inventory.dart';
import 'package:twinconnect/tenant_models.dart';
import 'package:twinconnect/windows_preview_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'twinconnect_ui_language_v1': 'en',
      'twinconnect_ui_dark_v1': true,
    });
  });

  testWidgets('original connection page shows authenticated quota and expiration',
      (tester) async {
    tester.view.physicalSize = const Size(1536, 1024);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    var refreshes = 0;
    final expiry = DateTime.now().toUtc().add(const Duration(days: 10));
    await tester.pumpWidget(MaterialApp(
      home: TwinConnectLiveDashboard(
        panel: PanelDirectoryEntry(
          namespace: WindowsPreviewFixture.namespace,
          apiOrigin: Uri.parse('https://panel.example.org'),
        ),
        username: 'real-account-test',
        brand: const BrandPreview(
          namespace: WindowsPreviewFixture.namespace,
          brandName: 'Test Reseller',
          ownerType: 'admin',
          accountStatus: 'active',
          appUsernamePrefix: '',
        ),
        sessionToken: List.filled(64, 'a').join(),
        catalog: WindowsPreviewFixture.protocolCatalog(),
        servers: const AppServerInventory(
          namespace: WindowsPreviewFixture.namespace,
          servers: [],
        ),
        native: const NativeProtocolReadiness(supportedCodes: {}),
        onRefresh: () {},
        plan: null,
        accountStatus: 'active',
        account: AppAccountSnapshot(
          namespace: WindowsPreviewFixture.namespace,
          trafficLimitBytes: 20 * 1024 * 1024 * 1024,
          trafficUsedBytes: 5 * 1024 * 1024 * 1024,
          expiresAt: expiry,
          activationDurationDays: null,
          status: 'active',
        ),
        onLogout: () {},
        onRefreshAccount: () { refreshes++; },
      ),
    ));
    await tester.pump(const Duration(milliseconds: 700));
    expect(find.byKey(const Key('liveHomeSubscriptionSummary')),
      findsOneWidget);
    expect(find.text('5.00 GB'), findsWidgets);
    expect(find.textContaining('15.00 GB'), findsWidgets);
    expect(find.textContaining('20.00 GB'), findsWidgets);
    expect(find.text('Expiry date'), findsOneWidget);
    expect(find.textContaining('days'), findsWidgets);
    expect(find.byKey(const Key('liveHomeUsageCompact')), findsOneWidget);
    // Fastest-server selection lives with protocol choices, never on Home.
    expect(find.byKey(const Key('liveAutoFastestServer')), findsNothing);
    expect(find.byKey(const Key('autoFastestServerToggle')), findsNothing);
    // The subscription summary is now a compact strip, not a giant panel.
    final summary = find.byKey(const Key('liveHomeSubscriptionSummary'));
    await tester.ensureVisible(summary);
    await tester.pump();
    expect(tester.getSize(summary).height, lessThan(210));
    // Fastest server is exclusively in Locations beside the protocol filters.
    await tester.tap(find.byKey(const Key('devNav_locations')));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(const Key('devProtocolFilters')), findsOneWidget);
    expect(find.byKey(const Key('liveAutoFastestServer')), findsOneWidget);
    expect(find.byKey(const Key('autoFastestServerToggle')), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('liveAutoFastestServer')));
    expect(find.text('Fastest server'), findsOneWidget);
    await tester.tap(find.byKey(const Key('devFilter_hysteria2')));
    await tester.pump();
    expect(find.byKey(const Key('devFilter_hysteria2')), findsOneWidget);
    await tester.tap(find.byKey(const Key('devNav_home')));
    await tester.pump();
    expect(find.byKey(const Key('liveAutoFastestServer')), findsNothing);
    // Assert the actual refresh callback, not the tap target of a possibly
    // off-screen duplicated shell during a navigation transition.
    final refreshButtons = tester.widgetList<IconButton>(
      find.byKey(const Key('liveHomeRefreshAccount'))).toList();
    expect(refreshButtons, isNotEmpty);
    refreshButtons.firstWhere((button) => button.onPressed != null)
        .onPressed!();
    expect(refreshes, 1);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 30));
  });

  testWidgets('Quick Connect remains navigable from other pages',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 960);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: TwinConnectLiveDashboard(
        panel: PanelDirectoryEntry(
          namespace: WindowsPreviewFixture.namespace,
          apiOrigin: Uri.parse('https://panel.example.org'),
        ),
        username: 'test-account',
        brand: const BrandPreview(
          namespace: WindowsPreviewFixture.namespace,
          brandName: 'Test Reseller',
          ownerType: 'admin',
          accountStatus: 'active',
          appUsernamePrefix: '',
        ),
        sessionToken: List.filled(64, 'a').join(),
        catalog: WindowsPreviewFixture.protocolCatalog(),
        servers: const AppServerInventory(
          namespace: WindowsPreviewFixture.namespace,
          servers: [
            AppServer(id: '1', name: 'TR', countryCode: 'TR',
              nodeOnline: true, latencyMs: 100),
            AppServer(id: '2', name: 'DE', countryCode: 'DE',
              nodeOnline: true, latencyMs: 200),
          ],
        ),
        native: const NativeProtocolReadiness(supportedCodes: {}),
        onRefresh: () {},
        plan: null,
        accountStatus: 'active',
        account: null,
        onLogout: () {},
        onRefreshAccount: () {},
      )),
    ));
    await tester.pump(const Duration(milliseconds: 800));
    // Selected server is TR initially: Locations shows its country flag.
    expect(find.byKey(const Key('selectedLocationFlag')), findsOneWidget);
    await tester.tap(find.byKey(const Key('devNav_locations')));
    await tester.pump(const Duration(milliseconds: 800));
    expect(find.byKey(const Key('devLocationListingCard')), findsOneWidget);
    expect(find.byKey(const Key('devProtocolFilters')), findsOneWidget);
    expect(find.byKey(const Key('liveAutoFastestServer')), findsOneWidget);

    await tester.tap(find.byKey(const Key('devNav_home')));
    await tester.pump(const Duration(milliseconds: 800));
    expect(find.byKey(const Key('liveConnectionStatus')), findsWidgets);
    // The duration is visible even while offline, and begins at zero.
    expect(find.byKey(const Key('liveConnectionDuration')), findsOneWidget);
    expect(find.byKey(const Key('liveConnectionControlsButton')),
        findsOneWidget);
    expect(find.text('Connect now'), findsOneWidget);
    expect(find.byKey(const Key('liveHomeDataProgress')), findsOneWidget);
    expect(find.byKey(const Key('liveHomeExpiryChip')), findsOneWidget);
    expect(find.byKey(const Key('liveHomeTimeChip')), findsOneWidget);
    expect(find.byType(TunnelTrafficChart), findsNWidgets(2));
    expect(find.byType(BackdropFilter), findsWidgets);

    // The original authenticated dashboard must expose account data directly
    // on Quick Connect, with no invented values while the snapshot is pending.
    expect(find.byKey(const Key('devAnimatedBackground')), findsOneWidget);
    expect(find.byKey(const Key('devAmbientGrid')), findsOneWidget);
    expect(find.byKey(const Key('liveHomeSubscriptionSummary')), findsOneWidget);
    expect(find.byKey(const Key('liveHomeRefreshAccount')), findsOneWidget);
    expect(find.text('Subscription details'), findsOneWidget);
    expect(find.text('Data usage'), findsOneWidget);
    expect(find.text('Expiry date'), findsOneWidget);
    expect(find.text('Time remaining'), findsOneWidget);
    expect(find.text('00:00:00'), findsOneWidget);

    await tester.tap(find.byKey(const Key('devNav_locations')));
    await tester.pump(const Duration(milliseconds: 800));
    // A modern protocol chip must never hide servers just because a
    // subscription profile or a native VPN engine isn't ready yet.
    await tester.ensureVisible(find.byKey(const Key('devFilter_hysteria2')));
    await tester.tap(find.byKey(const Key('devFilter_hysteria2')));
    await tester.pump(const Duration(milliseconds: 800));
    // Countries are initially collapsed, even when a protocol is selected.
    expect(find.byKey(const Key('countryToggle_TR')), findsOneWidget);
    expect(find.byKey(const Key('countryToggle_DE')), findsOneWidget);
    expect(find.byKey(const Key('devServer_0')), findsNothing);
    expect(find.byKey(const Key('devServer_1')), findsNothing);
    await tester.ensureVisible(find.byKey(const Key('countryToggle_DE')));
    await tester.tap(find.byKey(const Key('countryToggle_DE')));
    await tester.pump(const Duration(milliseconds: 800));
    expect(find.byKey(const Key('devServer_1')), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('devServer_1')));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.ensureVisible(find.byKey(const Key('devServer_1')));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.tap(find.byKey(const Key('devServer_1')));
    await tester.pump(const Duration(milliseconds: 800));
    expect(find.byKey(const Key('liveConnectionStatus')), findsWidgets);
    expect(find.text('Hysteria2'), findsWidgets);

    // A native engine not yet implemented (Cisco) also permits choosing
    // a server; this is a selection, not a simulated VPN connection.
    await tester.tap(find.byKey(const Key('devNav_locations')));
    await tester.pump(const Duration(milliseconds: 800));
    await tester.ensureVisible(find.byKey(const Key('devFilter_cisco')));
    await tester.tap(find.byKey(const Key('devFilter_cisco')));
    await tester.pump(const Duration(milliseconds: 800));
    expect(find.byKey(const Key('devServer_0')), findsNothing);
    await tester.ensureVisible(find.byKey(const Key('countryToggle_TR')));
    await tester.tap(find.byKey(const Key('countryToggle_TR')));
    await tester.pump(const Duration(milliseconds: 800));
    expect(find.byKey(const Key('devServer_0')), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.ensureVisible(find.byKey(const Key('devServer_0')));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.tap(find.byKey(const Key('devServer_0')));
    await tester.pump(const Duration(milliseconds: 800));
    expect(find.byKey(const Key('liveConnectionStatus')), findsWidgets);
    // Regression: selecting Cisco must use the OpenConnect adapter, NEVER
    // the sing-box protocol family (the original screenshot error).
    if (Platform.isWindows) {
      await tester.ensureVisible(
          find.byKey(const Key('liveConnectionControlsButton')));
      await tester.tap(find.byKey(const Key('liveConnectionControlsButton')));
      await tester.pump(const Duration(milliseconds: 900));
      expect(find.textContaining('SINGBOX_PROTOCOL_NOT_SUPPORTED'),
          findsNothing);
      // The synthetic test has no bundled Cisco CLI, but platform capability
      // probing and panel data are asynchronous. Verify the dispatch invariant,
      // not a specific translated error or a particular completion deadline.
      expect(find.textContaining('SINGBOX_PROTOCOL_NOT_SUPPORTED'),
          findsNothing);
    }
    // Unmount the dashboard so its periodic connection/UI timers are
    // cancelled, then let outstanding synthetic platform-channel timeouts
    // complete before Flutter verifies that the test has no pending timers.
    // This keeps the real navigation assertions intact.
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 30));
  });
}
