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
    final cacheCallback = platform.split('func clearDNSCache() {').last
        .split('func readWIFIState()').first;
    expect(cacheCallback, isNot(contains('setTunnelNetworkSettings(')));
    expect(cacheCallback, isNot(contains('tunnel.setTunnelNetworkSettings(settings)')));
    expect(platform, contains('func reset(completion: @escaping () -> Void)'));
    expect(platform, contains('let hadSettings = settings != nil'));
    expect(platform, contains('guard hadSettings, let tunnel else {'));
    expect(platform, contains('tunnel.setTunnelNetworkSettings(nil)'));
    expect(platform, contains('MACOS_LIBBOX_TUN_DESCRIPTOR_UNAVAILABLE'));
    expect(platform, contains('let applyLock = NSLock()'));
    expect(platform, contains('var applyFinished = false'));
    expect(platform, contains('var applyTimedOut = false'));
    expect(platform, contains('let mustRollback = applyTimedOut'));
    expect(platform, contains('if mustRollback {'));
    expect(platform, contains('applyTimedOut = true'));
    expect(platform, contains('if completedBeforeTimeout {'));
    expect(platform, contains('MACOS_LIBBOX_TUN_NETWORK_SETTINGS_TIMEOUT'));
    expect(platform, contains('let stoppedDuringApply = stopped'));
    // Stop state and local network-settings ownership share the same lock.
    expect(platform, contains('if !stoppedDuringApply {'));
    expect(platform, contains('settings = candidate'));
    expect(platform, contains('let hadSettings = settings != nil'));
    expect(platform, contains('stateLock.lock()'));
    expect(platform, contains('stateLock.unlock()'));
    expect(platform, contains('guard !stoppedDuringApply else {'));
    expect(platform, contains('settings = nil'));
    expect(engine, contains('platform.reset(completion: completion)'));
    expect(engine, contains('try? server?.closeService()'));
    expect(engine, contains('self.close(completion: completion)'));
    expect(engine, contains('self.close {'));
    expect(platform, contains('tunnel.setTunnelNetworkSettings(nil) { _ in'));
    expect(platform, contains('completion()'));
  });
}
