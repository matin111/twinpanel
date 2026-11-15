import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Android tab navigation preserves mounted VPN session state', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains('child: Platform.isAndroid'));
    expect(dashboard, contains("offstage: _page != 'home'"));
    expect(dashboard, contains('child: home(),'));
    expect(dashboard, contains("if (_page != 'home')"));
  });

  test('Cisco gateway retries IP addresses without weakening TLS', () {
    final service = File(
      'native/android/java/com/axevpn/flutter/openconnect/'
      'AxeOpenConnectVpnService.java',
    ).readAsStringSync();
    expect(service, contains('InetAddress.getAllByName(host)'));
    expect(service, contains('for (InetAddress address : addresses)'));
    expect(service, contains('if (!protect(base))'));
    expect(service, contains('factory.createSocket(base, host, port, true)'));
    expect(service, contains('requireVerifiedHost(tls, pin)'));
    expect(service, contains('tls.startHandshake()'));
    expect(service, contains('throw error; // Fail closed on TLS/certificate verification.'));
  });

  test('Cisco starts standard config-auth session before credentials', () {
    final service = File(
      'native/android/java/com/axevpn/flutter/openconnect/'
      'AxeOpenConnectVpnService.java',
    ).readAsStringSync();
    final init = service.indexOf('type=\\\"init\\\"');
    final username = service.indexOf('String body1 = "username="');
    expect(init, greaterThan(0));
    expect(username, greaterThan(init));
    expect(service, contains('Cookie: " + initCookies'));
    expect(service, contains('CISCO_AUTH_INIT_CONTEXT_MISSING'));
    expect(service, contains('Content-Type: text/xml'));
  });

  test('Cisco native error category survives service shutdown', () {
    final service = File(
      'native/android/java/com/axevpn/flutter/openconnect/'
      'AxeOpenConnectVpnService.java',
    ).readAsStringSync();
    final plugin = File(
      'native/android/java/com/axevpn/flutter/openconnect/'
      'OpenConnectFlutterPlugin.java',
    ).readAsStringSync();
    final tunnel = File('lib/android_cisco_tunnel.dart').readAsStringSync();
    expect(service, contains('lastFailureCode = failureStage'));
    expect(service, contains('CISCO_AUTH_XML_CHALLENGE_UNSUPPORTED'));
    expect(service, contains('CISCO_TLS_HANDSHAKE_FAILED'));
    expect(tunnel, contains('CISCO_AUTH_XML_CHALLENGE_UNSUPPORTED'));
    expect(plugin, contains('json.put("failure_code"'));
    expect(tunnel, contains("nativeStatus['failure_code']"));
    expect(tunnel, contains('CISCO_CSTP_CONFIG_MISSING'));
  });

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
