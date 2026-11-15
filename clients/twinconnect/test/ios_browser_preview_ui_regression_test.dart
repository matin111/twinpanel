import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('choosing a server never raises Windows engine error on iPhone', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, isNot(contains("setState(() => _vpnError = 'WINDOWS_ENGINE_REQUIRED')")));
    expect(dashboard, contains('if (!Platform.isWindows) {'));
    expect(dashboard, contains('The platform-specific Connect control remains'));
    expect(dashboard, contains("Key('iosVpnEngineUnavailableNotice')"));
  });

  test('mobile dashboard uses compact traffic visualization', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final wave = File('lib/twinconnect_wave_indicator.dart').readAsStringSync();
    expect(dashboard, contains('compact: Platform.isIOS || Platform.isAndroid'));
    expect(wave, contains('widget.compact ? 105 : 178'));
  });
}
