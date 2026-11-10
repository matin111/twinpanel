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
    expect((dns['servers'] as List).single['detour'], 'proxy');
    expect((item['outbound'] as Map).containsKey('tag'), isFalse);
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
