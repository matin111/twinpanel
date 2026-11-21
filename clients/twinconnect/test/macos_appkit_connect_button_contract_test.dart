import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('AppKit primary action is usable without a signed VPN entitlement', () {
    final swift = File('macos_native/TwinConnectMacOSNativeDashboard.swift')
        .readAsStringSync();
    expect(swift, contains('action: #selector(primaryProxyAction(_:)), primary: true'));
    expect(swift, contains('connect.isEnabled = !localProxyBusy'));
    expect(swift, contains('Test Hysteria2 proxy'));
    expect(swift, contains('testNativeHysteria2Proxy(sender)'));
    expect(swift, contains('Proxy test only'));
    expect(swift, contains('Select Hysteria2 from Locations first'));
    // Do not silently advertise the local proxy as a system VPN.
    expect(swift, contains('system VPN, Kill Switch and DNS protection remain OFF'));
    expect(swift, contains('One proxied HTTPS request; not a system-wide VPN connection.'));
  });
}
