import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_windows_config.dart';

void main() {
  final item = {
    'outbound': {
      'type': 'hysteria2', 'server': 'vpn.example.org',
      'server_port': 443, 'password': 'private-test-key',
      'tls': {'enabled': true, 'server_name': 'vpn.example.org'},
    },
  };

  test('composes secure TUN, strict routing and DNS via proxy', () {
    final config = SingBoxWindowsConfig.compose(
      protocol: 'hysteria2', item: item);
    final tun = (config['inbounds'] as List).single as Map;
    final routing = config['route'] as Map;
    final outbounds = config['outbounds'] as List;
    final dns = config['dns'] as Map;
    expect(tun['type'], 'tun');
    expect(tun['auto_route'], isTrue);
    expect(tun['strict_route'], isTrue);
    expect(tun['dns_mode'], 'hijack');
    expect(routing['auto_detect_interface'], isTrue);
    expect(routing['final'], 'proxy');
    expect((outbounds.first as Map)['password'], 'private-test-key');
    final servers = dns['servers'] as List;
    expect(servers, hasLength(2));
    expect((servers[0] as Map)['tag'], 'dns-bootstrap');
    expect((servers[0] as Map)['type'], 'local');
    expect((servers[0] as Map).containsKey('detour'), isFalse);
    expect((servers[1] as Map)['detour'], 'proxy');
    expect((servers[1] as Map)['type'], 'https');
    expect((servers[1] as Map)['server_port'], 443);
    expect((servers[1] as Map)['path'], '/dns-query');
    expect(dns['final'], 'dns-remote');
    expect(routing['default_domain_resolver'], 'dns-bootstrap');
    expect(dns['cache_capacity'], 4096);
    expect(dns['optimistic'], isFalse);
    expect(((routing['rules'] as List).first as Map)['action'], 'hijack-dns');
    expect(((routing['rules'] as List).first as Map)['protocol'], 'dns');
    expect((item['outbound'] as Map).containsKey('tag'), isFalse);
  });

  test('pins the resolved endpoint without weakening TLS identity', () {
    final config = SingBoxWindowsConfig.compose(
      protocol: 'hysteria2',
      item: {
        'outbound': {
          'type': 'hysteria2', 'server': 'vpn.example.org',
          'server_port': 443, 'password': 'private-test-key',
          'tls': {'enabled': true},
        },
      },
      resolvedServer: '203.0.113.15',
    );
    final outbound = (config['outbounds'] as List).single as Map;
    expect(outbound['server'], '203.0.113.15');
    expect((outbound['tls'] as Map)['server_name'], 'vpn.example.org');
    expect((config['route'] as Map)['auto_detect_interface'], isTrue);
    expect((config['route'] as Map)['default_domain_resolver'], 'dns-remote');
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'hysteria2', item: item, resolvedServer: 'not-an-ip'),
      throwsFormatException);
  });

  test('preserves explicit TLS SNI when pinning an endpoint', () {
    final config = SingBoxWindowsConfig.compose(
      protocol: 'hysteria2', item: item, resolvedServer: '203.0.113.20');
    final outbound = (config['outbounds'] as List).single as Map;
    expect(outbound['server'], '203.0.113.20');
    expect((outbound['tls'] as Map)['server_name'], 'vpn.example.org');
    expect((item['outbound'] as Map)['server'], 'vpn.example.org');
  });


  test('literal IP needs no local DNS resolver for TUN operation', () {
    final config = SingBoxWindowsConfig.compose(
      protocol: 'hysteria2',
      item: {
        'outbound': {
          'type': 'hysteria2', 'server': '203.0.113.20',
          'server_port': 443, 'password': 'private-test-key',
          'tls': {'enabled': true, 'server_name': 'vpn.example.org'},
        },
      },
    );
    expect((config['route'] as Map)['default_domain_resolver'], 'dns-remote');
    expect(((config['outbounds'] as List).single as Map)['server'],
        '203.0.113.20');
  });

  test('rejects a wrong or unstructured outbound without fallbacks', () {
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'tuic', item: item), throwsFormatException);
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'hysteria2', item: {'uri': 'hysteria2://secret'}),
        throwsFormatException);
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'shadowtls', item: item), throwsFormatException);
  });
}
