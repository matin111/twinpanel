import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_macos_config.dart';

void main() {
  Map<String, dynamic> outbound() => <String, dynamic>{
    'type': 'naive',
    'server': 'example.org',
    'server_port': 443,
    'username': 'SYNTHETIC_USER',
    'password': 'SYNTHETIC_SECRET',
    'tls': {'enabled': true, 'server_name': 'example.org'},
  };
  Map<String, dynamic> item(Map<String, dynamic> profile) =>
      <String, dynamic>{'node_id': 19, 'outbound': profile};

  test('Naive uses protected Libbox TUN, DNS and TCP-safe default', () {
    final naive = SingBoxMacConfig.composeNaive(item: item(outbound()));
    final hy2 = SingBoxMacConfig.composeHysteria2(item: item({
      'type': 'hysteria2',
      'server': 'example.org',
      'server_port': 443,
      'password': 'SYNTHETIC',
      'tls': {'enabled': true, 'server_name': 'example.org'},
    }));
    for (final field in ['dns', 'route', 'inbounds', 'log']) {
      expect(naive[field], hy2[field]);
    }
    final selected = (naive['outbounds'] as List).single as Map;
    expect(selected['type'], 'naive');
    expect(selected['tag'], 'proxy');
    expect(selected['username'], 'SYNTHETIC_USER');
    expect(selected['insecure_concurrency'], 0);
    expect(selected.containsKey('quic'), false);
    expect(selected.containsKey('udp_over_tcp'), false);
  });

  test('Naive rejects absent credentials and TLS certificate bypass', () {
    for (final invalid in <Map<String, dynamic>>[
      {'username': ''},
      {'password': ''},
      {'tls': {'enabled': false, 'server_name': 'example.org'}},
      {'tls': {'enabled': true, 'insecure': true}},
      {'tls': {'enabled': true, 'disable_sni': true}},
      {'tls': {'enabled': true, 'reality': {'enabled': true}}},
      {'insecure_concurrency': 2},
      {'quic': 'true'},
      {'udp_over_tcp': 'true'},
      {'quic_congestion_control': 'unknown'},
      {'extra_headers': {'x-example': 'arbitrary'}},
    ]) {
      final source = outbound()..addAll(invalid);
      expect(() => SingBoxMacConfig.composeNaive(item: item(source)),
          throwsFormatException);
    }
  });

  test('Naive only enables QUIC and UDP-over-TCP when explicitly configured', () {
    final source = outbound()
      ..addAll({'quic': true, 'quic_congestion_control': 'bbr',
        'udp_over_tcp': true, 'detour': 'direct'});
    final composed = SingBoxMacConfig.composeNaive(item: item(source));
    final selected = (composed['outbounds'] as List).single as Map;
    expect(selected['quic'], true);
    expect(selected['quic_congestion_control'], 'bbr');
    expect(selected['udp_over_tcp'], true);
    expect(selected.containsKey('detour'), false);
    source['route'] = {'final': 'direct'};
    expect(() => SingBoxMacConfig.composeNaive(item: item(source)),
        throwsFormatException);
  });

  test('Naive cannot use credentials from other protocols', () {
    final source = outbound()..['type'] = 'anytls';
    expect(() => SingBoxMacConfig.composeNaive(item: item(source)),
        throwsFormatException);
  });
}
