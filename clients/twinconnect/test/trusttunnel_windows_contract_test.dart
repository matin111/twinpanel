import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/trusttunnel_client_profile.dart';
import 'package:twinconnect/singbox_windows_config.dart';

String syntheticLink({int version = 1, bool badSkip = false, bool cert = false}) {
  final b = <int>[];
  void put(int tag, List<int> value) {
    // All test TLV values here are shorter than 16384.
    b.add(tag);
    if (value.length < 64) {
      b.add(value.length);
    } else {
      b.add(0x40 | (value.length >> 8), value.length & 0xff);
    }
    b.addAll(value);
  }
  put(0, [version]);
  put(1, utf8.encode('vpn.example.com'));
  put(2, utf8.encode('93.184.216.34:443'));
  put(5, utf8.encode('test-user'));
  put(6, utf8.encode('test-secret'));
  if (badSkip) put(7, [1]);
  if (cert) put(8, [0x30, 0x81, 100, ...List.filled(100, 0)]);
  return 'tt://?' + base64Url.encode(b).replaceAll('=', '');
}

Map<String, dynamic> item(String uri) => {
  'config_format': 'trusttunnel-deeplink', 'node_id': 25,
  'config': uri,
};

void main() {
  test('official TrustTunnel v1 link is decoded without losing identity', () async {
    final decoded = TrustTunnelClientProfile.fromItem(item(syntheticLink()));
    expect(decoded.username, 'test-user');
    expect(decoded.password, 'test-secret');
    expect(decoded.hostname, 'vpn.example.com');
    expect(await decoded.resolveEndpointIPv4(), '93.184.216.34');
    final toml = decoded.privateSocksToml('93.184.216.34', 39421);
    expect(toml, contains('addresses = ["93.184.216.34:443"]'));
    expect(toml, contains('username = "test-user"'));
    expect(toml, contains('password = "test-secret"'));
    expect(toml, contains('[listener.socks]'));
    expect(toml, contains('127.0.0.1:39421'));
    expect(toml, isNot(contains('[listener.tun]')));
    expect(toml, contains('skip_verification = false'));

    final bridge = SingBoxWindowsConfig.compose(
      protocol: 'trusttunnel', item: const {},
      trusttunnelSocksPort: 39421,
      trusttunnelEndpointIPv4: '93.184.216.34',
    );
    final proxy = (bridge['outbounds'] as List).single as Map;
    expect(proxy['server'], '127.0.0.1');
    expect(proxy['server_port'], 39421);
    expect(proxy['type'], 'socks');
    expect((bridge['route'] as Map)['final'], 'proxy');
    final tun = (bridge['inbounds'] as List).single as Map;
    expect(tun['strict_route'], isTrue);
    expect(tun['route_exclude_address'], ['93.184.216.34/32']);
  });

  test('certificate is included and verification is never disabled', () {
    final withCert = TrustTunnelClientProfile.fromItem(
        item(syntheticLink(cert: true)));
    expect(withCert.certificatePem, contains('BEGIN CERTIFICATE'));
    expect(withCert.privateSocksToml('93.184.216.34', 39421),
        contains('certificate = '));
    expect(() => TrustTunnelClientProfile.fromItem(
      item(syntheticLink(badSkip: true))), throwsFormatException);
  });

  test('unsupported versions and missing identity fail closed', () {
    expect(() => TrustTunnelClientProfile.fromItem(
        item(syntheticLink(version: 2))), throwsFormatException);
    expect(() => TrustTunnelClientProfile.fromItem(item('tt://?!!')),
        throwsFormatException);
    final p = TrustTunnelClientProfile.fromItem(item(syntheticLink()));
    expect(() => p.privateSocksToml('192.168.0.1', 39421),
        throwsFormatException);
    expect(() => p.privateSocksToml('93.184.216.34', 80),
        throwsFormatException);
  });

  test('native process owns private credential-bearing TOML and cleanup', () {
    final native = File('native/windows/twinconnect_trusttunnel_guard.h')
        .readAsStringSync();
    final bridge = File('tools/install_windows_native.py').readAsStringSync();
    final core = File('lib/windows_trusttunnel_proxy.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(native, contains('JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE'));
    expect(native, contains('ConvertSidToStringSidW'));
    expect(native, contains('DeleteFileW(ConfigPath().c_str())'));
    expect(native, contains('trusttunnel_client.exe'));
    expect(bridge, contains('stageTrustTunnelConfig'));
    expect(bridge, contains('guardTrustTunnelProcess'));
    expect(core, contains("['--config', path]"));
    expect(core, contains("'--socks5-hostname'"));
    expect(core, isNot(contains('print(config)')));
    expect(dashboard, contains('_startTrustTunnel'));
    expect(dashboard, contains('_trusttunnelProxy.stop()'));
  });
}
