import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS connection page uses panel-backed proxy test, not Windows card', () {
    final main = File('lib/main.dart').readAsStringSync();
    final card = File('lib/macos_standalone_connection_card.dart')
        .readAsStringSync();
    final adapter = File('lib/macos_standalone_panel_profile.dart')
        .readAsStringSync();
    final runtime = File('lib/macos_standalone_proxy_runtime.dart')
        .readAsStringSync();

    expect(main, contains('TargetPlatform.macOS'));
    expect(main, contains('MacStandaloneConnectionCard('));
    expect(card, contains('MacStandalonePanelProfile('));
    expect(card, contains('MacStandaloneProxyRuntime('));
    expect(adapter, contains('api.loadSessionProtocolCatalog('));
    expect(adapter, contains('api.refreshSessionServers('));
    expect(adapter, contains('api.loadSessionNativeProfiles('));
    expect(adapter, contains('entry.selected && entry.configRecordPresent'));
    expect(adapter, contains("item['node_id']?.toString() == serverId"));
    expect(card, contains('system VPN is not active'));
    expect(runtime, contains("socks5h://127.0.0.1:"));
    expect(runtime, contains("'https://api.ipify.org'"));
    expect(runtime, contains('engine?.kill(ProcessSignal.sigterm)'));
    expect(runtime, contains('privateDirectory.delete(recursive: true)'));
    expect(runtime, isNot(contains('route add')));
    expect(runtime, isNot(contains('networksetup')));
  });

  test('local proxy panel adapter does not allow a full tunnel claim', () {
    final adapter = File('lib/macos_standalone_panel_profile.dart')
        .readAsStringSync();
    final runtime = File('lib/macos_standalone_proxy_runtime.dart')
        .readAsStringSync();

    expect(adapter, contains("'type': 'mixed'"));
    expect(adapter, contains("'listen': '127.0.0.1'"));
    expect(adapter, contains("'route': {'final': 'proxy'}"));
    expect(runtime, contains('bool get systemWideVpn => false'));
    expect(adapter, isNot(contains('NETunnelProvider')));
  });
}
