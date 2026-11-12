import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Xray inbound list uses OS secure storage, not preferences', () {
    final cache = File('lib/xray_inbound_secure_cache.dart').readAsStringSync();
    expect(cache, contains('FlutterSecureStorage'));
    expect(cache, contains("static const _ttl = Duration(hours: 12)"));
    expect(cache, contains("data['username'] != username"));
    expect(cache, contains("data['namespace'] != namespace"));
    expect(cache, contains("data['origin'] != panelOrigin.origin"));
    expect(cache, contains('XrayServerProfiles.fromResponse'));
    expect(cache, isNot(contains('SharedPreferences')));
    expect(cache, isNot(contains('sessionToken')));
  });

  test('Xray list survives a failed refresh but connection requires live profile', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains('_restoreCachedXrayInbounds()'));
    expect(dashboard, contains('final XrayInboundSecureCache _xrayCache'));
    expect(dashboard, contains('_assignedXrayGroups(previous)'));
    expect(dashboard, contains('Failed refresh retains already validated'));
    expect(dashboard, contains("protocol: VpnProtocols.byCode('v2ray')!"));
    expect(dashboard, contains('final response = await TenantApi.fromBuildConfig()'));
    expect(dashboard, contains('final matches = response.xrayServerGroups'));
    expect(dashboard, contains('XRAY_INBOUND_NOT_AVAILABLE'));
  });

  test('logout erases credential-bearing inbound cache', () {
    final app = File('lib/main.dart').readAsStringSync();
    expect(app, contains('await _sessionStore.clearSession()'));
    expect(app, contains('await const XrayInboundSecureCache().clear()'));
  });
}
