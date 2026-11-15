import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/vitory_server_visibility.dart';

void main() {
  test('Vitory never shows nodes without either protocol', () {
    for (final filter in ['all', 'v2ray', 'hysteria2']) {
      expect(VitoryServerVisibility.shows(
        protocolFilter: filter,
        hasValidV2rayInbound: false,
        hasValidHysteriaProfile: false,
      ), isFalse, reason: 'filter=$filter');
    }
  });

  test('Hysteria-only Finland remains visible only for Hysteria and All', () {
    bool shown(String filter) => VitoryServerVisibility.shows(
      protocolFilter: filter,
      hasValidV2rayInbound: false,
      hasValidHysteriaProfile: true,
    );
    expect(shown('all'), isTrue);
    expect(shown('v2ray'), isFalse);
    expect(shown('hysteria2'), isTrue);
  });

  test('US or Germany with actual Xray inbounds appears in V2Ray', () {
    bool shown(String filter) => VitoryServerVisibility.shows(
      protocolFilter: filter,
      hasValidV2rayInbound: true,
      hasValidHysteriaProfile: false,
    );
    expect(shown('all'), isTrue);
    expect(shown('v2ray'), isTrue);
    expect(shown('hysteria2'), isFalse);
  });

  test('nodes with both verified profiles appear in both lists', () {
    for (final filter in ['all', 'v2ray', 'hysteria2']) {
      expect(VitoryServerVisibility.shows(
        protocolFilter: filter,
        hasValidV2rayInbound: true,
        hasValidHysteriaProfile: true,
      ), isTrue);
    }
  });

  test('Vitory cannot accidentally expose Cisco or WireGuard nodes', () {
    for (final filter in ['cisco', 'wireguard', 'openvpn', 'l2tp']) {
      expect(VitoryServerVisibility.shows(
        protocolFilter: filter,
        hasValidV2rayInbound: true,
        hasValidHysteriaProfile: true,
      ), isFalse);
    }
  });
}
