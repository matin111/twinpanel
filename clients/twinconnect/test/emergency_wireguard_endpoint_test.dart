import 'dart:io' show InternetAddress, SocketException;

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/emergency_wireguard_endpoint.dart';
import 'package:twinconnect/protocols.dart';
import 'package:twinconnect/server_inventory.dart';

final _server = AppServer.fromJson({
  'id': '17', 'name': 'Germany', 'country_code': 'DE',
  'node_online': true, 'latency_ms': null,
  'probe_ip': '8.8.8.8',
});
final _profiles = ClientProtocolProfiles(
  namespace: 'TPABCDEF',
  protocol: VpnProtocols.byCode('wireguard')!,
  items: [
    {'node_id': '17',
      'config': '[Interface]\nPrivateKey = protected\n[Peer]\nPublicKey = peer\nEndpoint = vpn.example.org:51820\nAllowedIPs = 0.0.0.0/0\n'},
  ],
);

void main() {
  test('DNS failure changes only endpoint destination, not peer identity',
      () async {
    final changed = await EmergencyWireGuardEndpoint.useDirectIpOnDnsFailure(
      profiles: _profiles, server: _server,
      lookup: (_) async => throw const SocketException('DNS unreachable'),
    );
    final config = changed.items.single['config'] as String;
    expect(config, contains('Endpoint = 8.8.8.8:51820'));
    expect(config, contains('PublicKey = peer'));
    expect(config, contains('PrivateKey = protected'));
    expect(config, contains('AllowedIPs = 0.0.0.0/0'));
    expect(_profiles.items.single['config'], contains('vpn.example.org'));
  });

  test('DNS success preserves actual configured endpoint', () async {
    final unchanged = await EmergencyWireGuardEndpoint.useDirectIpOnDnsFailure(
      profiles: _profiles, server: _server,
      lookup: (_) async => [InternetAddress('1.1.1.1')],
    );
    expect(unchanged.items.single['config'],
        contains('Endpoint = vpn.example.org:51820'));
  });

  test('no verified node IP cannot be synthesized', () async {
    final withoutIp = AppServer.fromJson({
      'id': '17', 'name': 'Germany', 'country_code': 'DE',
      'node_online': true, 'latency_ms': null,
    });
    final unchanged = await EmergencyWireGuardEndpoint.useDirectIpOnDnsFailure(
      profiles: _profiles, server: withoutIp,
      lookup: (_) async => throw const SocketException('DNS unreachable'),
    );
    expect(unchanged.items.single['config'], _profiles.items.single['config']);
  });

  test('unknown endpoint format is never rewritten', () async {
    final mismatched = ClientProtocolProfiles(
      namespace: 'TPABCDEF', protocol: VpnProtocols.byCode('wireguard')!,
      items: [{'node_id': '17', 'config': 'Endpoint = [2001:db8::1]:51820'}],
    );
    final unchanged = await EmergencyWireGuardEndpoint.useDirectIpOnDnsFailure(
      profiles: mismatched, server: _server,
      lookup: (_) async => throw const SocketException('DNS unreachable'),
    );
    expect(unchanged.items.single['config'], mismatched.items.single['config']);
  });
}
