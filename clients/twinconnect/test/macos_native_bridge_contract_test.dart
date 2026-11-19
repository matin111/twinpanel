import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS native channel exposes no fictitious VPN readiness', () {
    final swift = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    expect(swift, contains('com.twinpanel.twinconnect/vpn'));
    expect(swift, contains('case "getCapabilities":'));
    expect(swift, contains('case "getProtocolCapabilities":'));
    expect(swift, contains('case "macOSRuntimeStatus":'));
    expect(swift, contains('"engineReady": libboxBackendReady()'));
    expect(swift, contains('"fullTunnel": libboxBackendReady()'));
    expect(swift, contains('#if TWINCONNECT_SIGNED_LIBBOX'));
    expect(swift, contains('SecTaskCopyValueForEntitlement'));
    // gomobile's Libbox is statically linked into PacketTunnel. A separate
    // dylib under Frameworks must not be required for signed readiness.
    expect(swift, contains('bundle.executableURL'));
    expect(swift, contains('TwinConnectProtocolBackendLinked'));
    expect(swift, isNot(contains('Contents/Frameworks/Libbox.framework/Libbox')));
    expect(swift, contains('return false'));
    expect(swift, contains('"connected": false'));
    expect(swift, contains('"killSwitchEnforced": false'));
    expect(swift, contains('"supportedCodes": libboxBackendReady()'));
    expect(swift, contains('MACOS_PACKET_TUNNEL_NOT_INSTALLED'));
    expect(swift, isNot(contains('result(true)')));
  });

  test('macOS scaffolding installs native handler and HTTPS permission', () {
    final installer = File('macos_native/install_macos_bridge.py')
        .readAsStringSync();
    expect(installer, contains('MainFlutterWindow.swift'));
    expect(installer, contains('RegisterGeneratedPlugins(registry: flutterViewController)'));
    expect(installer, contains('TwinConnectMacOSVPNBridge.register('));
    expect(installer, contains('com.apple.security.network.client'));
    expect(installer, contains('DebugProfile.entitlements'));
    expect(installer, contains('Release.entitlements'));
    expect(installer, isNot(contains('networkextension"] = true')));
  });

  test('Mac Connect checks native readiness and never invokes Windows engine', () {
    final source = File('lib/live_dashboard.dart')
        .readAsStringSync().replaceAll('\r\n', '\n');
    final start = source.indexOf('Future<void> _toggleMacVpn()');
    final end = source.indexOf('Future<void> _toggleIosVpn()', start);
    expect(start, greaterThan(0));
    expect(end, greaterThan(start));
    final mac = source.substring(start, end);
    expect(mac, contains('NativeVpnBridge.probe()'));
    expect(mac, contains('!capabilities.engineReady || !capabilities.fullTunnel'));
    expect(mac, contains('MACOS_PACKET_TUNNEL_NOT_INSTALLED'));
    expect(mac, contains('_macVpn.start('));
    expect(mac, contains('ConnectionBootstrap(api: api).prepare('));
    expect(mac, contains('MACOS_WIREGUARD_BACKEND_NOT_LINKED'));
    expect(mac, isNot(contains('_toggleVpn()')));
    expect(source, contains('Platform.isMacOS'));
    expect(source, contains('? _toggleMacVpn : (Platform.isWindows ? _toggleVpn : null)'));
  });

  test('macOS capability bridge uses native OS handshake', () {
    final bridge = File('lib/native_vpn_bridge.dart').readAsStringSync();
    expect(bridge, contains('if (Platform.isMacOS) return VpnPlatform.macos'));
    expect(bridge, contains('os != VpnPlatform.ios && os != VpnPlatform.macos'));
    expect(bridge, contains('platform != VpnPlatform.ios && platform != VpnPlatform.macos'));
  });
}
