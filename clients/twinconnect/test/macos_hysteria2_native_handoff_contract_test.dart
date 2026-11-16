import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS Hysteria2 startup requires signed Keychain handoff', () {
    final host = File('macos_native/TwinConnectMacOSLibboxControl.swift')
        .readAsStringSync();
    final extension = File('macos_native/libbox/TwinConnectMacLibboxEngine.swift')
        .readAsStringSync();
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    final installer = File('macos_native/install_macos_bridge.py')
        .readAsStringSync();

    expect(host, contains('kSecAttrAccessGroup'));
    expect(host, contains('kSecReturnPersistentRef'));
    expect(host, contains('tunnel.passwordReference = reference'));
    expect(host, contains('"protocol": protocolCode'));
    expect(host, contains('"namespace": namespace'));
    expect(host, contains('MACOS_TENANT_PROFILE_CONFLICT'));
    expect(extension, contains('SecItemCopyMatching'));
    expect(extension, contains('kSecValuePersistentRef'));
    expect(extension, contains('profileIsAllowed(config)'));
    expect(extension, contains('LibboxNewCommandServer('));
    expect(extension, contains('startOrReloadService('));
    expect(bridge, contains('case "startHysteria2":'));
    expect(bridge, contains('backendLinked: libboxBackendReady()'));
    expect(bridge, contains('TWINCONNECT_SIGNED_LIBBOX'));
    expect(bridge, contains('SecTaskCopyValueForEntitlement'));
    expect(bridge, contains('TwinConnectProtocolBackendLinked'));
    expect(bridge, contains('backendLinked: wireGuardBackendReady()'));
    expect(bridge, contains('return false'));
    expect(installer, contains('TwinConnectMacOSLibboxControl.swift'));
    // Provider configuration must not store sensitive JSON directly.
    final provider = host.substring(
      host.indexOf('tunnel.providerConfiguration = ['),
      host.indexOf('selected.localizedDescription') >= 0
          ? host.indexOf('selected.localizedDescription')
          : host.indexOf('manager.protocolConfiguration = tunnel'),
    );
    expect(provider, isNot(contains('config')));
    expect(provider, isNot(contains('password')));
  });

  test('macOS Hysteria2 profile selection respects tenant and node', () {
    final dart = File('lib/macos_hysteria2_controller.dart')
        .readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dart, contains('SingBoxMacConfig.encodeForEphemeralTunnel'));
    expect(dart, contains('MACOS_HYSTERIA2_PACKET_FLOW_BRIDGE_MISSING'));
    expect(dart, contains("output['peerHandshakeVerified'] != false"));
    expect(dashboard, contains('final entitled = widget.catalog?.entries.any'));
    expect(dashboard, contains("entry.protocol.code == protocol"));
    expect(dashboard, contains('matches.length != 1'));
    expect(dashboard, contains('_macHysteria.start('));
    expect(dashboard, contains('profile: matches.single'));
    expect(dashboard, contains('_vpnVerified = false'));
  });
}
