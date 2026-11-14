import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('iPhone displays safe offline status without a native VPN engine', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final native = File('lib/native_vpn_bridge.dart').readAsStringSync();
    expect(dashboard, contains("Key('iosVpnEngineUnavailableNotice')"));
    expect(dashboard, contains("onPressed: !Platform.isWindows || _vpnBusy ? null : _toggleVpn"));
    expect(dashboard, contains("onTap: !Platform.isWindows || _vpnBusy ? null : ()"));
    expect(native, contains('iOS/macOS have no native VPN bridge yet.'));
    expect(native, contains('NativeVpnCapabilities.unavailable(os)'));
  });

  test('iPhone uses responsive navigation without desktop-only sidebar', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("key: const Key('iosBottomNavigation')"));
    expect(dashboard, contains("if (!iosMobile) sideBar()"));
    expect(dashboard, contains("'locations' => 1"));
    expect(dashboard, contains("'account' => 3"));
  });

  test('iOS CI builds a simulator-only app, not an unsigned device IPA', () {
    final workflow = File('../../.github/workflows/twinconnect-ios-simulator.yml')
        .readAsStringSync();
    expect(workflow, contains('flutter build ios --simulator --debug --no-codesign'));
    expect(workflow, contains('xcrun simctl install'));
    expect(workflow, contains('xcrun simctl launch'));
    expect(workflow, isNot(contains('flutter build ipa')));
  });
}
