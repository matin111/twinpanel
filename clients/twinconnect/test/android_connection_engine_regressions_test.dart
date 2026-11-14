import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Cisco asynchronous startup does not fail on initial disconnected', () {
    final source = File('lib/android_cisco_tunnel.dart').readAsStringSync();
    expect(source, contains('var observedStarting = false;'));
    expect(source, contains("stage == 'disconnected' && observedStarting &&"));
    expect(source, contains("CISCO_AUTH_OR_VPN_PERMISSION_DENIED"));
    expect(source, contains("CISCO_NATIVE_TUNNEL_FAILED"));
    expect(source, isNot(contains("stage == 'disconnected') {")));
  });

  test('OpenVPN and Cisco render moving connection fabric without fake rates', () {
    final card = File('lib/android_connection_card.dart').readAsStringSync();
    final wave = File('lib/twinconnect_wave_indicator.dart').readAsStringSync();
    expect(card, contains('connected: _activeVerifiedTransport,'));
    expect(wave, contains('bool get _animate => widget.connected || widget.connecting;'));
    expect(wave, contains('final active = connected;'));
    expect(wave, contains('widget.rxSamples'));
  });
}
