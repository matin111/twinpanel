import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/modern_transport_probe.dart';

void main() {
  const variants = <String, String>{
    'hysteria2': 'hysteria2',
    'tuic': 'tuic',
    'anytls': 'anytls',
    'naive': 'naive',
    'snell': 'snell',
    'socks5': 'socks',
  };
  for (final entry in variants.entries) {
    test('${entry.key} loopback proxy config is isolated and not a system VPN',
        () {
      final outbound = <String, dynamic>{
        'type': entry.value,
        'server': 'vpn.example.org',
        'server_port': 443,
        'password': 'synthetic',
        if (entry.key == 'tuic')
          'uuid': '2DD61D93-75D8-4DA4-AC0E-6AECE7EAC365',
        if (entry.key == 'naive' || entry.key == 'socks5')
          'username': 'synthetic',
        if (entry.key == 'socks5') ...{'version': '5', 'network': 'tcp'},
        if (entry.key == 'snell') ...{'version': 4, 'psk': 'synthetic'},
        if (!{'snell', 'socks5'}.contains(entry.key))
          'tls': {'enabled': true},
      };
      final config = ModernTransportProbe.proxyConfig(
        protocol: entry.key, profile: {'outbound': outbound}, port: 32567);
      final inbound = (config['inbounds'] as List).single as Map;
      expect(inbound['type'], 'mixed');
      expect(inbound['listen'], '127.0.0.1');
      expect(inbound['listen_port'], 32567);
      expect(config.containsKey('dns'), isFalse);
      expect(config['route'], {'final': 'proxy'});
      expect((config['outbounds'] as List).single['type'], entry.value);
      expect((config['outbounds'] as List).single['tag'], 'proxy');
      expect(outbound.containsKey('tag'), isFalse);
    });
  }

  test('preflight pins the same endpoint while keeping TLS host validation', () {
    final item = {'outbound': {
      'type': 'hysteria2',
      'server': 'vpn.example.org',
      'server_port': 443,
      'password': 'synthetic',
      'tls': {'enabled': true},
    }};
    final config = ModernTransportProbe.proxyConfig(
      protocol: 'hysteria2', profile: item, port: 32567,
      resolvedServer: '203.0.113.17');
    final outbound = (config['outbounds'] as List).single as Map;
    expect(outbound['server'], '203.0.113.17');
    expect((outbound['tls'] as Map)['server_name'], 'vpn.example.org');
    expect(((item['outbound'] as Map)['server']), 'vpn.example.org');
    expect(() => ModernTransportProbe.proxyConfig(
      protocol: 'hysteria2', profile: item, port: 32567,
      resolvedServer: 'not-an-ip'), throwsFormatException);
  });

  test('remote listener and unsupported protocols are rejected', () {
    expect(() => ModernTransportProbe.proxyConfig(
      protocol: 'hysteria2', profile: {'outbound': {
        'type': 'hysteria2', 'server': 'example.org',
        'server_port': 443, 'tls': {'enabled': true}
      }}, port: 0), throwsFormatException);
    expect(() => ModernTransportProbe.proxyConfig(
      protocol: 'wireguard', profile: {}, port: 33211),
      throwsFormatException);
    expect(() => ModernTransportProbe.proxyConfig(
      protocol: 'shadowtls', profile: {'outbound': {
        'type': 'shadowtls', 'server': 'example.org',
        'server_port': 443,
      }}, port: 33211), throwsFormatException);
  });
}
