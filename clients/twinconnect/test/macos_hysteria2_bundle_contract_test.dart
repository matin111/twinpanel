import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS bundles a verified sing-box transport but does not claim VPN', () {
    final workflow = File(
      '../../.github/workflows/twinconnect-macos-renewal-preview.yml',
    ).readAsStringSync();
    final swift = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    final source = File('macos_native/fetch_singbox_macos.sh')
        .readAsStringSync();

    expect(workflow, contains('bash macos_native/fetch_singbox_macos.sh'));
    expect(workflow, contains('Contents/Resources/TwinConnectEngines'));
    expect(workflow, contains('Hysteria2 packetFlow bridge: NOT IMPLEMENTED'));
    expect(source, contains('shasum -a 256 -c -'));
    expect(swift, contains('case "macOSHysteria2EngineStatus":'));
    expect(swift, contains('MACOS_HYSTERIA2_PACKET_FLOW_BRIDGE_MISSING'));
    expect(swift, contains('"packetFlowBridgeReady": false'));
    expect(swift, contains('"engineReady": false'));
  });
}
