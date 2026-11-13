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
        'password': 'confidential',
        if (entry.key == 'socks5') ...{
          'version': '5', 'username': 'synthetic', 'network': 'tcp',
        },
        if (entry.key != 'snell' && entry.key != 'socks5')
          'tls': <String, dynamic>{'enabled': true, 'server_name': 'example.org'},
      };
      final profile = <String, dynamic>{'node_id': 12, 'outbound': outbound};
      final parsed = SingBoxProfileValidator.validateOutbound(
        protocolCode: entry.key, item: profile);
      expect(parsed['type'], entry.value);
      expect(parsed['password'], 'confidential');
      expect(identical(parsed, outbound), isFalse);
    });
  }

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

  test('ShadowTLS detour cannot be flattened to a single node', () {
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'shadowtls', item: {
        'outbound': {'type': 'shadowtls', 'server': 'vpn.example.org',
          'server_port': 443},
      },
    ), throwsFormatException);
  });
}
