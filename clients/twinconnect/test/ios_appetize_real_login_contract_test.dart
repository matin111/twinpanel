import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Appetize authenticated artifact starts at real login', () {
    final workflow = File('../../.github/workflows/twinconnect-ios-simulator.yml')
        .readAsStringSync();
    final main = File('lib/main.dart').readAsStringSync();
    final demo = File('lib/ios_preview_main.dart').readAsStringSync();

    expect(workflow, contains('--target lib/main.dart'));
    expect(workflow, contains('TwinConnect-iOS-Appetize-RealLogin-v0.1.0'));
    expect(workflow, contains('--target lib/ios_preview_main.dart'));
    expect(main, contains('void main() => runApp(const TwinConnectApp());'));
    expect(main, contains('final _username = TextEditingController();'));
    expect(main, contains('final _password = TextEditingController();'));
    expect(main, contains('TenantApi.fromBuildConfig()'));
    expect(main, isNot(contains('ios_preview_main.dart')));
    expect(demo, contains('simulatorPreview: true'));
  });

  test('do not mark simulated iOS VPN as successfully connected', () {
    final shared = File('lib/live_dashboard.dart').readAsStringSync();
    final native = File('ios_native/TwinConnectIOSVpnBridge.swift')
        .readAsStringSync();
    expect(shared, contains('onPressed: _vpnBusy ? null : (Platform.isIOS'));
    expect(shared, contains("Key('iosVpnEngineUnavailableNotice')"));
    expect(native, contains('"engineReady": wireGuardReady'));
    expect(native, contains('TwinConnectIOSVPNControl.backendLinked()'));
    expect(native, contains('"verified": false'));
  });
}
