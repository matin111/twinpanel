import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/live_dashboard.dart';
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

  testWidgets('Quick Connect remains navigable from other pages',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 960);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await tester.pumpWidget(MaterialApp(
      home: TwinConnectLiveDashboard(
        panel: PanelDirectoryEntry(
          namespace: WindowsPreviewFixture.namespace,
          apiOrigin: Uri.parse('https://panel.example.org'),
        ),
        username: 'test-account',
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
      ),
    ));
    await tester.pump();
    await tester.tap(find.byKey(const Key('devNav_locations')));
    await tester.pump();
    expect(find.byKey(const Key('devLocationListingCard')), findsOneWidget);

    await tester.tap(find.byKey(const Key('devNav_home')));
    await tester.pump();
    expect(find.byKey(const Key('liveConnectionStatus')), findsOneWidget);

    await tester.tap(find.byKey(const Key('devNav_locations')));
    await tester.pump();
    await tester.ensureVisible(find.byKey(const Key('devServer_1')));
    await tester.tap(find.byKey(const Key('devServer_1')));
    await tester.pump();
    // Selecting a node is never a no-op, even without a Windows engine.
    expect(find.byKey(const Key('liveConnectionStatus')), findsOneWidget);
    expect(find.byKey(const Key('devLocationListingCard')), findsNothing);
  });
}
