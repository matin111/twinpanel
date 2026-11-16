import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS PacketTunnel prepares dual-stack and DNS policy but fails closed', () {
    final policy = File(
      'macos_native/libbox/TwinConnectMacTunnelPolicy.swift',
    ).readAsStringSync();
    final extension = File('macos_native/PacketTunnelProvider.swift')
        .readAsStringSync();
    final installer = File('macos_native/install_packet_tunnel_target.rb')
        .readAsStringSync();

    expect(policy, contains('NEPacketTunnelNetworkSettings'));
    expect(policy, contains('NEIPv4Route.default()'));
    expect(policy, contains('NEIPv6Route.default()'));
    expect(policy, contains('NEDNSSettings'));
    expect(policy, contains('dns.matchDomains = [""]'));
    expect(policy, isNot(contains('setTunnelNetworkSettings(')));
    expect(extension, contains('case "hysteria2":'));
    expect(extension, contains('TwinConnectMacTunnelPolicy.hysteria2Settings()'));
    expect(extension, contains('MACOS_HYSTERIA2_PACKET_FLOW_BRIDGE_MISSING'));
    expect(installer, contains('libbox/TwinConnectMacTunnelPolicy.swift'));
  });
}
