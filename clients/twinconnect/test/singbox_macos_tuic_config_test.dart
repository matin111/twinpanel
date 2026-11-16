import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_macos_config.dart';

void main() {
  Map<String, dynamic> item({
    Map<String, dynamic>? outbound,
  }) => <String, dynamic>{
    'node_id': 18,
    'outbound': outbound ?? <String, dynamic>{
      'type': 'tuic',
      'server': 'example.org',
      'server_port': 443,
      'uuid': '2dd61d93-75d8-4da4-ac0e-6aece7eac365',
      'password': 'TEST_ONLY_PASSWORD',
      'congestion_control': 'bbr',
      'udp_relay_mode': 'native',
      'tls': {'enabled': true, 'server_name': 'example.org'},
    },
  };

  test('TUIC inherits the identical fail-closed macOS TUN DNS route', () {
    final tuic = SingBoxMacConfig.composeTuic(item: item());
    final hysteria = SingBoxMacConfig.composeHysteria2(item: {
      'outbound': {
        'type': 'hysteria2', 'server': 'example.org', 'server_port': 443,
        'password': 'TEST_ONLY_PASSWORD',
        'tls': {'enabled': true, 'server_name': 'example.org'},
      },
    });
    for (final key in ['inbounds', 'dns', 'route', 'log']) {
      expect(tuic[key], hysteria[key]);
    }
    final outbound = (tuic['outbounds'] as List).single as Map;
    expect(outbound['type'], 'tuic');
    expect(outbound['tag'], 'proxy');
    expect(outbound['zero_rtt_handshake'], false);
    expect(outbound['congestion_control'], 'bbr');
    expect(outbound['uuid'], '2dd61d93-75d8-4da4-ac0e-6aece7eac365');
  });

  test('TUIC rejects TLS bypass, replay and unsupported settings', () {
    for (final bad in <Map<String, dynamic>>[
      {'tls': {'enabled': true, 'insecure': true}},
      {'tls': {'enabled': false}},
      {'tls': {'enabled': true, 'disable_sni': true}},
      {'zero_rtt_handshake': true},
      {'udp_over_stream': true},
      {'congestion_control': 'unknown'},
      {'udp_relay_mode': 'invalid'},
      {'uuid': 'not-a-valid-uuid'},
      {'password': ''},
    ]) {
      final base = Map<String, dynamic>.from(
        item()['outbound'] as Map<String, dynamic>);
      base.addAll(bad);
      expect(() => SingBoxMacConfig.composeTuic(
        item: item(outbound: base)),
        throwsFormatException,
      );
    }
  });

  test('TUIC drops untrusted detour, routes and TLS custom fields', () {
    final base = Map<String, dynamic>.from(
      item()['outbound'] as Map<String, dynamic>);
    base['detour'] = 'direct';
    base['tls'] = {
      'enabled': true, 'server_name': 'example.org',
      'alpn': ['http/1.1'],
      'certificate_path': '/tmp/custom-ca.pem',
    };
    final config = SingBoxMacConfig.composeTuic(
      item: item(outbound: base));
    final outbound = (config['outbounds'] as List).single as Map;
    expect(outbound.containsKey('detour'), false);
    expect((outbound['tls'] as Map).keys.toSet(),
        {'enabled', 'server_name'});
    base['route'] = {'final': 'direct'};
    expect(() => SingBoxMacConfig.composeTuic(
      item: item(outbound: base)), throwsFormatException);
  });

  test('TUIC keeps Hysteria2 profile isolated from wrong protocol', () {
    expect(() => SingBoxMacConfig.composeTuic(item: {
      'outbound': {'type': 'hysteria2', 'server': 'example.org',
        'server_port': 443, 'password': 'test', 'tls': {'enabled': true}},
    }), throwsFormatException);
  });
}
