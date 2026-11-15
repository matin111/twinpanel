import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('real iPhone login cannot show a working VPN when engine is absent', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final bridge = File('ios_native/TwinConnectIOSVpnBridge.swift')
        .readAsStringSync();

    expect(dashboard, contains("onPressed: _vpnBusy ? null : (Platform.isIOS"));
    expect(dashboard, contains("tr('اتصال سریع', 'Connect now')"));
    expect(dashboard, contains('ورود و دریافت اشتراک برقرار است، اما تونل فعال نیست.'));
    expect(bridge, contains('"engineReady": false'));
    expect(bridge, contains('"supportedProtocols": [String]()'));
    expect(bridge, contains('"verified": false'));
  });
}
