import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS Snell and SOCKS5 reach the same signed Libbox PacketTunnel', () {
    final host = File(
      'macos_native/TwinConnectMacOSLibboxControl.swift',
    ).readAsStringSync();
    final bridge = File(
      'macos_native/TwinConnectMacOSVPNBridge.swift',
    ).readAsStringSync();
    final provider = File(
      'macos_native/PacketTunnelProvider.swift',
    ).readAsStringSync();
    final engine = File(
      'macos_native/libbox/TwinConnectMacLibboxEngine.swift',
    ).readAsStringSync();

    expect(host, contains('"shadowtls", "snell", "socks5"].contains(protocolCode)'));
    expect(host, contains('protocolCode == "snell" ? "MACOS_SNELL"'));
    expect(host, contains('protocolCode == "socks5" ? "MACOS_SOCKS5"'));
    expect(host, contains('return allowedSocks5Config(text)'));
    expect(host, contains('return allowedSnellConfig(text)'));
    expect(host, contains('previous.providerConfiguration?["protocol"] as? String'));
    expect(host, contains('== protocolCode'));
    expect(bridge, contains('case "startSocks5":'));
    expect(bridge, contains('case "startSnell":'));
    expect(provider, contains('"shadowtls", "snell", "socks5":'));
    expect(engine, contains('return snellProfileAllowed(json)'));
    expect(engine, contains('return socks5ProfileAllowed(json)'));
    expect(engine, contains('"snell", "socks5"].contains(code)'));
    expect(host, contains('startVPNTunnel()'));
    expect(host, contains('"peerHandshakeVerified": false'));
  });
}
