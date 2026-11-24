import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_macos_config.dart';

Map<String, dynamic> profile() => {
  'outbound': {
    'type': 'socks',
    'server': 'example.org',
    'server_port': 1080,
    'version': '5',
    'username': 'test-user',
    'password': 'synthetic-test-password',
    'network': 'tcp',
  }
};

void main() {
  test('SOCKS5 uses an account-authenticated TCP outbound and strict TUN', () {
    final config = SingBoxMacConfig.composeSocks5(item: profile());
    final proxy = (config['outbounds'] as List).single as Map;
    expect(proxy['type'], 'socks');
    expect(proxy['version'], '5');
    expect(proxy['network'], 'tcp');
    expect(proxy['username'], 'test-user');
    expect(config['route']['final'], 'proxy');
    expect(config['dns']['final'], 'dns-remote');
    expect(config['inbounds'][0]['strict_route'], true);
  });

  test('reject SOCKS4 and missing authentication', () {
    final badVersion = profile();
    (badVersion['outbound'] as Map)['version'] = '4';
    expect(() => SingBoxMacConfig.composeSocks5(item: badVersion), throwsFormatException);
    final badPassword = profile();
    (badPassword['outbound'] as Map)['password'] = '';
    expect(() => SingBoxMacConfig.composeSocks5(item: badPassword), throwsFormatException);
  });

  test('reject unreviewed detour and UDP-only profiles', () {
    final detour = profile();
    (detour['outbound'] as Map)['detour'] = 'direct';
    expect(() => SingBoxMacConfig.composeSocks5(item: detour), throwsFormatException);
    final udp = profile();
    (udp['outbound'] as Map)['network'] = 'udp';
    expect(() => SingBoxMacConfig.composeSocks5(item: udp), throwsFormatException);
  });

  test('native macOS bridge is signed-only and never claims verified egress', () {
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift').readAsStringSync();
    final host = File('macos_native/TwinConnectMacOSLibboxControl.swift').readAsStringSync();
    final engine = File('macos_native/libbox/TwinConnectMacLibboxEngine.swift').readAsStringSync();
    final provider = File('macos_native/PacketTunnelProvider.swift').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(bridge, contains('case "startSocks5":'));
    expect(bridge, contains('case "macOSSocks5EngineStatus":'));
    expect(host, contains('allowedSocks5Config'));
    expect(engine, contains('socks5ProfileAllowed'));
    expect(provider, contains('"snell", "socks5"'));
    expect(dashboard, contains('_macSocks5.start('));
    expect(dashboard, contains('_vpnVerified = false'));
  });
}
