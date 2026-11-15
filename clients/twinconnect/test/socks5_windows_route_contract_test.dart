import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_profile_validator.dart';
import 'package:twinconnect/singbox_windows_config.dart';
import 'package:twinconnect/modern_transport_probe.dart';

Map<String, dynamic> liveStyleProfile({
  String server = '93.184.216.34',
  String transport = 'tcp',
  String version = '5',
}) => {
  'node_id': 25,
  'config_format': 'sing-box',
  'outbound': {
    'type': 'socks',
    'tag': 'socks5-node',
    'server': server,
    'server_port': 1081,
    'version': version,
    'network': transport,
    'username': 'synthetic-user',
    'password': 'synthetic-password',
  },
};

void main() {
  test('real panel SOCKS5 outbound preserves authenticated TCP credentials', () {
    final item = liveStyleProfile();
    final outbound = SingBoxProfileValidator.validateOutbound(
      protocolCode: 'socks5', item: item,
    );
    expect(outbound['type'], 'socks');
    expect(outbound['version'], '5');
    expect(outbound['network'], 'tcp');
    expect(outbound['username'], 'synthetic-user');
    expect(outbound['password'], 'synthetic-password');
    final probe = ModernTransportProbe.proxyConfig(
      protocol: 'socks5', profile: item, port: 31234,
    );
    expect((probe['outbounds'] as List).single['type'], 'socks');
    final local = (probe['inbounds'] as List).single as Map;
    expect(local['listen'], '127.0.0.1');
    expect(local['listen_port'], 31234);
  });

  test('SOCKS5 TUN pins public remote IP to prevent TCP routing loop', () {
    final composed = SingBoxWindowsConfig.compose(
      protocol: 'socks5', item: liveStyleProfile(),
    );
    final tun = (composed['inbounds'] as List).single as Map;
    expect(tun['route_exclude_address'], ['93.184.216.34/32']);
    expect(tun['auto_route'], isTrue);
    expect(tun['strict_route'], isTrue);
    final outbound = (composed['outbounds'] as List).single as Map;
    expect(outbound['tag'], 'proxy');
    expect(outbound['server'], '93.184.216.34');
    expect(outbound['version'], '5');
    expect(outbound['username'], 'synthetic-user');
    expect(outbound['password'], 'synthetic-password');
    final dns = composed['dns'] as Map;
    expect(dns['final'], 'dns-remote');
    expect((composed['route'] as Map)['final'], 'proxy');
  });

  test('SOCKS5 domain is pinned at runtime while retaining authentication', () {
    final composed = SingBoxWindowsConfig.compose(
      protocol: 'socks5',
      item: liveStyleProfile(server: 'socks.example.org'),
      resolvedServer: '93.184.216.35',
    );
    expect((composed['inbounds'] as List).single['route_exclude_address'],
        ['93.184.216.35/32']);
    expect((composed['outbounds'] as List).single['server'], '93.184.216.35');
    expect((composed['outbounds'] as List).single['username'], 'synthetic-user');
  });

  test('SOCKS5 refuses missing credentials, UDP-only and protocol downgrade', () {
    final missing = liveStyleProfile();
    (missing['outbound'] as Map).remove('password');
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'socks5', item: missing,
    ), throwsFormatException);
    final udp = liveStyleProfile(transport: 'udp');
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'socks5', item: udp,
    ), throwsFormatException);
    final v4 = liveStyleProfile(version: '4');
    expect(() => SingBoxProfileValidator.validateOutbound(
      protocolCode: 'socks5', item: v4,
    ), throwsFormatException);
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'socks5', item: liveStyleProfile(server: '127.0.0.1'),
    ), throwsFormatException);
  });
}
