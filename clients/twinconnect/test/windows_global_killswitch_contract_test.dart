import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/native_vpn_bridge.dart';
import 'package:twinconnect/vpn_policy.dart';

void main() {
  test('Windows WFP preflight is read-only and never enables global filtering', () {
    final header = File('native/windows/twinconnect_global_killswitch.h')
        .readAsStringSync();
    expect(header, contains('FwpmEngineOpen0('));
    expect(header, contains('FWPM_SESSION_FLAG_DYNAMIC'));
    expect(header, contains('FwpmEngineClose0(engine)'));
    expect(header, contains('flutter::EncodableValue(false)'));
    expect(header, isNot(contains('FwpmFilterAdd')));
    expect(header, isNot(contains('FwpmFilterDelete')));
    expect(header, isNot(contains('FwpmSubLayerAdd')));
    expect(header, isNot(contains('FWPM_FILTER_FLAG_PERSISTENT')));
  });

  test('native bridge installs only a read-only guard status method', () {
    final install = File('tools/install_windows_native.py')
        .readAsStringSync();
    expect(install, contains('twinconnect_global_killswitch.h'));
    expect(install, contains('getGlobalKillSwitchStatus'));
    expect(install, contains('twinconnect_global_killswitch::Preflight()'));
    expect(install, isNot(contains('setGlobalKillSwitchEnabled')));
  });

  test('system-wide kill switch must not be claimed through saved preferences', () {
    const policy = VpnPolicy(killSwitchRequested: true);
    final native = NativeVpnCapabilities(
      platform: VpnPlatform.windows,
      engineReady: true,
      fullTunnel: true,
      dnsGuard: true,
      ipv6Guard: true,
      killSwitchEnforced: false,
    );
    expect(policy.connectionProblems(native),
        contains('KILL_SWITCH_NOT_ENFORCED'));
    expect(
      () => NativeVpnBridge.requireSafeToConnect(policy, native),
      throwsStateError,
    );
  });

  test('settings cannot activate global guard without enforcement', () {
    final screen = File('lib/vpn_settings.dart').readAsStringSync();
    expect(screen, contains('NativeVpnBridge.globalKillSwitchStatus()'));
    expect(screen, contains('Protection service not ready'));
    expect(screen, contains('onChanged: null'));
    expect(screen, isNot(contains('setGlobalKillSwitchEnabled')));
  });
}
