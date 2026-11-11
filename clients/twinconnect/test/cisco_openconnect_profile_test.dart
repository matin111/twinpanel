import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/cisco_openconnect_profile.dart';

void main() {
  test('accepts canonical authorized Cisco endpoint and credentials', () {
    final profile = CiscoOpenConnectProfile.fromItem({
      'node_id': 12,
      'host': 'vpn.example.org',
      'port': 443,
      'username': 'customer_1',
      'password': 'example-secret',
    });
    expect(profile.gateway, 'vpn.example.org:443');
    expect(profile.username, 'customer_1');
    expect(profile.password, 'example-secret');
  });

  test('supports existing endpoint key aliases', () {
    final profile = CiscoOpenConnectProfile.fromItem({
      'server_ip': '203.0.113.22',
      'server_port': '4443',
      'user': 'customer',
      'password': 'with spaces ',
    });
    expect(profile.gateway, '203.0.113.22:4443');
    expect(profile.password, 'with spaces ');
  });

  test('rejects profiles missing authentic credentials', () {
    expect(() => CiscoOpenConnectProfile.fromItem({
      'host': 'vpn.example.org', 'username': 'customer',
    }), throwsFormatException);
    expect(() => CiscoOpenConnectProfile.fromItem({
      'host': 'vpn.example.org', 'password': 'secret',
    }), throwsFormatException);
  });

  test('rejects injected hosts, invalid ports and control characters', () {
    for (final host in [
      'https://vpn.example.org', '-evil.example.org',
      'vpn.example.org/path', 'vpn.example.org\n--script',
    ]) {
      expect(() => CiscoOpenConnectProfile.fromItem({
        'host': host, 'username': 'customer', 'password': 'secret',
      }), throwsFormatException);
    }
    expect(() => CiscoOpenConnectProfile.fromItem({
      'host': 'vpn.example.org', 'port': 65536,
      'username': 'customer', 'password': 'secret',
    }), throwsFormatException);
    expect(() => CiscoOpenConnectProfile.fromItem({
      'host': 'vpn.example.org', 'username': 'customer',
      'password': 'pass\nword',
    }), throwsFormatException);
  });

  test('uses a verified certificate fingerprint provided by the panel', () {
    final profile = CiscoOpenConnectProfile.fromItem({
      'host': 'vpn.example.org', 'username': 'customer',
      'password': 'secret',
      'certificate_fingerprint': 'sha256:${'b' * 64}',
    });
    expect(profile.serverCertificate, 'sha256:${'b' * 64}');
  });

  test('certificate pin is validated rather than silently ignored', () {
    expect(() => CiscoOpenConnectProfile.fromItem({
      'host': 'vpn.example.org', 'username': 'customer',
      'password': 'secret', 'servercert': '--no-cert-check',
    }), throwsFormatException);
    final profile = CiscoOpenConnectProfile.fromItem({
      'host': 'vpn.example.org', 'username': 'customer',
      'password': 'secret', 'servercert': 'sha256:${'a' * 64}',
    });
    expect(profile.serverCertificate, startsWith('sha256:'));
  });
}
