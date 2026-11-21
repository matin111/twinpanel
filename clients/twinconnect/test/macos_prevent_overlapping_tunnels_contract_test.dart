import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS prevents overlapping protocol starts within TwinConnect', () {
    final libbox = File(
      'macos_native/TwinConnectMacOSLibboxControl.swift',
    ).readAsStringSync();
    final wireguard = File(
      'macos_native/TwinConnectMacOSVPNControl.swift',
    ).readAsStringSync();

    for (final host in [libbox, wireguard]) {
      expect(host, contains('let conflicting = (managers ?? []).contains'));
      expect(host, contains('case .connected, .connecting, .reasserting, .disconnecting:'));
      expect(host, contains('guard !conflicting else {'));
      expect(host, contains('result(failure("MACOS_VPN_ALREADY_ACTIVE"))'));
    }

    expect(libbox, contains('existing.providerBundleIdentifier == bundleID'));
    expect(wireguard, contains('config.providerBundleIdentifier == providerBundle'));
    expect(libbox, contains('previous.providerConfiguration?["protocol"] as? String'));
    expect(wireguard, contains('== "wireguard"'));
  });
}
