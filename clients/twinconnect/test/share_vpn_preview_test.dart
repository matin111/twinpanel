import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/share_vpn_preview.dart';

void main() {
  testWidgets('Share VPN is a glass preview, not a live Windows hotspot',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1000, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ShareVpnPreview(dark: true, persian: true),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('devShareVpnCard')), findsOneWidget);
    expect(find.byKey(const Key('devWifiSettingsCard')), findsOneWidget);
    expect(find.byKey(const Key('devShareVpnGuideCard')), findsOneWidget);
    final toggle = tester.widget<Switch>(
      find.byKey(const Key('devShareVpnSwitch')));
    expect(toggle.value, isFalse);
    expect(toggle.onChanged, isNull);
  });

  testWidgets('Share VPN guide explains native requirements',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1000, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ShareVpnPreview(dark: true, persian: false),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Share VPN guide'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('devShareVpnGuide')), findsOneWidget);
  });
}
