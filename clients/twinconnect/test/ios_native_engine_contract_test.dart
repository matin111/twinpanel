import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/protocols.dart';

void main() {
  test('iOS native bridge fails closed until signed extension engines exist', () {
    final swift = File('ios_native/TwinConnectIOSVpnBridge.swift')
        .readAsStringSync();
    final native = File('lib/native_vpn_bridge.dart').readAsStringSync();
    final provider = File('ios_native/PacketTunnelProvider.swift')
        .readAsStringSync();
    expect(swift, contains('"engineReady": wireGuardReady'));
    expect(swift, contains('"fullTunnel": wireGuardReady'));
    expect(swift, contains('TwinConnectIOSVPNControl.backendLinked()'));
    expect(swift, contains('NETunnelProviderManager.loadAllFromPreferences'));
    expect(swift, contains('"verified": false'));
    expect(native, contains('os != VpnPlatform.ios'));
    expect(provider, contains('NEPacketTunnelProvider'));
    final wireguard = File('ios_native/TwinConnectWireGuardEngine.swift')
        .readAsStringSync();
    expect(provider, contains('IOS_PROTOCOL_ENGINE_NOT_INSTALLED'));
    expect(wireguard, contains('TwinConnectWireGuardError.engineNotLinked'));
    expect(provider, isNot(contains('setTunnelNetworkSettings(')));
  });

  test('sixteen canonical protocol IDs remain shared by all platforms', () {
    expect(VpnProtocols.all.length, 16);
    expect(VpnProtocols.all.map((e) => e.code).toSet().length, 16);
    expect(VpnProtocols.byCode('xray')?.code, 'v2ray');
    expect(VpnProtocols.byCode('hy2')?.code, 'hysteria2');
    expect(VpnProtocols.byCode('openconnect')?.code, 'cisco');
  });

  test('macOS CI compiles iOS provider source, not a falsely signed IPA', () {
    final workflow = File('../../.github/workflows/twinconnect-ios-simulator.yml')
        .readAsStringSync();
    expect(workflow, contains('ios_native/TwinConnectIOSVpnBridge.swift'));
    expect(workflow, contains('ios_native/PacketTunnelProvider.swift'));
    expect(workflow, contains('swiftc -typecheck'));
    expect(workflow, isNot(contains('flutter build ipa')));
  });
}
