import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/main.dart';
import 'package:twinconnect/vpn_policy.dart';
import 'package:twinconnect/vpn_policy_store.dart';
import 'package:twinconnect/vpn_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('login has language picker but no VPN settings shortcut',
      (tester) async {
    SharedPreferences.setMockInitialValues({
      'twinconnect_ui_language_v1': 'en',
    });
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('vpnSettingsButton')), findsNothing);
    expect(find.byKey(const Key('languagePicker')), findsOneWidget);
    expect(find.byKey(const Key('accountUsername')), findsOneWidget);
    expect(find.byKey(const Key('appPassword')), findsOneWidget);
  });

  testWidgets('advanced network settings expose honest feature availability',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: VpnSettingsScreen(tenant: '', account: ''),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('vpnCapabilityRefresh')), findsOneWidget);
    await tester.scrollUntilVisible(
      find.byKey(const Key('vpnProxyModeUnavailable')), 180,
    );
    final proxy = tester.widget<ListTile>(
      find.byKey(const Key('vpnProxyModeUnavailable')),
    );
    expect(proxy.enabled, isFalse);
    expect(find.byKey(const Key('vpnTunMode')), findsOneWidget);

    await tester.scrollUntilVisible(
      find.byKey(const Key('vpnShareGuideButton')), 180,
    );
    await tester.tap(find.byKey(const Key('vpnShareGuideButton')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('devShareVpnCard')), findsOneWidget);
  });

  testWidgets('draft does not save without an identified account',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: VpnSettingsScreen(tenant: '', account: ''),
    ));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.byKey(const Key('vpnSaveButton')),
      260,
    );
    final save = tester.widget<FilledButton>(
      find.byKey(const Key('vpnSaveButton')),
    );
    expect(save.onPressed, isNull);
  });

  testWidgets('preview disables OS controls and never saves false protections',
      (tester) async {
    const tenant = 'TP0123456789ABCDEF';
    const account = 'TP0123456789ABCDEF_R1_alice';
    await tester.pumpWidget(const MaterialApp(
      home: VpnSettingsScreen(tenant: tenant, account: account),
    ));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.byKey(const Key('vpnKillSwitch')), 180,
    );
    final kill = tester.widget<SwitchListTile>(
      find.byKey(const Key('vpnKillSwitch')),
    );
    expect(kill.onChanged, isNull);
    expect(kill.value, isFalse);
    final dns = tester.widget<SwitchListTile>(
      find.byKey(const Key('vpnDnsGuard')),
    );
    expect(dns.onChanged, isNull);
    expect(dns.value, isFalse);

    await tester.scrollUntilVisible(
      find.byKey(const Key('vpnSaveButton')), 230,
    );
    final save = tester.widget<FilledButton>(
      find.byKey(const Key('vpnSaveButton')),
    );
    expect(save.onPressed, isNull);
    final saved = await const VpnPolicyStore().load(tenant, account);
    expect(saved.killSwitchRequested, false);
    expect(saved.routingMode, VpnRoutingMode.fullTunnel);
  });

}
