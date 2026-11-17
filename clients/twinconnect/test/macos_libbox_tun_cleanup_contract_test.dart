import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Libbox macOS TUN clears OS routes and DNS on stop or missing descriptor', () {
    final platform = File(
      'macos_native/libbox/TwinConnectMacLibboxPlatform.swift',
    ).readAsStringSync();
    final engine = File(
      'macos_native/libbox/TwinConnectMacLibboxEngine.swift',
    ).readAsStringSync();
    expect(platform, contains('func reset()'));
    expect(platform, contains('let hadSettings = settings != nil'));
    expect(platform, contains('if hadSettings, let tunnel {'));
    expect(platform, contains('tunnel.setTunnelNetworkSettings(nil)'));
    expect(platform, contains('MACOS_LIBBOX_TUN_DESCRIPTOR_UNAVAILABLE'));
    expect(platform, contains('settings = nil'));
    expect(engine, contains('platform.reset()'));
    expect(engine, contains('try? server?.closeService()'));
  });
}
