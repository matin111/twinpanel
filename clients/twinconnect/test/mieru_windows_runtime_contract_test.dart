import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_windows_config.dart';

void main() {
  test('Mieru SOCKS bridge remains strict, pinned and local-only', () {
    final config = SingBoxWindowsConfig.compose(
      protocol: 'mieru', item: const {},
      mieruSocksPort: 34101, mieruEndpointIPv4: '93.184.216.34',
    );
    final rows = config['outbounds'] as List;
    expect(rows, hasLength(1));
    final proxy = rows.single as Map;
    expect(proxy['type'], 'socks');
    expect(proxy['tag'], 'proxy');
    expect(proxy['server'], '127.0.0.1');
    expect(proxy['server_port'], 34101);
    final tun = (config['inbounds'] as List).single as Map;
    expect(tun['strict_route'], isTrue);
    expect(tun['route_exclude_address'], ['93.184.216.34/32']);
    expect((config['route'] as Map)['final'], 'proxy');
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'mieru', item: const {}, mieruSocksPort: 34101,
    ), throwsFormatException);
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'wireguard', item: const {},
      mieruSocksPort: 34101, mieruEndpointIPv4: '93.184.216.34',
    ), throwsFormatException);
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'mieru', item: const {}, mieruSocksPort: 34101,
      mieruEndpointIPv4: '93.184.216.34', sudokuSocksPort: 34201,
      sudokuEndpointIPv4: '93.184.216.35',
    ), throwsFormatException);
  });

  test('official Mieru engine is guarded with Windows user-only config', () {
    final native = File('native/windows/twinconnect_mieru_guard.h')
        .readAsStringSync();
    final install = File('tools/install_windows_native.py')
        .readAsStringSync();
    final runner = File('lib/windows_mieru_proxy.dart')
        .readAsStringSync();
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    final flow = File('../../.github/workflows/twinconnect-windows-preview.yml')
        .readAsStringSync();
    expect(native, contains('JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE'));
    expect(native, contains('ConvertSidToStringSidW'));
    expect(native, contains('CreateFileW(path.c_str(), GENERIC_READ'));
    expect(native, contains('DeleteFileW(ConfigPath().c_str())'));
    expect(native, contains('mieru.exe'));
    expect(install, contains('stageMieruConfig'));
    expect(install, contains('finishMieruConfig'));
    expect(install, contains('guardMieruProcess'));
    expect(runner, contains('MIERU_CONFIG_JSON_FILE'));
    expect(runner, contains('WindowsMieruProxy'));
    expect(runner, contains('mieruVerifiedExitIp'));
    expect(runner, isNot(contains('print(config)')));
    expect(ui, contains('_startMieruTunnel'));
    expect(ui, contains('protocol: \'mieru\''));
    expect(ui, contains('_mieruProxy.stop()'));
    expect(flow, contains('bundle_mieru_windows.ps1'));
    expect(flow, contains('check_mieru_windows.ps1'));
  });
}
