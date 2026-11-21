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
    expect(extension, contains('case "hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell", "socks5":'));
    expect(extension, contains('TwinConnectMacLibboxEngine(tunnel: self)'));
    expect(extension, contains('engine.start'));
    // The old Hysteria2-only bridge placeholder was replaced by the
    // shared Libbox engine. If the Libbox module is absent, the extension
    // must still fail closed for each of the seven supported profiles.
    expect(extension, contains('#if canImport(Libbox)'));
    expect(extension, contains('MACOS_LIBBOX_BACKEND_NOT_LINKED_'));
    expect(extension, contains('completionHandler(unavailable('));
    expect(installer, contains('libbox/TwinConnectMacTunnelPolicy.swift'));
    expect(installer, contains('libbox/TwinConnectMacLibboxPlatform.swift'));
    expect(installer, contains('libbox/TwinConnectMacLibboxEngine.swift'));
    final platform = File('macos_native/libbox/TwinConnectMacLibboxPlatform.swift').readAsStringSync();
    final engine = File('macos_native/libbox/TwinConnectMacLibboxEngine.swift').readAsStringSync();
    expect(platform, contains('LibboxPlatformInterfaceProtocol'));
    expect(platform, contains('setTunnelNetworkSettings(candidate)'));
    expect(platform, contains('LibboxGetTunnelFileDescriptor()'));
    expect(engine, contains('LibboxNewCommandServer('));
    expect(engine, contains('startOrReloadService('));
    expect(engine, contains('kSecValuePersistentRef'));
    expect(engine, contains('MACOS_LIBBOX_KEYCHAIN_PROFILE_MISSING'));
  });
}
