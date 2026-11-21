import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/macos_shadowtls_config.dart';

Map<String, dynamic> profile() => {
  'config': jsonEncode({
    'outbounds': [
      {'type': 'shadowsocks', 'tag': 'ss-user', 'detour': 'tls-hop',
       'method': 'aes-128-gcm', 'password': 'test-secret'},
      {'type': 'shadowtls', 'tag': 'tls-hop', 'version': 3,
       'server': 'example.org', 'server_port': 443,
       'password': 'test-transport-secret',
       'tls': {'enabled': true, 'server_name': 'example.org'}},
    ],
    'route': {'final': 'ss-user'},
  }),
};

void main() {
  test('ShadowTLS v3 is a two-hop detour, not a naked ShadowTLS outbound', () {
    final config = MacShadowTlsConfig.compose(item: profile());
    final outbounds = config['outbounds'] as List;
    expect(outbounds.length, 2);
    expect(outbounds[0]['type'], 'shadowsocks');
    expect(outbounds[0]['detour'], 'shadowtls-transport');
    expect(outbounds[1]['type'], 'shadowtls');
    expect(outbounds[1]['version'], 3);
    expect(config['route']['final'], 'proxy');
    expect(config['dns']['final'], 'dns-remote');
  });

  test('reject TLS verification bypass', () {
    final p = profile();
    final config = jsonDecode(p['config'] as String);
    config['outbounds'][1]['tls']['insecure'] = true;
    p['config'] = jsonEncode(config);
    expect(() => MacShadowTlsConfig.compose(item: p), throwsFormatException);
  });

  test('reject arbitrary outbound injection', () {
    final p = profile();
    final config = jsonDecode(p['config'] as String);
    config['outbounds'][1]['detour'] = 'direct';
    p['config'] = jsonEncode(config);
    expect(() => MacShadowTlsConfig.compose(item: p), throwsFormatException);
  });

  test('reject unreviewed endpoint and protocol fields', () {
    final p = profile();
    final config = jsonDecode(p['config'] as String);
    config['outbounds'][1]['custom_transport'] = 'unsafe';
    p['config'] = jsonEncode(config);
    expect(() => MacShadowTlsConfig.compose(item: p), throwsFormatException);
  });
}
