import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/main_dev.dart';
import 'package:twinconnect/protocols.dart';

void main() {
  Future<void> openLocations(WidgetTester tester) async {
    await tester.tap(find.byKey(const Key('devNav_locations')));
    await tester.pumpAndSettle();
  }

  testWidgets('dev starts in premium four-screen dashboard without login',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const TwinConnectDevApp());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('devAnimatedBackground')), findsOneWidget);
    expect(find.byKey(const Key('devAmbientGrid')), findsOneWidget);
    expect(find.byKey(const Key('devPageTransition')), findsOneWidget);
    expect(find.byType(AnimatedSwitcher), findsWidgets);
    expect(find.byKey(const Key('devConnectionStatus')), findsOneWidget);
    expect(find.byKey(const Key('devConnectionStats')), findsOneWidget);
    expect(find.text('— ms'), findsWidgets);
    expect(find.text('— B/s'), findsNWidgets(2));
    expect(find.byKey(const Key('devSampleNotice')), findsOneWidget);
    for (final page in ['home', 'locations', 'settings', 'account']) {
      expect(find.byKey(Key('devNav_$page')), findsOneWidget);
    }
    expect(find.byKey(const Key('accountUsername')), findsNothing);
    expect(find.byKey(const Key('appPassword')), findsNothing);
    expect(tester.widget<FilledButton>(
      find.byKey(const Key('devConnectButton'))).onPressed, isNull);
    expect(tester.widget<Switch>(
      find.byKey(const Key('devAutoBestServer'))).onChanged, isNull);

    await openLocations(tester);
    expect(find.byKey(const Key('devRefreshServers')), findsOneWidget);
    expect(find.byKey(const Key('devProtocolFilters')), findsOneWidget);
    expect(find.byKey(const Key('devLocationListingCard')), findsOneWidget);
    expect(find.byKey(const Key('devFilter_openvpn')), findsOneWidget);

    await tester.tap(find.byKey(const Key('devRefreshServers')));
    await tester.pump();
    expect(find.text('برای دریافت سرورها وارد حساب شوید'), findsOneWidget);
  });

  testWidgets('premium glass layout pins connection left and stats right',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const TwinConnectDevApp());
    await tester.pumpAndSettle();

    final connect = tester.getTopLeft(
      find.byKey(const Key('devConnectionStatus')));
    final network = tester.getTopLeft(
      find.byKey(const Key('devConnectionStats')));
    expect(connect.dx, lessThan(network.dx));
    expect(find.byKey(const Key('devAutoSelectCard')), findsOneWidget);
    expect(find.byKey(const Key('devLocationsCard')), findsOneWidget);
    expect(find.byType(BackdropFilter), findsWidgets);

    await tester.tap(find.byKey(const Key('devLanguageToggle')));
    await tester.pumpAndSettle();
    final englishConnect = tester.getTopLeft(
      find.byKey(const Key('devConnectionStatus')));
    final englishNetwork = tester.getTopLeft(
      find.byKey(const Key('devConnectionStats')));
    expect(englishConnect.dx, lessThan(englishNetwork.dx));
  });

  testWidgets('all 16 canonical protocols appear in horizontal filter',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const TwinConnectDevApp());
    await tester.pumpAndSettle();
    await openLocations(tester);
    expect(VpnProtocols.all.length, 16);
    expect(find.byKey(const Key('devProtocolFilters')), findsOneWidget);
    expect(find.byType(ChoiceChip), findsNWidgets(17));
    expect(find.byKey(const Key('devFilter_sudoku')), findsOneWidget);
    await tester.tap(find.byKey(const Key('devFilter_wireguard')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Netherlands'), findsOneWidget);
    expect(find.textContaining('Germany'), findsNothing);
  });

  testWidgets('light mode and account and settings remain navigable',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const TwinConnectDevApp());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('devThemeToggle')));
    await tester.pumpAndSettle();
    expect(Theme.of(tester.element(find.byKey(const Key('devNav_home'))))
        .brightness, Brightness.light);
    await tester.tap(find.byKey(const Key('devNav_settings')));
    await tester.pumpAndSettle();
    expect(find.text('Kill Switch'), findsOneWidget);
    expect(find.byKey(const Key('devSettingsGlassHeader')), findsOneWidget);
    expect(find.byKey(const Key('devSettingsAppearanceCard')), findsOneWidget);
    expect(find.byType(BackdropFilter), findsWidgets);
    await tester.tap(find.byKey(const Key('devNav_account')));
    await tester.pumpAndSettle();
    expect(find.text('حساب آزمایشی'), findsWidgets);
    expect(find.byType(BackdropFilter), findsWidgets);
  });
}
