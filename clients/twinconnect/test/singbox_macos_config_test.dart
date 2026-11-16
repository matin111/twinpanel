import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_macos_config.dart';

void main() {
  Map<String, dynamic> item({Map<String, dynamic>? outbound}) => {
        'node_id': 18,
        'outbound': outbound ?? <String, dynamic>{
          'type': 'hysteria2',
          'server': 'example.org',
          'server_port': 443,
          'password': 'synthetic-secret-not-live',
          'tls': {'enabled': true, 'server_name': 'example.org'},
        },
      };

  test('macOS Libbox TUN and DNS never use a direct default egress', () {
    final original = item();
    final raw = SingBoxMacConfig.encodeForEphemeralTunnel(item: original);
    final config = jsonDecode(raw) as Map<String, dynamic>;
    final inbounds = config['inbounds'] as List<dynamic>;
    final tun = inbounds.single as Map;
    final route = config['route'] as Map;
    final dns = config['dns'] as Map;
    final remote = (dns['servers'] as List)[1] as Map;
    final proxy = (config['outbounds'] as List).single as Map;

    expect(tun['type'], 'tun');
    expect(tun['auto_route'], true);
    expect(tun['strict_route'], true);
    expect(tun['dns_mode'], 'hijack');
    expect(route['final'], 'proxy');
    expect((route['rules'] as List).first, {'port': 53, 'action': 'hijack-dns'});
    expect((route['rules'] as List).last,
        {'ip_version': 6, 'action': 'reject'});
    expect((dns['servers'] as List).first['tag'], 'dns-bootstrap');
    expect(remote['type'], 'https');
    expect(remote['detour'], 'proxy');
    expect(dns['final'], 'dns-remote');
    expect(proxy['type'], 'hysteria2');
    expect(proxy['password'], 'synthetic-secret-not-live');
    expect((original['outbound'] as Map).containsKey('tag'), false);
    expect(config.toString(), isNot(contains('direct')));
  });

  test('malicious profile cannot inject routes or insecure TLS', () {
    final injected = item(outbound: {
      'type': 'hysteria2',
      'server': 'example.org',
      'server_port': 443,
      'password': 'synthetic',
      'tls': {'enabled': true, 'server_name': 'example.org'},
      'detour': 'direct',
      'route': {'final': 'direct'},
      'inbounds': [{'type': 'mixed'}],
    });
    final built = SingBoxMacConfig.composeHysteria2(item: injected);
    final outbound = (built['outbounds'] as List).single as Map;
    expect(outbound.containsKey('route'), false);
    expect(outbound.containsKey('inbounds'), false);
    expect(outbound.containsKey('detour'), false);

    for (final tls in [
      {'enabled': true, 'insecure': true},
      {'enabled': false},
      {'enabled': true, 'disable_sni': true},
      {'enabled': true, 'utls': {'enabled': true}},
    ]) {
      expect(
        () => SingBoxMacConfig.composeHysteria2(item: item(outbound: {
          'type': 'hysteria2',
          'server': 'example.org',
          'server_port': 443,
          'password': 'synthetic',
          'tls': tls,
        })),
        throwsFormatException,
      );
    }
  });

  test('rejects URI-only, wrong-protocol and missing credentials', () {
    expect(() => SingBoxMacConfig.composeHysteria2(item: {
      'uri': 'hysteria2://secret@example.org:443',
    }), throwsFormatException);
    expect(() => SingBoxMacConfig.composeHysteria2(item: item(outbound: {
      'type': 'tuic',
      'server': 'example.org',
      'server_port': 443,
      'tls': {'enabled': true},
    })), throwsFormatException);
    expect(() => SingBoxMacConfig.composeHysteria2(item: item(outbound: {
      'type': 'hysteria2',
      'server': 'example.org',
      'server_port': 443,
      'tls': {'enabled': true},
    })), throwsFormatException);
  });

  test('preserves supported Hysteria2 obfuscation and bandwidth', () {
    final config = SingBoxMacConfig.composeHysteria2(item: item(outbound: {
      'type': 'hysteria2',
      'server': 'example.org',
      'server_port': 8443,
      'password': 'synthetic',
      'tls': {'enabled': true, 'server_name': 'example.org'},
      'obfs': {'type': 'salamander', 'password': 'test-obfs'},
      'up_mbps': 50,
      'down_mbps': 100,
    }));
    final outbound = (config['outbounds'] as List).single as Map;
    expect(outbound['obfs'], {'type': 'salamander', 'password': 'test-obfs'});
    expect(outbound['up_mbps'], 50);
    expect(outbound['down_mbps'], 100);
  });
}
