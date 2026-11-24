import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/macos_hysteria2_controller.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.twinpanel.twinconnect/vpn');
  final messenger = TestDefaultBinaryMessengerBinding
      .instance.defaultBinaryMessenger;

  tearDown(() {
    messenger.setMockMethodCallHandler(channel, null);
  });

  test("Hysteria2 only reports the Apple OS-connected state, never verified", () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'getHysteria2TunnelStatus');
      return <String, dynamic>{
        'contractVersion': 1,
        'protocol': 'hysteria2',
        'state': 'os_connected_unverified',
        'osConnected': true,
        'verified': false,
        'peerHandshakeVerified': false,
      };
    });
    final status = await const MacHysteria2Controller().status();
    if (!Platform.isMacOS) {
      expect(status['state'], 'unavailable');
      expect(status['osConnected'], false);
      return;
    }
    expect(status['state'], 'os_connected_unverified');
    expect(status['osConnected'], true);
    expect(status['verified'], false);
    expect(status['peerHandshakeVerified'], false);
  });

  test('a native unverified OS status may not claim handshake success', () async {
    if (!Platform.isMacOS) return;
    messenger.setMockMethodCallHandler(channel, (call) async => {
      'contractVersion': 1,
      'protocol': 'hysteria2',
      'state': 'os_connected_unverified',
      'osConnected': true,
      'verified': true,
      'peerHandshakeVerified': true,
    });
    expect(const MacHysteria2Controller().status(),
        throwsA(isA<FormatException>()));
  });

  test('rejects impossible OS status transitions and mismatched protocol', () async {
    if (!Platform.isMacOS) return;
    for (final sample in [
      <String, dynamic>{
        'contractVersion': 1,
        'protocol': 'hysteria2',
        'state': 'disconnected',
        'osConnected': true,
        'verified': false,
        'peerHandshakeVerified': false,
      },
      <String, dynamic>{
        'contractVersion': 1,
        'protocol': 'wireguard',
        'state': 'connecting',
        'osConnected': false,
        'verified': false,
        'peerHandshakeVerified': false,
      },
    ]) {
      messenger.setMockMethodCallHandler(channel, (call) async => sample);
      expect(const MacHysteria2Controller().status(),
          throwsA(isA<FormatException>()));
    }
  });

  test('macOS native bridge maintains Hysteria2 unverified OS status', () {
    final host = File('macos_native/TwinConnectMacOSLibboxControl.swift')
        .readAsStringSync();
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    expect(bridge, contains('case "getHysteria2TunnelStatus":'));
    expect(bridge, contains('TwinConnectMacOSLibboxControl.status(result)'));
    expect(host, contains('static func status(_ result: @escaping FlutterResult, protocolCode: String = "hysteria2")'));
    expect(host, contains('os_connected_unverified'));
    expect(host, contains('"peerHandshakeVerified": false'));
    expect(host, contains('"verified": false'));
  });
}
