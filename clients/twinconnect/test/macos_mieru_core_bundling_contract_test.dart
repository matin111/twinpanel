import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Mieru core presence is never mistaken for a macOS VPN backend', () {
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final workflow = File('../../.github/workflows/twinconnect-macos-mieru-core.yml')
        .readAsStringSync();

    expect(bridge, contains('case "macOSMieruEngineStatus":'));
    expect(bridge, contains('"binaryInstalled": mieruCoreBundled()'));
    expect(bridge, contains('"packetFlowBridgeReady": false'));
    expect(bridge, contains('"engineReady": false'));
    expect(bridge, contains('MACOS_MIERU_PACKET_FLOW_BRIDGE_MISSING'));
    expect(dashboard, contains('MACOS_MIERU_NATIVE_CORE_NOT_LINKED'));
    expect(workflow, contains('lipo -create'));
    expect(workflow, contains('TwinConnect-macOS-Mieru-UNSIGNED.zip'));
    expect(workflow, contains('TwinConnectProtocolBackendLinked'));
  });
}
