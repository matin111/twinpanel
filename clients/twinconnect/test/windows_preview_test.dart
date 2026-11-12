import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/main.dart';
import 'package:twinconnect/windows_preview_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({
        'twinconnect_ui_language_v1': 'en',
      }));

  test('offline sample has 16 protocols without any real account secrets', () {
    final brand = WindowsPreviewFixture.brand();
    final catalog = WindowsPreviewFixture.protocolCatalog();

    expect(brand.namespace, WindowsPreviewFixture.namespace);
    expect(brand.brandName, 'TwinConnect Demo');
    expect(brand.accountStatus, 'demo');
    expect(catalog.entries.length, 16);
    expect(catalog.entries.map((e) => e.protocol.code).toSet().length, 16);
    expect(catalog.entries.every((e) => e.selected), true);
    expect(catalog.entries.every((e) => !e.clientEngineReady), true);
    expect(catalog.entries
        .where((e) => e.configRecordPresent)
        .map((e) => e.protocol.code)
        .toSet(), {'wireguard', 'cisco', 'v2ray'});
  });

  testWidgets('offline desktop preview has honest empty telemetry and tabs',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1536, 1024));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();

    await tester.drag(find.byType(ListView).first, const Offset(0, -260));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('windowsDemoButton')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('referenceDesktopShell')), findsOneWidget);
    expect(find.text('Network status'), findsOneWidget);
    expect(find.textContaining('Tunnel inactive'), findsOneWidget);
    expect(find.textContaining('Not connected'), findsOneWidget);
    expect(find.text('204.10.192.96'), findsNothing);
    expect(find.text('133 ms'), findsNothing);

    await tester.tap(find.byKey(const Key('referenceNav1')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Offline preview:'), findsOneWidget);
    await tester.tap(find.byKey(const Key('referenceNav0')));
    await tester.pumpAndSettle();
    expect(find.text('Quick Connect'), findsOneWidget);
  });

  testWidgets('desktop settings still opens existing real settings page',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1536, 1024));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView).first, const Offset(0, -260));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('windowsDemoButton')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('referenceSettingsButton')));
    await tester.pumpAndSettle();

    expect(find.text('Advanced VPN settings'), findsOneWidget);
    expect(find.byKey(const Key('vpnNotActiveNotice')), findsOneWidget);
    expect(find.byKey(const Key('vpnMode_fullTunnel')), findsOneWidget);
  });
}
