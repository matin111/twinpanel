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
    expect(platform, contains('func reset(completion: @escaping () -> Void)'));
    expect(platform, contains('let hadSettings = settings != nil'));
    expect(platform, contains('guard hadSettings, let tunnel else {'));
    expect(platform, contains('tunnel.setTunnelNetworkSettings(nil)'));
    expect(platform, contains('MACOS_LIBBOX_TUN_DESCRIPTOR_UNAVAILABLE'));
    expect(platform, contains('settings = nil'));
    expect(engine, contains('platform.reset(completion: completion)'));
    expect(engine, contains('try? server?.closeService()'));
    expect(engine, contains('self.close(completion: completion)'));
    expect(engine, contains('self.close {'));
    expect(platform, contains('tunnel.setTunnelNetworkSettings(nil) { _ in'));
    expect(platform, contains('completion()'));
  });
}
