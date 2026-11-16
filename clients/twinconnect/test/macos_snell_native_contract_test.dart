import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Snell uses signed-only Libbox, Keychain, and a scoped account', () {
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift').readAsStringSync();
    final host = File('macos_native/TwinConnectMacOSLibboxControl.swift').readAsStringSync();
    final engine = File('macos_native/libbox/TwinConnectMacLibboxEngine.swift').readAsStringSync();
    final provider = File('macos_native/PacketTunnelProvider.swift').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final controller = File('lib/macos_snell_controller.dart').readAsStringSync();
    expect(bridge, contains('case "startSnell":'));
    expect(bridge, contains('case "getSnellTunnelStatus":'));
    expect(bridge, contains('case "macOSSnellEngineStatus":'));
    expect(host, contains('allowedSnellConfig'));
    expect(host, contains('namespace + ":" + account + ":" + protocolCode'));
    expect(engine, contains('snellProfileAllowed'));
    expect(provider, contains('"shadowtls", "snell"'));
    expect(controller, contains('SingBoxMacConfig.encodeSnellForEphemeralTunnel'));
    expect(dashboard, contains('_macSnell.start('));
    expect(dashboard, contains("protocol == 'snell'"));
    expect(dashboard, contains('_vpnVerified = false'));
  });
}
