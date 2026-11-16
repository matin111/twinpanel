import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('native macOS TUIC remains signed-only and scoped to the correct plan', () {
    final native = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    final host = File('macos_native/TwinConnectMacOSLibboxControl.swift')
        .readAsStringSync();
    final engine = File('macos_native/libbox/TwinConnectMacLibboxEngine.swift')
        .readAsStringSync();
    final provider = File('macos_native/PacketTunnelProvider.swift')
        .readAsStringSync();
    final client = File('lib/macos_tuic_controller.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();

    expect(native, contains('case "startTuic":'));
    expect(native, contains('case "getTuicTunnelStatus":'));
    expect(native, contains('case "macOSTuicEngineStatus":'));
    expect(native, contains('["hysteria2", "tuic", "anytls", "naive", "shadowtls"]'));
    expect(native, contains('libboxBackendReady()'));
    expect(host, contains('allowedConfig(config, protocolCode: protocolCode)'));
    expect(host, contains('namespace + ":" + account + ":" + protocolCode'));
    expect(host, contains('outbound["zero_rtt_handshake"] as? Bool == false'));
    expect(engine, contains('["hysteria2", "tuic", "anytls", "naive", "shadowtls"]'));
    expect(engine, contains('outbounds.first?["type"] as? String == code'));
    expect(provider, contains('case "hysteria2", "tuic", "anytls", "naive", "shadowtls":'));
    expect(client, contains("SingBoxMacConfig.encodeTuicForEphemeralTunnel"));
    expect(client, contains("'startTuic'"));
    expect(client, contains("'getTuicTunnelStatus'"));
    expect(client, contains("'peerHandshakeVerified'"));
    expect(dashboard, contains("protocol == 'hysteria2' || protocol == 'tuic'"));
    expect(dashboard, contains('_macTuic.installation()'));
    expect(dashboard, contains('_macTuic.start('));
    expect(dashboard, contains("entry.protocol.code == protocol"));
    expect(dashboard, contains('matches.length != 1'));
  });

  test('TUIC is not an unverified WireGuard or Xray fallback', () {
    final source = File('lib/live_dashboard.dart').readAsStringSync();
    final begin = source.indexOf('Future<void> _toggleMacVpn()');
    final end = source.indexOf('Future<void> _toggleIosVpn()', begin);
    final mac = source.substring(begin, end);
    expect(mac, contains("VpnProtocols.byCode(protocol)"));
    expect(mac, contains('native: const NativeProtocolReadiness('));
    expect(mac, contains("supportedCodes: {'hysteria2', 'tuic', 'anytls', 'naive', 'shadowtls'}"));
    expect(mac, contains('profile: matches.single'));
    expect(mac, contains('_vpnVerified = false'));
  });
}
