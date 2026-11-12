import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/sudoku_client_profile.dart';
import 'package:twinconnect/singbox_windows_config.dart';

void main() {
  const secret = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
      'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
      'cccccccccccccccccccccccccccccccc'
      'dddddddddddddddddddddddddddddddd';

  Map<String, dynamic> profile({
    String endpoint = 'vpn.example.org:18553',
    String key = secret,
    String mode = 'client',
  }) {
    final config = {
      'mode': mode,
      'transport': 'tcp',
      'server_address': endpoint,
      'local_address': '127.0.0.1',
      'local_port': 1080,
      'key': key,
      'aead': 'chacha20-poly1305',
      'padding_min': 5,
      'padding_max': 15,
      'ascii': 'prefer_entropy',
      'enable_pure_downlink': true,
      'multiplex': 'off',
      'httpmask': {'disable': false, 'mode': 'auto'},
    };
    return {
      'node_id': 42,
      'config_format': 'sudoku-json',
      'config': jsonEncode(config),
    };
  }

  test('validates central shared per-user Sudoku config without conversion', () {
    final item = SudokuClientProfile.fromItem(profile(), '42');
    expect(item, isNotNull);
    expect(item!.host, 'vpn.example.org');
    expect(item.port, 18553);
    final config = item.runtimeConfig(
        serverIpv4: '203.0.113.77', localPort: 17558);
    expect(config['mode'], 'client');
    expect(config['transport'], 'tcp');
    expect(config['server_address'], '203.0.113.77:18553');
    expect(config['key'], secret);
    expect(config['local_port'], 17558);
    expect(config['local_address'], '127.0.0.1');
    expect(config['aead'], 'chacha20-poly1305');
    expect(config['httpmask'], {'disable': false, 'mode': 'auto'});
    expect(config['rule_urls'], ['global']);
    expect(config.containsKey('external_controller'), false);
  });

  test('honors tunnel-forwarded port and refuses foreign node identities', () {
    final forwarded = SudokuClientProfile.fromItem(
        profile(endpoint: 'vpn.example.org:50022'), '42');
    expect(forwarded?.port, 50022);
    expect(forwarded?.runtimeConfig(
        serverIpv4: '203.0.113.33', localPort: 17559)['server_address'],
        '203.0.113.33:50022');
    expect(SudokuClientProfile.fromItem(
        profile(endpoint: 'vpn.example.org:bad'), '42'), isNull);
    expect(SudokuClientProfile.fromItem(profile(), '41'), isNull);
  });

  test('rejects invalid key, server mode and insecure AEAD', () {
    expect(SudokuClientProfile.fromItem(
        profile(key: 'not-a-key'), '42'), isNull);
    expect(SudokuClientProfile.fromItem(
        profile(mode: 'server'), '42'), isNull);
    final item = profile();
    final config = jsonDecode(item['config'] as String) as Map<String,dynamic>;
    config['aead'] = 'none';
    item['config'] = jsonEncode(config);
    expect(SudokuClientProfile.fromItem(item, '42'), isNull);
  });

  test('verified Sudoku SOCKS bridge preserves strict Windows TUN', () {
    final config = SingBoxWindowsConfig.compose(
      protocol: 'sudoku', item: const <String, dynamic>{},
      sudokuSocksPort: 17558,
      sudokuEndpointIPv4: '203.0.113.77',
    );
    final outbound = (config['outbounds'] as List).single as Map;
    expect(outbound['type'], 'socks');
    expect(outbound['server'], '127.0.0.1');
    expect(outbound['server_port'], 17558);
    final tun = (config['inbounds'] as List).single as Map;
    expect(tun['route_exclude_address'], ['203.0.113.77/32']);
    expect(tun['strict_route'], true);
    expect((config['route'] as Map)['final'], 'proxy');
    expect((config['dns'] as Map)['final'], 'dns-remote');
  });

  test('cannot use Sudoku tunnel bridge for wrong protocol or internal IP', () {
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'sudoku', item: const <String,dynamic>{},
      sudokuSocksPort: 17558,
    ), throwsFormatException);
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'openvpn', item: const <String,dynamic>{},
      sudokuSocksPort: 17558, sudokuEndpointIPv4: '203.0.113.77',
    ), throwsFormatException);
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'sudoku', item: const <String,dynamic>{},
      sudokuSocksPort: 17558, sudokuEndpointIPv4: '10.0.0.1',
    ), throwsFormatException);
  });
}
