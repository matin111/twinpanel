import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/macos_mieru_tun_relay.dart';

void main() {
  test('offline relay targets only the in-extension Mieru loopback port', () {
    final config = MacMieruTunRelay.compose(
      localSocksPort: 34101,
      coreOwnedByPacketTunnel: true,
      endpointPinnedOutsideTunnel: true,
    );
    final proxy = (config['outbounds'] as List).single as Map;
    expect(proxy['type'], 'socks');
    expect(proxy['version'], '5');
    expect(proxy['server'], '127.0.0.1');
    expect(proxy['server_port'], 34101);
    expect(proxy['network'], 'tcp');
    expect(proxy, isNot(contains('password')));
    expect(config['route']['final'], 'proxy');
    expect(config['dns']['final'], 'dns-remote');
    final rules = (config['route']['rules'] as List).cast<Map>();
    expect(
      rules.any((rule) => rule['ip_version'] == 6 &&
          rule['action'] == 'reject'),
      isTrue,
    );
    expect(config['inbounds'][0]['strict_route'], true);
  });

  test('refuses to prepare relay without extension ownership', () {
    expect(() => MacMieruTunRelay.compose(
      localSocksPort: 34101,
      coreOwnedByPacketTunnel: false,
      endpointPinnedOutsideTunnel: true,
    ), throwsFormatException);
  });

  test('refuses to prepare relay without pre-TUN route pin', () {
    expect(() => MacMieruTunRelay.compose(
      localSocksPort: 34101,
      coreOwnedByPacketTunnel: true,
      endpointPinnedOutsideTunnel: false,
    ), throwsFormatException);
  });

  test('refuses privileged and invalid loopback ports', () {
    for (final port in [0, 80, 1024, 65536]) {
      expect(() => MacMieruTunRelay.compose(
        localSocksPort: port,
        coreOwnedByPacketTunnel: true,
        endpointPinnedOutsideTunnel: true,
      ), throwsFormatException);
    }
  });
}
