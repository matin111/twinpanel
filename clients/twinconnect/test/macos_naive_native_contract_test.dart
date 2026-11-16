import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('NaiveProxy remains signed-only and is scoped to the entitled account', () {
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    final host = File('macos_native/TwinConnectMacOSLibboxControl.swift')
        .readAsStringSync();
    final engine = File('macos_native/libbox/TwinConnectMacLibboxEngine.swift')
        .readAsStringSync();
    final provider = File('macos_native/PacketTunnelProvider.swift')
        .readAsStringSync();
    final controller = File('lib/macos_naive_controller.dart')
        .readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();

    expect(bridge, contains('case "macOSNaiveEngineStatus":'));
    expect(bridge, contains('case "startNaive":'));
    expect(bridge, contains('case "getNaiveTunnelStatus":'));
    expect(bridge, contains('["hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell", "socks5"]'));
    expect(bridge, contains('libboxBackendReady()'));
    expect(provider, contains('case "hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell", "socks5":'));
    expect(host, contains('allowedConfig(config, protocolCode: protocolCode)'));
    expect(host, contains('protocolCode == "naive"'));
    expect(host, contains('outbound["insecure_concurrency"] as? Int == 0'));
    expect(host, contains('namespace + ":" + account + ":" + protocolCode'));
    expect(engine, contains('["hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell", "socks5"]'));
    expect(engine, contains('outbounds.first?["type"] as? String == code'));
    expect(engine, contains('outbound["username"] as? String'));
    expect(controller, contains('SingBoxMacConfig.encodeNaiveForEphemeralTunnel'));
    expect(controller, contains("'macOSNaiveEngineStatus'"));
    expect(controller, contains("'startNaive'"));
    expect(controller, contains("'getNaiveTunnelStatus'"));
    expect(controller, contains("'peerHandshakeVerified'"));
    expect(dashboard, contains("protocol == 'naive'"));
    expect(dashboard, contains('_macNaive.installation()'));
    expect(dashboard, contains('_macNaive.start('));
    expect(dashboard, contains("entry.protocol.code == protocol"));
    expect(dashboard, contains('matches.length != 1'));
    expect(dashboard, contains("supportedCodes: {'hysteria2', 'tuic', 'anytls', 'naive', 'shadowtls', 'snell', 'socks5'}"));
    expect(dashboard, contains('_vpnVerified = false'));
  });

  test('NaiveParser is checked by pinned official Apple sing-box release', () {
    final workflow = File('../.github/workflows/twinconnect-macos-renewal-preview.yml');
    // Flutter tests may be run from a checkout where the GitHub workflow is
    // located two directories above the client project.
    final source = workflow.existsSync()
        ? workflow.readAsStringSync()
        : File('../../.github/workflows/twinconnect-macos-renewal-preview.yml')
            .readAsStringSync();
    expect(source, contains('with_naive_outbound'));
    expect(source, contains('tool/macos_naive_config_fixture.dart'));
    expect(source, contains('twinconnect-macos-naive-synthetic.json'));
  });
}
