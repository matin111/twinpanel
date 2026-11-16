import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Mieru Swift bridge compiles in PacketTunnel but unsigned build stays disabled', () {
    final adapter = File(
      'macos_native/mieru/TwinConnectMacMieruCore.swift',
    ).readAsStringSync();
    final installer = File(
      'macos_native/install_packet_tunnel_target.rb',
    ).readAsStringSync();
    final provider = File(
      'macos_native/PacketTunnelProvider.swift',
    ).readAsStringSync();
    final bridge = File(
      'macos_native/TwinConnectMacOSVPNBridge.swift',
    ).readAsStringSync();
    expect(installer, contains('mieru/TwinConnectMacMieruCore.swift'));
    expect(adapter, contains('#if TWINCONNECT_SIGNED_MIERU'));
    expect(adapter, contains('SecTaskCopyValueForEntitlement'));
    expect(adapter, contains('Bundle.main.bundleIdentifier'));
    expect(adapter, contains('Contents/Frameworks/libtwinmieru.dylib'));
    expect(adapter, contains('dlopen(library.path, RTLD_NOW | RTLD_LOCAL)'));
    expect(adapter, contains('TwinMieruStart'));
    expect(adapter, contains('TwinMieruStop'));
    expect(adapter, contains('TwinMieruLocalReady'));
    expect(adapter, contains('MACOS_MIERU_SIGNED_CORE_UNAVAILABLE'));
    expect(adapter, contains('endpointPinnedOutsideTunnel'));
    expect(adapter, contains('coreOwnedByExtension'));
    expect(adapter, contains('deinit { stop() }'));
    final candidate = File(
      '../../.github/workflows/twinconnect-macos-mieru-core.yml',
    ).readAsStringSync();
    expect(candidate, contains(r'GOARCH="$arch" CGO_ENABLED=1'));
    expect(candidate, contains('buildmode=c-shared'));
    expect(candidate, contains('libtwinmieru.dylib'));
    expect(candidate, contains('extension_frameworks='));
    expect(candidate, contains(r'test ! -f "$app/Contents/Frameworks/libtwinmieru.dylib"'));
    expect(bridge, contains('"extensionLibraryInstalled": mieruInProcessLibraryBundled()'));
    expect(File('lib/macos_mieru_controller.dart').readAsStringSync(),
        contains("raw['extensionLibraryInstalled'] is! bool"));
    expect(bridge, contains('"packetFlowBridgeReady": false'));
    expect(bridge, contains('"engineReady": false'));
    expect(provider, contains('MACOS_PROTOCOL_ENGINE_NOT_LINKED_'));
  });
}
