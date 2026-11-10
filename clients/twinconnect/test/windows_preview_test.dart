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

  testWidgets('offline Windows demo opens without user credentials',
      (tester) async {
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('windowsDemoButton')), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('windowsDemoButton')));
    await tester.tap(find.byKey(const Key('windowsDemoButton')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('offlineDemoBanner')), findsOneWidget);
    expect(
      find.textContaining('Sample data only'),
      findsOneWidget,
    );
  });

  testWidgets('offline demo can inspect settings without live VPN engines',
      (tester) async {
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('windowsDemoButton')));
    await tester.tap(find.byKey(const Key('windowsDemoButton')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('vpnSettingsButton')));
    await tester.pumpAndSettle();

    expect(find.text('Advanced VPN settings'), findsOneWidget);
    expect(find.byKey(const Key('vpnNotActiveNotice')), findsOneWidget);
    expect(find.byKey(const Key('vpnMode_fullTunnel')), findsOneWidget);
  });
}
