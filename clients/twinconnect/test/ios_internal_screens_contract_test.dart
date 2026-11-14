import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('authenticated iOS UI uses the real shared four-tab phone shell', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final shell = File('lib/ios_home_shell.dart').readAsStringSync();
    expect(dashboard, contains('if (Platform.isIOS) {'));
    expect(dashboard, contains('home: TwinConnectIphoneShell('));
    expect(dashboard, contains('inventory: widget.servers,'));
    expect(dashboard, contains('account: widget.account,'));
    expect(dashboard, contains('plan: widget.plan,'));
    expect(shell, contains("key: const Key('iosShowcaseNavigation')"));
    expect(shell, contains("key: const Key('iphoneConnectDisabled')"));
    expect(shell, contains('onPressed: null,'));
  });

  test('iOS preview uses an explicit separate entry point and fake fixtures', () {
    final live = File('lib/main.dart').readAsStringSync();
    final preview = File('lib/ios_preview_main.dart').readAsStringSync();
    final workflow = File('../../.github/workflows/twinconnect-ios-simulator.yml')
        .readAsStringSync();
    expect(preview, contains('void main() => runApp(const TwinConnectIphonePreview());'));
    expect(preview, contains("username: 'demo_user'"));
    expect(preview, contains('previewMode: true,'));
    expect(preview, contains('autoTour: true,'));
    expect(live, isNot(contains('ios_preview_main.dart')));
    expect(workflow, contains('--target lib/ios_preview_main.dart'));
    for (final name in [
      'TwinConnect-iOS-01-Connect.png',
      'TwinConnect-iOS-02-Locations.png',
      'TwinConnect-iOS-03-Settings.png',
      'TwinConnect-iOS-04-Account.png',
    ]) {
      expect(workflow, contains(name));
    }
  });
}
