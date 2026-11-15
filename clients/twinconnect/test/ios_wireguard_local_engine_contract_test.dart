import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('iOS local WireGuard adapter keeps secrets in Keychain references', () {
    final engine = File('ios_native/TwinConnectWireGuardEngine.swift')
        .readAsStringSync();
    expect(engine, contains('#if canImport(WireGuardKit)'));
    expect(engine, contains('WireGuardAdapter(with: provider)'));
    expect(engine, contains('SecItemCopyMatching'));
    expect(engine, contains('passwordReference'));
    expect(engine, contains('TunnelConfiguration('));
    expect(engine, contains('TwinConnectWireGuardError.engineNotLinked'));
    expect(engine, isNot(contains('print(config)')));
  });

  test('packet extension activates only linked WireGuard or fails closed', () {
    final provider = File('ios_native/PacketTunnelProvider.swift')
        .readAsStringSync();
    expect(provider, contains('case "wireguard":'));
    expect(provider, contains('TwinConnectWireGuardEngine(provider: self)'));
    expect(provider, contains('IOS_PROTOCOL_ENGINE_NOT_INSTALLED'));
    expect(provider, contains('MISSING_PROTOCOL_SELECTION'));
    expect(provider, isNot(contains('setTunnelNetworkSettings(')));
  });

  test('iOS simulator only type-checks, never claims device connectivity', () {
    final yaml = File('../../.github/workflows/twinconnect-ios-simulator.yml')
        .readAsStringSync();
    expect(yaml, contains('ios_native/TwinConnectWireGuardEngine.swift'));
    expect(yaml, contains('ios_native/PacketTunnelProvider.swift'));
    expect(yaml, contains('swiftc -typecheck'));
    expect(yaml, isNot(contains('flutter build ipa')));
  });
}
