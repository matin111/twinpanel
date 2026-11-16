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
    expect(bridge, contains('"extensionBinaryInstalled": mieruCoreInExtension()'));
    expect(bridge, contains('mieruCoreInExtension() &&'));
    expect(File('lib/macos_mieru_controller.dart').readAsStringSync(),
        contains("raw['extensionBinaryInstalled'] is! bool"));
    expect(bridge, contains('"packetFlowBridgeReady": false'));
    expect(bridge, contains('"engineReady": false'));
    expect(bridge, contains('MACOS_MIERU_PACKET_FLOW_BRIDGE_MISSING'));
    expect(dashboard, contains('_macMieru.installation()'));
    expect(dashboard, contains('MACOS_MIERU_CONNECTION_NOT_VERIFIED'));
    expect(dashboard, contains('PROTOCOL_NOT_INCLUDED_IN_SUBSCRIPTION'));
    expect(workflow, contains('lipo -create'));
    expect(workflow, contains('extension_engines='));
    expect(workflow, contains('cmp "$destination/mieru" "$extension_engines/mieru"'));
    expect(workflow, contains('TwinConnect-macOS-Mieru-UNSIGNED.zip'));
    expect(workflow, contains('TwinConnectProtocolBackendLinked'));
  });
}
