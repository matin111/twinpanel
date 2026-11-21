import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_macos_config.dart';

Map<String, dynamic> sample({int version = 4}) => {
  'outbound': {
    'type': 'snell',
    'server': 'example.org',
    'server_port': 8388,
    'version': version,
    'psk': 'synthetic-test-secret',
  },
};

void main() {
  test('Snell v4 uses a guarded TUN with remote DNS', () {
    final config = SingBoxMacConfig.composeSnell(item: sample());
    final outbound = (config['outbounds'] as List).single;
    expect(outbound['type'], 'snell');
    expect(outbound['version'], 4);
    expect(config['route']['final'], 'proxy');
    expect(config['dns']['final'], 'dns-remote');
    expect((config['inbounds'] as List).single['strict_route'], true);
  });
  test('Snell v6 needs a valid pre-shared key', () {
    expect(SingBoxMacConfig.composeSnell(item: sample(version: 6))
        ['outbounds'][0]['version'], 6);
    final bad = sample(version: 6);
    (bad['outbound'] as Map)['psk'] = 'short';
    expect(() => SingBoxMacConfig.composeSnell(item: bad), throwsFormatException);
  });
  test('do not silently downgrade Snell version', () {
    expect(() => SingBoxMacConfig.composeSnell(item: sample(version: 3)),
        throwsFormatException);
  });
  test('reject unsafe or unsupported overrides', () {
    final bad = sample();
    (bad['outbound'] as Map)['detour'] = 'direct';
    expect(() => SingBoxMacConfig.composeSnell(item: bad), throwsFormatException);
  });
  test('reject Snell v6 legacy obfuscation', () {
    final bad = sample(version: 6);
    (bad['outbound'] as Map)['obfs_mode'] = 'http';
    expect(() => SingBoxMacConfig.composeSnell(item: bad), throwsFormatException);
  });
}
