import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('original Connect button uses iOS native controller, not a fake switch', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("tr('اتصال سریع', 'Connect now')"));
    expect(dashboard, contains('Platform.isIOS\n                    ? _toggleIosVpn'));
    expect(dashboard, contains('Future<void> _toggleIosVpn() async'));
    expect(dashboard, contains('ConnectionBootstrap(api: api).prepare('));
    expect(dashboard, contains('await _iosVpn.start('));
    expect(dashboard, contains('_vpnVerified = false;'));
    expect(dashboard, isNot(contains("tr('موتور آیفون آماده نیست', 'iOS engine unavailable')")));
  });

  test('iOS source includes embedded packet tunnel and secure profile bridge', () {
    final workflow = File('../../.github/workflows/twinconnect-ios-simulator.yml')
        .readAsStringSync();
    final ruby = File('ios_native/install_packet_tunnel_target.rb')
        .readAsStringSync();
    final native = File('ios_native/TwinConnectIOSVPNControl.swift')
        .readAsStringSync();
    final adapter = File('ios_native/TwinConnectWireGuardEngine.swift')
        .readAsStringSync();
    expect(workflow, contains('ruby ios_native/install_packet_tunnel_target.rb'));
    expect(workflow, contains('ios_native/TwinConnectIOSVPNControl.swift'));
    expect(ruby, contains("project.new_target(:app_extension, 'PacketTunnel'"));
    expect(ruby, contains("runner.add_dependency(extension)"));
    expect(ruby, contains("runner.new_copy_files_build_phase('Embed App Extensions')"));
    expect(ruby, contains("settings['MARKETING_VERSION'] = '0.1.0'"));
    expect(ruby, contains("settings['CURRENT_PROJECT_VERSION'] = '1'"));
    expect(workflow, contains('Validate embedded PacketTunnel metadata before install'));
    expect(workflow, contains('CFBundleShortVersionString'));
    expect(workflow, contains('CFBundleVersion'));
    expect(ruby, contains("phase.name == 'Thin Binary'"));
    expect(ruby, contains('phases.insert(thin_index, embed)'));
    expect(ruby, contains('runner.build_phases.index(embed) < runner.build_phases.index(thin_binary)'));
    expect(native, contains('SecItemAdd('));
    expect(native, contains('saveToPreferences'));
    expect(native, contains('startVPNTunnel()'));
    expect(native, contains('"peerHandshakeVerified": false'));
    expect(adapter, contains('#if canImport(WireGuardKit)'));
    expect(adapter, contains('WireGuardAdapter(with: provider)'));
  });
}
