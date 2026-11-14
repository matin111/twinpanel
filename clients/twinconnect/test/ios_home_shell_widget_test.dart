import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:twinconnect/ios_home_shell.dart';
import 'package:twinconnect/server_inventory.dart';
import 'package:twinconnect/tenant_models.dart';

void main() {
  const brand = BrandPreview(
    namespace: 'TPABC123',
    brandName: 'Matin VPN',
    ownerType: 'owner',
    accountStatus: 'active',
    appUsernamePrefix: 'D',
  );
  const inventory = AppServerInventory(namespace: 'TPABC123', servers: [
    AppServer(id: '1', name: 'Demo Turkey', countryCode: 'TR',
      nodeOnline: true, latencyMs: 83),
  ]);

  testWidgets('iPhone internal shell shows offline home and switches all tabs',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: TwinConnectIphoneShell(
        brand: brand,
        username: 'demo',
        inventory: inventory,
        previewMode: true,
      ),
    ));

    expect(find.byKey(const Key('iphoneConnectDisabled')), findsOneWidget);
    expect(find.text('اتصال برقرار نیست'), findsOneWidget);
    expect(find.byKey(const Key('iosShowcaseNavigation')), findsOneWidget);

    await tester.tap(find.byIcon(Icons.public_rounded).last);
    await tester.pumpAndSettle();
    expect(find.text('Demo Turkey'), findsNothing);
    await tester.tap(find.text('ترکیه'));
    await tester.pumpAndSettle();
    expect(find.text('Demo Turkey'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.tune_rounded).last);
    await tester.pumpAndSettle();
    expect(find.text('Kill Switch'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.person_outline_rounded).last);
    await tester.pumpAndSettle();
    expect(find.text('demo'), findsOneWidget);
    expect(find.textContaining('داده‌های ساختگی'), findsOneWidget);
  });
}
