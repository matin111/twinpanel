import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('native connection authorizations run concurrently before secrets', () {
    final source = File('lib/connection_bootstrap.dart').readAsStringSync();
    final overlap = source.indexOf('Future.wait<Object>([');
    final catalog = source.indexOf('api.loadSessionProtocolCatalog(', overlap);
    final inventory = source.indexOf('api.refreshSessionServers(', overlap);
    final privateProfiles = source.indexOf('api.loadSessionNativeProfiles(', overlap);
    expect(overlap, greaterThan(-1));
    expect(catalog, greaterThan(overlap));
    expect(inventory, greaterThan(catalog));
    expect(privateProfiles, greaterThan(inventory));
    expect(source, contains("PROTOCOL_NOT_ALLOWED"));
    expect(source, contains("SERVER_NOT_AVAILABLE"));
  });

  test('polling gets faster but no protocol skips verified OS egress', () {
    final l2tp = File('lib/windows_l2tp_tunnel.dart').readAsStringSync();
    final cisco = File('lib/windows_openconnect_tunnel.dart').readAsStringSync();
    final ovpn = File('lib/windows_openvpn_tunnel.dart').readAsStringSync();

    expect(l2tp, contains('milliseconds: 250'));
    expect(l2tp, contains('if (status.state == 2)'));
    expect(l2tp, contains('hasVpnEgress('));
    expect(cisco, contains('milliseconds: 300'));
    expect(cisco, contains('if (ip != _baselineIp)'));
    expect(ovpn, contains('attempt < 10'));
    expect(ovpn, contains('attempt <= 2 ? 350'));
    expect(ovpn, contains('if (ip != baseline) return ip'));
  });
}
