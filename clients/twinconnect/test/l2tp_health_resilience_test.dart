import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/windows_l2tp_tunnel.dart';

void main() {
  test('L2TP rotating exit IP is not confused with a disconnect', () {
    expect(WindowsL2tpTunnel.hasVpnEgress(
      baselineIp: '198.51.100.10',
      currentIp: '203.0.113.20',
    ), isTrue);
    expect(WindowsL2tpTunnel.hasVpnEgress(
      baselineIp: '198.51.100.10',
      currentIp: '203.0.113.30',
    ), isTrue);
  });

  test('L2TP direct route fallback is not a verified VPN exit', () {
    expect(WindowsL2tpTunnel.hasVpnEgress(
      baselineIp: '198.51.100.10',
      currentIp: '198.51.100.10',
    ), isFalse);
  });

  test('periodic L2TP health uses two independent direct HTTPS probes', () {
    final tunnel = File('lib/windows_l2tp_tunnel.dart')
        .readAsStringSync();
    expect(tunnel, contains('api.ipify.org'));
    expect(tunnel, contains('ipv4.icanhazip.com'));
    expect(tunnel, contains("findProxy = (_) => 'DIRECT'"));
    expect(tunnel, contains('L2TP_HEALTH_PROBE_UNAVAILABLE'));
    expect(tunnel, contains('L2TP_ROUTE_BYPASS_DETECTED'));
    expect(tunnel, contains('L2TP_RAS_STATUS_UNAVAILABLE'));
  });

  test('client explains each health reason instead of generic degraded', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains('_l2tpTunnel.lastHealthError'));
    expect(dashboard, contains("'L2TP_HEALTH_PROBE_UNAVAILABLE'"));
    expect(dashboard, contains("'L2TP_ROUTE_BYPASS_DETECTED'"));
    expect(dashboard, contains("'L2TP_RAS_STATUS_UNAVAILABLE'"));
  });
}
