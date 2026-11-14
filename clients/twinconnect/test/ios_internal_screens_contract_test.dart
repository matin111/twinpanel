import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('all platforms use the same authenticated dashboard and panel data', () {
    final app = File('lib/main.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(app, contains('return TwinConnectLiveDashboard('));
    expect(dashboard, isNot(contains('home: TwinConnectIphoneShell(')));
    expect(dashboard, contains('home: Builder(builder: _shell)'));
    expect(dashboard, contains('widget.servers?.servers'));
    expect(dashboard, contains('widget.catalog'));
    expect(dashboard, contains('widget.account'));
    expect(dashboard, contains('widget.brand'));
    expect(dashboard, contains("key: const Key('iosBottomNavigation')"));
    expect(dashboard, contains('if (!iosMobile) sideBar()'));
  });

  test('preview uses the same shared dashboard with fake data in isolation', () {
    final app = File('lib/main.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final preview = File('lib/ios_preview_main.dart').readAsStringSync();
    final workflow = File('../../.github/workflows/twinconnect-ios-simulator.yml')
        .readAsStringSync();
    expect(preview, contains('void main() => runApp(const TwinConnectIphonePreview());'));
    expect(preview, contains('=> TwinConnectLiveDashboard('));
    expect(preview, contains("username: 'demo_user'"));
    expect(preview, contains('simulatorPreview: true'));
    expect(dashboard, contains('if (widget.simulatorPreview) {'));
    expect(app, isNot(contains('ios_preview_main.dart')));
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
