import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Mieru profile handoff stores scoped Keychain data but never starts VPN', () {
    final control = File(
      'macos_native/TwinConnectMacOSMieruControl.swift',
    ).readAsStringSync();
    final bridge = File(
      'macos_native/TwinConnectMacOSVPNBridge.swift',
    ).readAsStringSync();
    final installer = File(
      'macos_native/install_macos_bridge.py',
    ).readAsStringSync();
    expect(bridge, contains('case "prepareMieru":'));
    expect(bridge, contains('TwinConnectMacOSMieruControl.prepare('));
    expect(installer, contains('mieru_control.read_text(encoding="utf-8")'));
    expect(control, contains('kSecAttrAccessGroup: group'));
    expect(control, contains('kSecValueData] = data'));
    expect(control, contains('kSecReturnPersistentRef'));
    expect(control, contains('provider.passwordReference = persistent'));
    expect(control, contains('"protocol": "mieru"'));
    expect(control, contains('"namespace": namespace'));
    expect(control, contains('manager.isEnabled = false'));
    expect(control, contains('"state": "prepared_not_connectable"'));
    expect(control, contains('"connected": false'));
    expect(control, contains('"peerHandshakeVerified": false'));
    expect(control, isNot(contains('startVPNTunnel(')));
    expect(control, contains('existing.providerConfiguration?["protocol"] as? String == "mieru"'));
    expect(control, contains('SecItemDelete(item as CFDictionary)'));
    // No account password must appear in providerConfiguration.
    expect(control, isNot(contains('"password": password')));
  });
}
