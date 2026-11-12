import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/shadowtls_chain.dart';
import 'package:twinconnect/singbox_windows_config.dart';
import 'package:twinconnect/modern_transport_probe.dart';

Map<String, dynamic> deliveredShadowTls() => {
  'node_id': 25,
  'protocol': 'shadowtls',
  'config': jsonEncode({
    'log': {'level': 'warn'},
    'inbounds': [{'type': 'mixed', 'listen': '127.0.0.1',
      'listen_port': 1080}],
    'outbounds': [
      {
        'type': 'shadowsocks', 'tag': 'user-ss',
        'method': '2022-blake3-aes-128-gcm',
        'password': 'AAAAAAAAAAAAAAAAAAAAAA==',
        'detour': 'outer-tls',
        'udp_over_tcp': {'enabled': true, 'version': 2},
      },
      {
        'type': 'shadowtls', 'tag': 'outer-tls',
        'version': 3, 'password': 'example-test-secret',
        'server': 'vpn.example.org', 'server_port': 443,
        'tls': {'enabled': true, 'server_name': 'www.microsoft.com'},
      },
    ],
    'route': {'final': 'user-ss'},
  }),
};

void main() {
  test('authentic two-stage ShadowTLS v3 identity survives normalization', () {
    final item = deliveredShadowTls();
    final chain = ShadowTlsChain.fromItem(item);
    expect(chain.endpoint, 'vpn.example.org');
    final out = chain.outbounds(resolvedServer: '93.184.216.34');
    expect(out, hasLength(2));
    expect(out[0]['type'], 'shadowsocks');
    expect(out[0]['tag'], 'proxy');
    expect(out[0]['detour'], 'shadowtls-transport');
    expect(out[0]['password'], 'AAAAAAAAAAAAAAAAAAAAAA==');
    expect(out[0]['udp_over_tcp'], {'enabled': true, 'version': 2});
    expect(out[1]['type'], 'shadowtls');
    expect(out[1]['tag'], 'shadowtls-transport');
    expect(out[1]['server'], '93.184.216.34');
    expect((out[1]['tls'] as Map)['server_name'], 'www.microsoft.com');

    final tun = SingBoxWindowsConfig.compose(
      protocol: 'shadowtls', item: item, resolvedServer: '93.184.216.34');
    expect(tun['outbounds'], out);
    expect((tun['route'] as Map)['final'], 'proxy');
    expect(((tun['inbounds'] as List).single as Map)['strict_route'], true);
    expect(((tun['dns'] as Map)['servers'] as List)[1]['detour'], 'proxy');

    final probe = ModernTransportProbe.proxyConfig(
      protocol: 'shadowtls', profile: item, port: 15000,
      resolvedServer: '93.184.216.34');
    expect(probe['outbounds'], out);
    expect((probe['route'] as Map)['final'], 'proxy');
  });

  test('missing identity, invalid detour and injected bypass fail closed', () {
    final item = deliveredShadowTls();
    final original = jsonDecode(item['config'] as String) as Map<String, dynamic>;
    final rows = original['outbounds'] as List;
    final ss = rows[0] as Map<String, dynamic>;
    final tls = rows[1] as Map<String, dynamic>;

    Map<String, dynamic> changed() => {'config': jsonEncode(original)};
    ss['detour'] = 'direct';
    expect(() => ShadowTlsChain.fromItem(changed()), throwsFormatException);
    ss['detour'] = 'outer-tls';
    // Preserve the actual panel trust policy instead of silently changing
    // it. Legacy delivery may have insecure=true pending certificate repair.
    tls['tls']['insecure'] = true;
    expect((ShadowTlsChain.fromItem(changed()).transport['tls'] as Map)
        ['insecure'], isTrue);
    tls['tls'].remove('insecure');
    tls['detour'] = 'direct';
    expect(() => ShadowTlsChain.fromItem(changed()), throwsFormatException);
    tls.remove('detour');
    ss.remove('password');
    expect(() => ShadowTlsChain.fromItem(changed()), throwsFormatException);
    ss['password'] = 'AAAAAAAAAAAAAAAAAAAAAA==';
    rows.add({'type': 'direct', 'tag': 'bypass'});
    expect(() => ShadowTlsChain.fromItem(changed()), throwsFormatException);
  });
}
