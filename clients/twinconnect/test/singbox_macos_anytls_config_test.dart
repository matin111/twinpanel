import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_macos_config.dart';

void main() {
  Map<String, dynamic> outbound() => <String, dynamic>{
        'type': 'anytls',
        'server': 'example.org',
        'server_port': 443,
        'password': 'SYNTHETIC_ONLY',
        'tls': {'enabled': true, 'server_name': 'example.org'},
      };
  Map<String, dynamic> item(Map<String, dynamic> profile) =>
      <String, dynamic>{'node_id': 19, 'outbound': profile};

  test('AnyTLS is isolated from TUIC/Hysteria2 and uses shared secure TUN', () {
    final anytls = SingBoxMacConfig.composeAnyTls(item: item(outbound()));
    final hysteria2 = SingBoxMacConfig.composeHysteria2(item: item({
      'type': 'hysteria2',
      'server': 'example.org',
      'server_port': 443,
      'password': 'SYNTHETIC_ONLY',
      'tls': {'enabled': true, 'server_name': 'example.org'},
    }));
    for (final field in ['dns', 'route', 'inbounds', 'log']) {
      expect(anytls[field], hysteria2[field]);
    }
    final chosen = (anytls['outbounds'] as List).single as Map;
    expect(chosen['type'], 'anytls');
    expect(chosen['tag'], 'proxy');
    expect(chosen['server'], 'example.org');
    expect(chosen['password'], 'SYNTHETIC_ONLY');
    expect(chosen.containsKey('detour'), false);
  });

  test('AnyTLS validates idle settings and rejects insecure TLS', () {
    final examples = <Map<String, dynamic>>[
      {'password': ''},
      {'tls': {'enabled': true, 'insecure': true}},
      {'tls': {'enabled': false}},
      {'tls': {'enabled': true, 'disable_sni': true}},
      {'idle_session_check_interval': '0s'},
      {'idle_session_timeout': 'bogus'},
      {'min_idle_session': -1},
      {'min_idle_session': 513},
    ];
    for (final invalid in examples) {
      final candidate = outbound()..addAll(invalid);
      expect(
        () => SingBoxMacConfig.composeAnyTls(item: item(candidate)),
        throwsFormatException,
      );
    }
  });

  test('AnyTLS allows valid idles and discards unknown routes and detours', () {
    final candidate = outbound()
      ..addAll({
        'min_idle_session': 5,
        'idle_session_timeout': '30s',
        'idle_session_check_interval': '30s',
        'detour': 'direct',
      });
    final generated = SingBoxMacConfig.composeAnyTls(item: item(candidate));
    final selected = (generated['outbounds'] as List).single as Map;
    expect(selected['min_idle_session'], 5);
    expect(selected['idle_session_timeout'], '30s');
    expect(selected.containsKey('detour'), false);
    candidate['route'] = {'final': 'direct'};
    expect(() => SingBoxMacConfig.composeAnyTls(item: item(candidate)),
        throwsFormatException);
  });

  test('AnyTLS never accepts a TUIC or Hysteria2 outbound', () {
    final candidate = outbound()..['type'] = 'tuic';
    expect(() => SingBoxMacConfig.composeAnyTls(item: item(candidate)),
        throwsFormatException);
  });
}
