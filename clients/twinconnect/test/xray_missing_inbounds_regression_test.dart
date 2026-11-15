import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final dashboard = File('lib/live_dashboard.dart')
      .readAsStringSync().replaceAll('\r\n', '\n');

  test('refreshing account inventory reloads REAL Xray server inbounds', () {
    final update = dashboard.substring(
      dashboard.indexOf('void didUpdateWidget('),
      dashboard.indexOf('Future<void> _refreshVpnStatus()'),
    );
    expect(update, contains('oldWidget.servers != widget.servers'));
    expect(update, contains('oldWidget.catalog != widget.catalog'));
    expect(update, contains('_loadXrayGroups(refresh: true)'));
    expect(update, contains('_assignedXrayGroups(_xrayGroups)'));
  });

  test('missing USA, Germany or Finland inbounds are not fabricated', () {
    final assigned = dashboard.substring(
      dashboard.indexOf('List<XrayServerProfiles> _assignedXrayGroups('),
      dashboard.indexOf('Future<void> _restoreCachedXrayInbounds()'),
    );
    expect(assigned, contains('allowed.contains(g.serverId)'));
    expect(assigned, contains('g.inbounds.isNotEmpty'));
    final locations = dashboard.substring(
      dashboard.indexOf('Widget locations()'),
      dashboard.indexOf("key: const Key('devLocationListingCard')"),
    );
    expect(locations, contains('_inboundsForNode(widget.servers!.servers[i].id)'));
    expect(locations, contains('No provisioned Xray inbound'));
    expect(locations, isNot(contains('synthetic')));
  });

  test('connecting always reloads authorized live inbounds, not cached URLs', () {
    final start = dashboard.indexOf('Future<void> _startXrayTunnel(');
    final end = dashboard.indexOf('Future<void> _startSudokuTunnel(', start);
    expect(start, greaterThan(0));
    expect(end, greaterThan(start));
    final method = dashboard.substring(start, end);
    expect(method, contains('loadSessionNativeProfiles('));
    expect(method, contains('response.xrayServerGroups'));
    expect(method, contains("XRAY_SERVER_PROFILES_MISSING"));
    expect(method, isNot(contains('_xrayCache.read(')));
  });
}
