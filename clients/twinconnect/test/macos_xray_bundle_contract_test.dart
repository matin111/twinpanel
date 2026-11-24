import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS Xray bundle is pinned but packet tunnel not declared ready', () {
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    final workflow = File(
      '../../.github/workflows/twinconnect-macos-renewal-preview.yml',
    ).readAsStringSync();
    final script = File('macos_native/fetch_xray_macos.sh')
        .readAsStringSync();
    expect(script, contains('shasum -a 256 -c -'));
    expect(script, contains('Xray-macos-arm64-v8a.zip'));
    expect(script, contains('Xray-macos-64.zip'));
    expect(bridge, contains('case "macOSXrayEngineStatus":'));
    expect(bridge, contains('MACOS_XRAY_PACKET_FLOW_BRIDGE_MISSING'));
    expect(bridge, contains('"packetFlowBridgeReady": false'));
    expect(workflow, contains('bash macos_native/fetch_xray_macos.sh'));
    expect(workflow, contains('Xray packetFlow bridge: NOT IMPLEMENTED'));
    expect(workflow, contains('Contents/Resources/TwinConnectEngines/xray'));
  });
}
