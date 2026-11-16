import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS AnyTLS is scoped to the subscribed server and native Libbox', () {
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    final host = File('macos_native/TwinConnectMacOSLibboxControl.swift')
        .readAsStringSync();
    final extension = File('macos_native/PacketTunnelProvider.swift')
        .readAsStringSync();
    final engine = File('macos_native/libbox/TwinConnectMacLibboxEngine.swift')
        .readAsStringSync();
    final client = File('lib/macos_anytls_controller.dart')
        .readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();

    expect(bridge, contains('case "macOSAnyTlsEngineStatus":'));
    expect(bridge, contains('case "startAnyTls":'));
    expect(bridge, contains('case "getAnyTlsTunnelStatus":'));
    expect(bridge, contains('"protocol": "anytls"'));
    expect(bridge, contains('libboxBackendReady()'));
    expect(extension, contains('case "hysteria2", "tuic", "anytls":'));
    expect(engine, contains('["hysteria2", "tuic", "anytls"]'));
    expect(engine, contains('outbounds.first?["type"] as? String == code'));
    expect(host, contains('allowedConfig(config, protocolCode: protocolCode)'));
    expect(host, contains('namespace + ":" + account + ":" + protocolCode'));
    expect(host, contains('protocolCode == "anytls"'));
    expect(client, contains('SingBoxMacConfig.encodeAnyTlsForEphemeralTunnel'));
    expect(client, contains("'startAnyTls'"));
    expect(client, contains("'getAnyTlsTunnelStatus'"));
    expect(client, contains("'peerHandshakeVerified'"));
    expect(dashboard, contains("protocol == 'anytls'"));
    expect(dashboard, contains('_macAnyTls.installation()'));
    expect(dashboard, contains('_macAnyTls.start('));
    expect(dashboard, contains("entry.protocol.code == protocol"));
    expect(dashboard, contains('matches.length != 1'));
    expect(dashboard, contains("supportedCodes: {'hysteria2', 'tuic', 'anytls'}"));
    expect(dashboard, contains('_vpnVerified = false'));
  });
}
