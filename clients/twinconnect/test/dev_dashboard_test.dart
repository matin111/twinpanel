import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/main_dev.dart';

void main() {
  testWidgets('dev entry starts at dashboard without production login',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 820));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const TwinConnectDevApp());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('devConnectionStatus')), findsOneWidget);
    expect(find.byKey(const Key('devSampleNotice')), findsOneWidget);
    expect(find.byKey(const Key('accountUsername')), findsNothing);
    expect(find.byKey(const Key('appPassword')), findsNothing);
    final connect = tester.widget<FilledButton>(
        find.byKey(const Key('devConnectButton')));
    expect(connect.onPressed, isNull);
    expect(find.byKey(const Key('devProtocol_openvpn')), findsOneWidget);
    expect(find.byKey(const Key('devRefreshServers')), findsOneWidget);
    await tester.tap(find.byKey(const Key('devRefreshServers')));
    await tester.pump();
    expect(find.text('برای دریافت سرورها، ورود به پنل لازم است'), findsOneWidget);
  });

  testWidgets('dev dashboard supports filters without fake connections',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 820));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const TwinConnectDevApp());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('devFilter_wireguard')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('devProtocol_wireguard')), findsOneWidget);
    expect(find.byKey(const Key('devProtocol_openvpn')), findsNothing);
    final connect = tester.widget<FilledButton>(
        find.byKey(const Key('devConnectButton')));
    expect(connect.onPressed, isNull);
  });
}
