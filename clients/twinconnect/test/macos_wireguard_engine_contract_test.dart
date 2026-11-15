import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS WireGuard extension has a real adapter boundary', () {
    final adapter = File('macos_native/TwinConnectWireGuardEngine.swift')
        .readAsStringSync();
    final extension = File('macos_native/PacketTunnelProvider.swift')
        .readAsStringSync();
    final generator = File('macos_native/install_packet_tunnel_target.rb')
        .readAsStringSync();
    expect(adapter, contains('import WireGuardKit'));
    expect(adapter, contains('WireGuardAdapter(with: provider)'));
    expect(adapter, contains('fromWgQuickConfig'));
    expect(adapter, contains('kSecValuePersistentRef'));
    expect(adapter, contains('MacWireGuardError.backendNotLinked'));
    expect(extension, contains('case "wireguard"'));
    expect(extension, contains('engine.start'));
    expect(extension, contains('engine.stop'));
    expect(generator, contains('TwinConnectWireGuardEngine.swift'));
  });

  test('macOS tunnel commands never claim a verified peer handshake', () {
    final host = File('macos_native/TwinConnectMacOSVPNControl.swift')
        .readAsStringSync();
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    final dart = File('lib/macos_wireguard_controller.dart')
        .readAsStringSync();
    expect(host, contains('NETunnelProviderManager.loadAllFromPreferences'));
    expect(host, contains('startVPNTunnel()'));
    expect(host, contains('stopVPNTunnel()'));
    expect(host, contains('kSecAttrAccessGroup'));
    expect(host, contains('"peerHandshakeVerified": false'));
    expect(bridge, contains('case "startTunnel":'));
    expect(bridge, contains('case "stopTunnel":'));
    expect(bridge, contains('case "getTunnelStatus":'));
    expect(bridge, contains('return false'));
    expect(dart, contains('MACOS_WIREGUARD_BACKEND_NOT_LINKED'));
    expect(dart, contains("'peerHandshakeVerified'"));
  });
}
