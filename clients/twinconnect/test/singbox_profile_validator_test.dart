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

  test('ShadowTLS detour cannot be flattened to a single node', () {
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'shadowtls', item: {
        'outbound': {'type': 'shadowtls', 'server': 'vpn.example.org',
          'server_port': 443},
      },
    ), throwsFormatException);
  });
}
