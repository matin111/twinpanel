import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/windows_app_route_engine.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Map<String, dynamic> config() => <String, dynamic>{
    'outbounds': <Map<String, dynamic>>[
      <String, dynamic>{'tag': 'proxy', 'type': 'socks'},
    ],
    'route': <String, dynamic>{
      'final': 'proxy',
      'rules': <Map<String, dynamic>>[
        <String, dynamic>{'port': 53, 'action': 'hijack-dns'},
        <String, dynamic>{'ip_version': 6, 'action': 'reject'},
        <String, dynamic>{'action': 'sniff'},
      ],
    },
  };

  const target = r'C:\Program Files\Browser\browser.exe';

  test('full-device engine preserves original protected TUN policy', () {
    final before = config();
    const WindowsAppRoutePolicy(
      mode: WindowsAppRoutingMode.fullTunnel, applicationPaths: [],
    ).applyTo(before);
    expect((before['route'] as Map)['final'], 'proxy');
    expect((before['route'] as Map)['rules'], hasLength(3));
    expect(before['outbounds'], hasLength(1));
  });

  test('only selected app uses the proxy on sing-box Windows', () {
    final cfg = config();
    const WindowsAppRoutePolicy(
      mode: WindowsAppRoutingMode.includeSelected,
      applicationPaths: [target],
    ).applyTo(cfg);
    final route = cfg['route'] as Map<String, dynamic>;
    final rules = route['rules'] as List;
    expect(route['final'], 'direct');
    expect(rules.first['action'], 'hijack-dns');
    expect(rules[1]['action'], 'reject');
    expect(rules[2]['process_path'], [target]);
    expect(rules[2]['outbound'], 'proxy');
    expect(rules[3]['action'], 'sniff');
    expect((cfg['outbounds'] as List).last['type'], 'direct');
  });

  test('all except selected app use proxy on sing-box Windows', () {
    final cfg = config();
    const WindowsAppRoutePolicy(
      mode: WindowsAppRoutingMode.excludeSelected,
      applicationPaths: [target],
    ).applyTo(cfg);
    final route = cfg['route'] as Map<String, dynamic>;
    expect(route['final'], 'proxy');
    expect((route['rules'] as List)[2]['outbound'], 'direct');
    expect((route['rules'] as List)[2]['process_path'], [target]);
  });

  test('missing app or unsafe executable path cannot enable split routing', () {
    expect(() => const WindowsAppRoutePolicy(
      mode: WindowsAppRoutingMode.includeSelected, applicationPaths: [],
    ).validate(), throwsFormatException);
    expect(() => const WindowsAppRoutePolicy(
      mode: WindowsAppRoutingMode.excludeSelected,
      applicationPaths: ['bad-script.ps1'],
    ).validate(), throwsFormatException);
  });

  test('saved Windows split routing is reused by native TUN startup', () async {
    SharedPreferences.setMockInitialValues({});
    const saved = WindowsAppRoutePolicy(
      mode: WindowsAppRoutingMode.excludeSelected,
      applicationPaths: [target],
    );
    await saved.persist();
    final read = await WindowsAppRoutePolicy.load();
    expect(read.mode, WindowsAppRoutingMode.excludeSelected);
    expect(read.applicationPaths, [target]);
    final tunnel = File('lib/windows_singbox_tunnel.dart').readAsStringSync();
    expect(tunnel, contains('WindowsAppRoutePolicy.load()'));
    expect(tunnel, contains('routingPolicy.applyTo(config)'));
  });

  test('system proxy engine never changes device routes or WinHTTP settings', () {
    final engine = File('tools/windows_system_proxy.ps1').readAsStringSync();
    final installer = File('installer.iss').readAsStringSync();
    final settings = File('lib/vpn_settings.dart').readAsStringSync();
    expect(engine, contains('LOCAL_SOCKS5_NOT_VERIFIED'));
    // The TCP stream may split a valid 2-byte SOCKS5 reply across reads.
    expect(engine, contains(r'while ($received -lt $reply.Length)'));
    expect(engine, contains(r'$received += $count'));
    expect(engine, contains('Restore-Values'));
    expect(engine, contains('PROXY_SETTINGS_CHANGED_EXTERNALLY_DO_NOT_OVERWRITE'));
    expect(engine, contains('InternetSetOptionW'));
    expect(engine, isNot(contains('netsh winhttp set')));
    expect(engine, isNot(contains('Set-NetIPInterface')));
    expect(installer, contains('windows_system_proxy.ps1'));
    expect(installer, contains('TwinConnect - Restore System Proxy'));
    expect(settings, contains("Key('vpnSystemProxyToggle')"));
    expect(settings, contains("Key('vpnPickRoutingApp')"));
    expect(settings, contains('split_tunnel_mode:'));
    expect(settings, contains('system_proxy_status:'));
  });
}
