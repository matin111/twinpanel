import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/vpn_policy.dart';

void main() {
  test('Android split routing is saved only with actual selected apps', () {
    const selected = VpnPolicy(
      routingMode: VpnRoutingMode.onlySelectedApps,
      appIds: ['com.android.chrome'],
    );
    expect(selected.draftProblems(VpnPlatform.android), isEmpty);

    const missing = VpnPolicy(routingMode: VpnRoutingMode.excludeSelectedApps);
    expect(missing.draftProblems(VpnPlatform.android), contains('NO_SELECTED_APPS'));
  });

  test('in-app Kill Switch never advertises per-app bypass as protected', () {
    const conflicting = VpnPolicy(
      routingMode: VpnRoutingMode.excludeSelectedApps,
      appIds: ['com.android.chrome'],
      killSwitchRequested: true,
    );
    expect(conflicting.draftProblems(VpnPlatform.android),
        contains('SPLIT_TUNNEL_GUARD_CONFLICT'));
  });

  test('every shared native Android tunnel Builder receives app filter', () {
    final native = File('native/android/kotlin/com/twinpanel/twinconnect/'
        'SharedTunVpnService.kt').readAsStringSync();
    expect(native, contains('fun configureAppRouting(context: Context, mode: String'));
    expect(native, contains('builder.addAllowedApplication(it)'));
    expect(native, contains('builder.addDisallowedApplication(it)'));
    expect(native, contains('routingBuilder(Builder())'));
    expect(native, contains('routingBuilder(Builder().setSession(name))'));
    expect(native, contains('routingBuilder(Builder().setSession("TwinConnect WireGuard"))'));
    expect(native, contains('routingBuilder(Builder().setSession("TwinConnect AmneziaWG"))'));

    final bridge = File('lib/native_vpn_bridge.dart').readAsStringSync();
    expect(bridge, contains('configureAndroidAppRouting(VpnPolicy policy)'));
    final connection = File('lib/android_connection_card.dart').readAsStringSync();
    expect(connection, contains('await NativeVpnBridge.configureAndroidAppRouting(policy);'));
  });

  test('launcher app picker is permission-minimal and settings are persisted', () {
    final installer = File('tools/install_android_native.py').readAsStringSync();
    expect(installer, contains('android.intent.category.LAUNCHER'));
    expect(installer, isNot(contains('android:name="android.permission.QUERY_ALL_PACKAGES"')));
    final host = File('native/android/kotlin/com/twinpanel/twinconnect/'
        'MainActivity.kt').readAsStringSync();
    expect(host, contains('"listLaunchableApps" -> onWorker(result)'));
    expect(host, contains('"configureAppRouting" -> onWorker(result)'));
    expect(host, contains('"getAndroidVpnNetworkDiagnostics" -> onWorker(result)'));

    final settings = File('lib/vpn_settings.dart').readAsStringSync();
    expect(settings, contains('_selectRouting(VpnRoutingMode mode)'));
    expect(settings, contains('await _policyStore.save(widget.tenant, widget.account, updated)'));
    expect(settings, contains('getAndroidVpnNetworkDiagnostics'));
    expect(settings, contains('if (Platform.isAndroid) ...['));
  });
}
