import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/main.dart';
import 'package:twinconnect/vpn_policy.dart';
import 'package:twinconnect/vpn_policy_store.dart';
import 'package:twinconnect/vpn_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.twinpanel.twinconnect/vpn');
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      // Deterministic native availability in UI tests: no plugin timeout
      // and no fabricated enforcement. Real OS behavior is tested separately.
      if (call.method == 'getCapabilities') return null;
      if (call.method == 'getGlobalKillSwitchStatus') {
        return <String, Object>{
          'contractVersion': 1,
          'wfpAvailable': false,
          'serviceInstalled': false,
          'armed': false,
          'enforcedV4': false,
          'enforcedV6': false,
          'recoveryVerified': false,
          'reason': 'TEST_UNAVAILABLE',
        };
      }
      return null;
    });
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  testWidgets('login stays simple and has no settings shortcut', (tester) async {
    SharedPreferences.setMockInitialValues({'twinconnect_ui_language_v1': 'en'});
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('vpnSettingsButton')), findsNothing);
    expect(find.byKey(const Key('languagePicker')), findsOneWidget);
    expect(find.byKey(const Key('accountUsername')), findsOneWidget);
    expect(find.byKey(const Key('appPassword')), findsOneWidget);
  });

  testWidgets('one page shows real diagnostics without unsupported controls', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: VpnSettingsScreen(tenant: '', account: ''),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('vpnCapabilityRefresh')), findsOneWidget);
    expect(find.byKey(const Key('vpnDiagnosticsDisclosure')), findsOneWidget);
    // The passive diagnostic cards are lazily built by ExpansionTile;
    // verify the disclosure exists without depending on offscreen children.
    expect(find.byKey(const Key('vpnDiagnosticsCard')), findsOneWidget);
    expect(find.byKey(const Key('vpnSystemProxyCard')), findsOneWidget);
    expect(find.byKey(const Key('vpnSystemProxyToggle')), findsOneWidget);
    expect(find.byKey(const Key('vpnTunMode')), findsOneWidget);
    expect(find.byKey(const Key('vpnRoutingIncludeApps')), findsOneWidget);
    expect(find.byKey(const Key('vpnRoutingExcludeApps')), findsOneWidget);
    expect(find.byKey(const Key('vpnSharingUnavailable')), findsNothing);
    expect(find.byKey(const Key('vpnSaveButton')), findsNothing);
  });

  testWidgets('kill switch remains disabled until native WFP service exists', (tester) async {
    const tenant = 'TP0123456789ABCDEF';
    const account = 'TP0123456789ABCDEF_R1_alice';
    await tester.pumpWidget(const MaterialApp(
      home: VpnSettingsScreen(tenant: tenant, account: account),
    ));
    await tester.pumpAndSettle();
    // Legacy system-wide toggle is removed; independent app-scoped guard
    // is available on Windows only and never claims protection on Linux.
    expect(find.byKey(const Key('vpnKillSwitch')), findsNothing);
    if (Platform.isWindows) {
      final kill = tester.widget<Switch>(
        find.byKey(const Key('vpnSelectedAppKillSwitch')));
      expect(kill.onChanged, isNull);
      expect(kill.value, isFalse);
    }
    final policy = await const VpnPolicyStore().load(tenant, account);
    expect(policy.killSwitchRequested, false);
    expect(policy.routingMode, VpnRoutingMode.fullTunnel);
  });

  testWidgets('question mark opens help without navigating away', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: VpnSettingsScreen(tenant: '', account: ''),
    ));
    await tester.pumpAndSettle();
    final details = find.byTooltip('Details');
    expect(details, findsWidgets);
    await tester.tap(details.first);
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.byType(VpnSettingsScreen), findsOneWidget);
  });
}
