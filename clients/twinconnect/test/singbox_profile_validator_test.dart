import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_profile_validator.dart';

void main() {
  const cases = <String, String>{
    'hysteria2': 'hysteria2',
    'tuic': 'tuic',
    'anytls': 'anytls',
    'naive': 'naive',
    'snell': 'snell',
    'socks5': 'socks',
  };

  test('modern sing-box family stays separate from native engines', () {
    for (final protocol in cases.keys) {
      expect(SingBoxProfileValidator.supportsFamily(protocol), isTrue);
    }
    expect(SingBoxProfileValidator.supportsFamily('shadowtls'), isTrue);
    for (final protocol in ['wireguard', 'mieru', 'amneziawg',
      'trusttunnel', 'sudoku', 'cisco']) {
      expect(SingBoxProfileValidator.supportsFamily(protocol), isFalse);
    }
  });

  for (final entry in cases.entries) {
    test('native ${entry.key} outbound validates without rewriting secrets', () {
      final outbound = <String, dynamic>{
        'type': entry.value,
        'server': 'vpn.example.org',
        'server_port': 443,
        if (entry.key == 'snell') ...{
          'psk': 'confidential',
          'version': 4,
        } else 'password': 'confidential',
        if (entry.key == 'socks5') ...{
          'username': 'synthetic',
          'version': '5',
          'network': 'tcp',
        },
        if (entry.key != 'snell' && entry.key != 'socks5')
          'tls': <String, dynamic>{'enabled': true, 'server_name': 'example.org'},
      };
      final profile = <String, dynamic>{'node_id': 12, 'outbound': outbound};
      final parsed = SingBoxProfileValidator.validateOutbound(
        protocolCode: entry.key, item: profile);
      expect(parsed['type'], entry.value);
      expect(entry.key == 'snell' ? parsed['psk'] : parsed['password'],
          'confidential');
      expect(identical(parsed, outbound), isFalse);
    });
  }

  test('full panel JSON yields only one native outbound and drops app routing', () {
    const original = '{"inbounds":[{"type":"tun","tag":"unsafe"}],'
        '"dns":{"servers":[{"server":"8.8.8.8"}]},'
        '"route":{"final":"direct"},'
        '"outbounds":[{"type":"hysteria2","server":"vpn.example.org",'
        '"server_port":443,"password":"secret",'
        '"tls":{"enabled":true,"server_name":"vpn.example.org"}},'
        '{"type":"direct","tag":"direct"}]}';
    final outbound = SingBoxProfileValidator.validateOutbound(
      protocolCode: 'hysteria2',
      item: {'config': original},
    );
    expect(outbound['type'], 'hysteria2');
    expect(outbound['password'], 'secret');
    expect(outbound.containsKey('route'), isFalse);
    expect(outbound.containsKey('dns'), isFalse);
    expect(outbound.containsKey('inbounds'), isFalse);
  });

  test('ambiguous full panel sing-box profile is rejected', () {
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'tuic',
      item: {'config': '{"outbounds":[{"type":"tuic"},{"type":"tuic"}]}'},
    ), throwsFormatException);
  });

  test('opaque links and wrong protocol cannot silently be converted', () {
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'hysteria2',
      item: {'uri': 'hysteria2://secret@example.org:443'},
    ), throwsFormatException);
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'tuic', item: {
        'outbound': {'type': 'hysteria2', 'server': 'vpn.example.org',
          'server_port': 443, 'tls': {'enabled': true}},
      },
    ), throwsFormatException);
  });

  test('subscription cannot inject routes or bypass TLS checks', () {
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'anytls', item: {
        'outbound': {'type': 'anytls', 'server': 'vpn.example.org',
          'server_port': 443, 'route': {'final': 'direct'},
          'tls': {'enabled': true}},
      },
    ), throwsFormatException);
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'anytls', item: {
        'outbound': {'type': 'anytls', 'server': 'vpn.example.org',
          'server_port': 443},
      },
    ), throwsFormatException);
  });

  test('ShadowTLS chain uses actual authenticated detour and retains secrets', () {
    const innerSecret = 'synthetic-secret-inner';
    const outerSecret = 'synthetic-secret-outer';
    final item = {
      'node_id': 25,
      'config': {
        // This full application envelope is NOT executed by the app.
        'dns': {'servers': ['1.1.1.1']},
        'route': {'final': 'direct'},
        'outbounds': [
          {'type': 'direct', 'tag': 'untrusted-direct'},
          {
            'type': 'shadowtls',
            'tag': 'shad-outer',
            'server': 'vpn.example.org',
            'server_port': 443,
            'version': 3,
            'password': outerSecret,
            'tls': {'enabled': true, 'server_name': 'www.example.org'},
          },
          {
            'type': 'shadowsocks',
            'tag': 'inner-proxy',
            'method': 'aes-256-gcm',
            'password': innerSecret,
            'detour': 'shad-outer',
          },
        ],
      },
    };
    final chain = SingBoxProfileValidator.validateShadowTlsChain(item);
    expect(chain.length, 2);
    expect(chain[0]['type'], 'shadowsocks');
    expect(chain[0]['password'], innerSecret);
    expect(chain[0]['detour'], 'shad-outer');
    expect(chain[1]['type'], 'shadowtls');
    expect(chain[1]['password'], outerSecret);
    expect(chain.any((outbound) => outbound.containsKey('route')), false);
    expect(chain.any((outbound) => outbound['type'] == 'direct'), false);
  });

  test('ShadowTLS accepts standard sing-box TLS object without explicit fields', () {
    final chain = SingBoxProfileValidator.validateShadowTlsChain({
      'config': {
        'outbounds': [
          {
            'type': 'shadowsocks', 'tag': 'inner',
            'method': 'aes-256-gcm', 'password': 'synthetic',
            'detour': 'wrapper',
          },
          {
            'type': 'shadowtls', 'tag': 'wrapper',
            'server': 'vpn.example.org',
            'server_port': 443, 'version': 3,
            'password': 'synthetic', 'tls': <String, dynamic>{},
          },
        ],
      },
    });
    expect(chain[1]['tls'], {'enabled': true});
    expect(chain[0]['detour'], 'wrapper');
  });

  test('ShadowTLS accepts panel SNI shorthand and omitted TLS enabled', () {
    final chain = SingBoxProfileValidator.validateShadowTlsChain({
      'config': {
        'outbounds': [
          {
            'type': 'shadowsocks', 'tag': 'proxy',
            'detour': 'st', 'method': 'aes-256-gcm',
            'password': 'synthetic',
          },
          {
            'type': 'shadowtls', 'tag': 'st',
            'server': '198.51.100.16',
            'server_port': 443, 'version': 3,
            'password': 'synthetic',
            'sni': 'www.example.org',
            'tls': {'server_name': 'www.example.org'},
          },
        ],
      },
    });
    expect(chain[1]['tls'], {
      'server_name': 'www.example.org',
      'enabled': true,
    });
    expect(chain[1].containsKey('sni'), isFalse);
  });

  test('ShadowTLS accepts panel SNI without nested TLS block', () {
    final chain = SingBoxProfileValidator.validateShadowTlsChain({
      'outbounds': [
        {
          'type': 'shadowsocks', 'tag': 'proxy',
          'detour': 'st', 'method': 'aes-256-gcm',
          'password': 'test-inner',
        },
        {
          'type': 'shadowtls', 'tag': 'st',
          'server': '198.51.100.16', 'server_port': 443,
          'version': 3, 'password': 'test-outer',
          'sni': 'www.example.org',
        },
      ],
    });
    expect(chain[1]['tls'], {
      'enabled': true,
      'server_name': 'www.example.org',
    });
  });

  test('ShadowTLS refuses invalid numeric SNI with no cover hostname', () {
    expect(() => SingBoxProfileValidator.validateShadowTlsChain({
      'outbounds': [
        {
          'type': 'shadowsocks', 'tag': 'proxy',
          'detour': 'st', 'method': 'aes-256-gcm',
          'password': 'synthetic',
        },
        {
          'type': 'shadowtls', 'tag': 'st',
          'server': '198.51.100.16',
          'server_port': 443, 'version': 3,
          'password': 'synthetic',
        },
      ],
    }), throwsFormatException);
  });

  test('ShadowTLS chain rejects mismatched detour and insecure TLS', () {
    final item = {
      'outbounds': [
        {
          'type': 'shadowsocks', 'tag': 'inner-proxy',
          'method': 'aes-256-gcm', 'password': 'test',
          'detour': 'wrong-wrapper',
        },
        {
          'type': 'shadowtls', 'tag': 'shadow',
          'server': 'vpn.example.org', 'server_port': 443,
          'version': 3, 'password': 'test',
          'tls': {'enabled': true, 'server_name': 'example.org'},
        },
      ],
    };
    expect(() => SingBoxProfileValidator.validateShadowTlsChain(item),
        throwsFormatException);
    final inner = (item['outbounds'] as List)[0] as Map;
    inner['detour'] = 'shadow';
    final outer = (item['outbounds'] as List)[1] as Map;
    (outer['tls'] as Map)['insecure'] = true;
    expect(() => SingBoxProfileValidator.validateShadowTlsChain(item),
        throwsFormatException);
  });

  test('Snell v6 requires a valid 12-255 byte PSK', () {
    Map<String, dynamic> profile(String psk) => {
      'outbound': {
        'type': 'snell',
        'server': 'vpn.example.org',
        'server_port': 443,
        'version': 6,
        'psk': psk,
      },
    };
    expect(() => SingBoxProfileValidator.validateOutbound(
        protocolCode: 'snell', item: profile('short')),
        throwsFormatException);
    final result = SingBoxProfileValidator.validateOutbound(
        protocolCode: 'snell', item: profile('validSnellKey123'));
    expect(result['psk'], 'validSnellKey123');
    expect(result['version'], 6);
  });

  test('unsupported Snell v5 QUIC is not disguised as TCP v4', () {
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'snell',
      item: {'outbound': {
        'type': 'snell',
        'server': 'vpn.example.org',
        'server_port': 443,
        'version': 5,
        'psk': 'secret',
      }},
    ), throwsFormatException);
  });

  test('TLS-enabled modern protocols accept missing enabled flag securely', () {
    for (final protocol in ['hysteria2', 'tuic', 'anytls']) {
      final result = SingBoxProfileValidator.validateOutbound(
        protocolCode: protocol,
        item: {
          'outbound': {
            'type': protocol,
            'server': 'vpn.example.org',
            'server_port': 443,
            'tls': {'server_name': 'www.example.org'},
          },
        },
      );
      expect((result['tls'] as Map)['enabled'], isTrue);
      expect((result['tls'] as Map)['server_name'], 'www.example.org');
    }
  });

  test('TLS-enabled modern protocols reject insecure certificates', () {
    for (final protocol in ['hysteria2', 'tuic', 'anytls']) {
      expect(() => SingBoxProfileValidator.validateOutbound(
        protocolCode: protocol,
        item: {
          'outbound': {
            'type': protocol,
            'server': 'vpn.example.org',
            'server_port': 443,
            'tls': {'enabled': true, 'insecure': true},
          },
        },
      ), throwsFormatException);
    }
  });


  test('Modern TLS accepts panel-level SNI for numeric endpoints', () {
    for (final protocol in ['hysteria2', 'tuic', 'anytls']) {
      final parsed = SingBoxProfileValidator.validateOutbound(
        protocolCode: protocol, item: {
          'sni': 'www.example.org',
          'outbound': {'type': protocol, 'server': '198.51.100.16',
            'server_port': 443, 'tls': <String, dynamic>{}},
        });
      expect((parsed['tls'] as Map)['server_name'], 'www.example.org');
      expect(parsed.containsKey('sni'), isFalse);
    }
  });

  test('Modern TLS never infers certificate identity from a numeric IP', () {
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'hysteria2', item: {
        'outbound': {'type': 'hysteria2', 'server': '198.51.100.16',
          'server_port': 443, 'tls': <String, dynamic>{}},
      }), throwsFormatException);
  });

  test('ShadowTLS detour cannot be flattened to a single node', () {
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'shadowtls', item: {
        'outbound': {'type': 'shadowtls', 'server': 'vpn.example.org',
          'server_port': 443},
      },
    ), throwsFormatException);
  });
}
