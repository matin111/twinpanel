import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Mac tunnel stop targets only active TwinConnect VPN managers', () {
    final control = File(
      'macos_native/TwinConnectMacOSVPNControl.swift',
    ).readAsStringSync();
    expect(control, contains('config.providerConfiguration?["protocol"] as? String'));
    expect(control, contains('== "wireguard"'));
    expect(control, contains('let active = (managers ?? []).filter'));
    expect(control, contains('config.providerBundleIdentifier == providerBundle'));
    expect(control, contains('case .connected, .connecting, .reasserting:'));
    expect(control, contains('for selected in active'));
    expect(control, contains('selected.connection.stopVPNTunnel()'));
    expect(control, contains('active.isEmpty ? "disconnected" : "disconnecting"'));
    expect(control, contains('let candidates = (managers ?? []).filter'));
    expect(control, contains('} ?? candidates.first'));
    expect(control, isNot(contains('guard let selected = (managers ?? []).first(where:')));
  });
}
