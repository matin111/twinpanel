import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Cisco native status is authoritative for process exit', () {
    final source = File('lib/windows_openconnect_tunnel.dart')
        .readAsStringSync();
    final health = source.substring(source.indexOf('Future<bool> checkHealth()'));
    final status = health.indexOf("'openConnectStatus'");
    final ip = health.indexOf('final ip = await _publicIp()');
    expect(status, greaterThanOrEqualTo(0));
    expect(ip, greaterThan(status));
    expect(health, contains("_lastHealthError = 'CISCO_PROCESS_EXITED'"));
    expect(health, contains("_lastHealthError = 'CISCO_ROUTE_BYPASS_DETECTED'"));
    // A failed internet IP service is not evidence the native VPN exited.
    expect(health, contains(
        "_lastHealthError = 'CISCO_EGRESS_RECHECK_UNAVAILABLE';\n"
        "      return true;"));
    expect(health, contains('if (ip == _baselineIp)'));
  });

  test('Cisco health is not counted twice as a sing-box failure', () {
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    final cisco = ui.indexOf("if (!healthy && _modernProtocol == 'cisco')");
    final generic = ui.indexOf("if (healthy) {", cisco);
    expect(cisco, greaterThan(0));
    expect(generic, greaterThan(cisco));
    final section = ui.substring(cisco, generic);
    expect(section, contains('return;'));
    expect(section, contains('_ciscoTunnel.lastHealthError'));
    expect(section, contains('CISCO_EGRESS_RECHECK_UNAVAILABLE'));
    expect(ui, contains("'CISCO_ROUTE_BYPASS_DETECTED' => tr("));
  });

  test('initial Cisco connection still requires changed verified public IP', () {
    final source = File('lib/windows_openconnect_tunnel.dart')
        .readAsStringSync();
    expect(source, contains('if (ip != _baselineIp)'));
    expect(source, contains("'openConnectStatus'"));
    expect(source, contains('CISCO_EGRESS_NOT_VERIFIED'));
  });
}
